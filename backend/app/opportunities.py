"""Explicit weeks-to-months entry rules and risk-sized arithmetic, separate from earnings valuation."""
from datetime import date, datetime, timezone
import hashlib
import json
import math
from statistics import mean
from zoneinfo import ZoneInfo

from .data_utils import finite_number
from .market_setup import MARKET_ZONES

RISK_PERCENT = {'low': .5, 'medium': 1, 'high': 2}
POLICY = 'trend-and-observed-range-v1'


def price_levels(history, market, holding_weeks, now):
    today = now.astimezone(ZoneInfo(MARKET_ZONES[market])).date()
    bars = []
    for row in (history or {}).get('bars', []):
        when = date.fromisoformat(row['date'])
        if when == today:
            continue  # Provisional bars can have inconsistent OHLC fields while the session is open.
        values = [finite_number(row.get(key)) for key in ('open', 'high', 'low', 'close')]
        if any(value is None or value <= 0 for value in values):
            raise ValueError('Daily high/low prices are incomplete')
        opening, high, low, closing = values
        if not low <= min(opening, closing) <= max(opening, closing) <= high:
            raise ValueError('Daily high/low prices are inconsistent')
        if bars and when <= bars[-1][0]:
            raise ValueError('Daily high/low prices are unordered')
        if when > today:
            raise ValueError('Daily high/low prices contain a future date')
        if when < today:
            bars.append((when, high, low, closing))
    if len(bars) < 61 or (today - bars[-1][0]).days > 4:
        raise ValueError('At least 61 recent completed daily high/low prices are required')
    bars = bars[-260:]
    if any((b[0] - a[0]).days > 10 for a, b in zip(bars, bars[1:])):
        raise ValueError('Daily high/low prices contain a gap over ten days')
    ranges = [max(b[1] - b[2], abs(b[1] - a[3]), abs(b[2] - a[3])) for a, b in zip(bars, bars[1:])]
    atr = mean(ranges[:14])
    for value in ranges[14:]:
        atr = (atr * 13 + value) / 14
    if atr <= 0:
        raise ValueError('Daily trading ranges are too small to establish exit levels')
    closes = [row[3] for row in bars]
    lookback = min(len(bars), 126, holding_weeks * 5)
    return {'sma20': mean(closes[-20:]), 'sma50': mean(closes[-50:]), 'atr14': atr,
            'recent_high': max(row[1] for row in bars[-lookback:]), 'lookback_sessions': lookback,
            'as_of': bars[-1][0].isoformat()}


def build_opportunity(view, history, *, holding_weeks=12, loss_amount=None, min_reward_risk=1.5,
                      round_trip_cost_percent=.2, planned_stop=None, planned_target=None,
                      risk_budget=None, explicit_stock_limits=False, now=None):
    now = now or datetime.now(timezone.utc)
    preferences = view['preferences']
    amount = view['budget']['amount']
    loss = loss_amount if loss_amount is not None else amount * (risk_budget if risk_budget is not None else RISK_PERCENT.get(preferences['risk'], 1)) / 100
    inputs = {'holding_weeks': holding_weeks, 'loss_amount': float(loss), 'min_reward_risk': float(min_reward_risk),
              'round_trip_cost_percent': float(round_trip_cost_percent), 'planned_stop': planned_stop,
              'planned_target': planned_target, 'explicit_stock_limits': explicit_stock_limits}
    key = hashlib.sha256(json.dumps({'screening_key': preferences['screening_key'], **inputs}, sort_keys=True).encode()).hexdigest()
    result = {'policy': POLICY, 'key': key, 'verdict': 'INSUFFICIENT DATA', 'reason': '', 'eligible': False,
              'inputs': inputs, 'plan': None, 'checks': [], 'context': [],
              'news_review': {'status': 'not_requested', 'reason': 'Company news has not been reviewed for this plan.'},
              'limitations': 'This investing rule has not been proven profitable. The target may never be reached, and actual exit losses can be larger than shown. Costs are estimates. The budget is money available for this stock. No order is placed.'}
    checks = result['checks']
    def check(label, passed, detail):
        checks.append({'label': label, 'passed': bool(passed), 'detail': detail})
    setup = view.get('market_setup') or {}
    check('Current trade price', setup.get('quote_fresh'), 'A recent provider trade quote is required. Daily closes do not qualify.')
    check('Matches your markets and assets', setup.get('profile_fit'), 'Use stocks in your saved markets and asset types.')
    check('Company identified', bool(view.get('company')), 'Company identity must be known before considering an investment.')
    fx = finite_number((view['budget'].get('fx') or {}).get('rate'))
    check('Currency conversion', fx is not None and fx > 0, 'A dated currency conversion is required for money figures.')
    check('Money at risk', 0 < loss <= amount, 'Planned loss must be positive and no larger than your available money.')
    if explicit_stock_limits:
        risk = [row for row in view['buy_assessment']['checks'] if row['label'] in explicit_stock_limits]
        check('Your optional stock-risk limits', bool(risk) and all(row['passed'] for row in risk),
              'You explicitly selected stock drawdown/volatility limits; those limits remain binding.')
    try:
        levels = price_levels(history, view['market'], holding_weeks, now)
        check('Recent trading levels', setup.get('status') != 'unavailable', 'Completed daily prices establish the entry and exit references.')
    except (ValueError, TypeError, KeyError) as exc:
        result['reason'] = str(exc) if isinstance(exc, ValueError) else 'Recent daily price evidence is incomplete.'
        return result
    for row in view['buy_assessment']['checks']:
        if row['label'] in ('Loss tolerance', 'Risk profile', 'Return goal', 'Downside sensitivity') and not row['passed']:
            result['context'].append(row['detail'])
    current = view['quote_validation'].get('price')
    if not all(row['passed'] for row in checks):
        failed = next(row for row in checks if not row['passed'])
        result.update(verdict='WAIT', reason=failed['detail'])
        return result
    support = levels['sma20'] if current > levels['sma20'] else levels['sma50']
    stop = planned_stop if planned_stop is not None else round(max(.0001, support - levels['atr14']), 4)
    target = planned_target if planned_target is not None else round(levels['recent_high'], 4)
    if not 0 < stop < current < target:
        result.update(verdict='WAIT', reason='No valid upward price range is available at this price. Review the chart or enter your own exit and target under Advanced options.')
        return result
    cost = round_trip_cost_percent / 100
    per_share_loss = current - stop + current * cost
    per_share_gain = target - current - current * cost
    ratio = per_share_gain / per_share_loss
    ceiling = (target + min_reward_risk * stop) / ((1 + min_reward_risk) * (1 + cost))
    units = math.floor(min(amount * fx / (current * (1 + cost / 2)), loss * fx / per_share_loss))
    check('Recent upward trend', setup.get('trend') == 'SUPPORTIVE', 'Price and the short-term average must be above the 50-session average.')
    check('Observed target evidence', planned_target is None or target <= levels['recent_high'],
          'A manually entered target above the observed trading range is a personal scenario, not evidence for a buy setup.')
    check('Profit compared with planned loss', ratio >= min_reward_risk,
          f'After estimated costs, target profit is {ratio:.2f} times planned loss; your minimum is {min_reward_risk:g}.')
    check('Affordable position', units >= 1,
          f'At these levels, one whole share needs about {per_share_loss / fx:.2f} {preferences["currency"]} of planned loss capacity; your answer allows {loss:.2f}.')
    result['plan'] = {'entry_price': current, 'buy_up_to': round(ceiling, 4), 'exit_price': stop, 'target_price': target,
                      'target_basis': 'Your entered price' if planned_target is not None else f"Highest traded price in the last {levels['lookback_sessions']} completed sessions",
                      'exit_basis': 'Your entered price' if planned_stop is not None else 'Recent moving-average support minus one daily average true range',
                      'levels_as_of': levels['as_of'], 'shares': units, 'money_used': round(units * current * (1 + cost / 2) / fx, 2),
                      'money_unallocated': round(amount - units * current * (1 + cost / 2) / fx, 2),
                      'planned_loss': round(units * per_share_loss / fx, 2), 'potential_gain': round(units * per_share_gain / fx, 2),
                      'gain_on_position_percent': round(per_share_gain / (current * (1 + cost / 2)) * 100, 2),
                      'reward_risk': round(ratio, 2), 'estimated_round_trip_cost': round(units * current * cost / fx, 2)}
    result['eligible'] = all(row['passed'] for row in checks)
    if result['eligible']:
        result.update(verdict='BUY SETUP', reason='The recent upward trend and target-versus-exit range support a risk-sized entry. Check current company news before acting.')
    elif setup.get('trend') != 'SUPPORTIVE':
        result.update(verdict='WAIT FOR TREND', reason='The recent price trend is mixed or weak. An attractive target alone is not an entry signal.')
    elif ratio < min_reward_risk:
        result.update(verdict='WAIT FOR BETTER PRICE', reason=f'The current price leaves too little potential profit compared with planned loss. With the same levels, a price at or below {ceiling:.2f} would meet your reward/loss requirement; the trend must also remain supportive.')
    else:
        result.update(verdict='WAIT', reason=next(row['detail'] for row in checks if not row['passed']))
    return result
