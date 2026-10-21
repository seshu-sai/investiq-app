"""Current quote against completed daily price trends; no return forecast or buy verdict."""
from datetime import date, datetime, timezone
from statistics import mean
from zoneinfo import ZoneInfo

from .data_utils import finite_number
from .price_validation import validate_market_quote

MARKET_ZONES = {'US': 'America/New_York', 'CA': 'America/Toronto', 'IN': 'Asia/Kolkata'}


def completed_prices(history, today):
    """Exclude today's possibly provisional bar, reject bad dates/values and recent gaps."""
    rows = history.get('price_closes') or []
    result = []
    previous = None
    for row in rows:
        when = date.fromisoformat(row['date'])
        value = finite_number(row.get('close'))
        if value is None or value <= 0 or (previous is not None and when <= previous):
            raise ValueError('Invalid or unordered daily prices')
        previous = when
        if when > today:
            raise ValueError('Daily prices include a future session')
        if when < today:
            result.append((when, value))
    if len(result) < 61:
        raise ValueError('At least 61 completed daily sessions are needed for the current-market view')
    result = result[-260:]
    if not 0 <= (today - result[-1][0]).days <= 4:
        raise ValueError('Completed daily prices are stale')
    if any((b[0] - a[0]).days > 10 for a, b in zip(result, result[1:])):
        raise ValueError('Daily prices contain gaps over ten days')
    return result


def rsi(values, period=14):
    changes = [b - a for a, b in zip(values, values[1:])]
    up = mean(max(change, 0) for change in changes[:period])
    down = mean(max(-change, 0) for change in changes[:period])
    for change in changes[period:]:
        up = (up * (period - 1) + max(change, 0)) / period
        down = (down * (period - 1) + max(-change, 0)) / period
    return 50.0 if up == down == 0 else 100.0 if down == 0 else 100 - 100 / (1 + up / down)


def build_market_setup(history, benchmark, quote, preferences, risk_checks, *, market, now=None):
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(ZoneInfo(MARKET_ZONES[market])).date()
    validated = validate_market_quote(quote, now=now)
    age_limit = preferences['max_quote_age_minutes']
    fresh = (validated['valid'] and (quote or {}).get('price_type') != 'daily_bar'
             and validated.get('age_seconds', 1e9) <= age_limit * 60)
    risk_conflicts = [row['detail'] for row in risk_checks
                      if row['label'] in ('Loss tolerance', 'Risk profile') and not row['passed']]
    fit = market in preferences.get('markets', []) and 'stocks' in preferences.get('assets', [])
    result = {'status': 'unavailable', 'label': 'INSUFFICIENT RECENT DATA', 'trend': None,
              'reason': '', 'as_of': None, 'timeframe': 'Daily trend context for entries over days to weeks',
              'quote_fresh': fresh, 'is_realtime': validated.get('is_realtime', False),
              'quote_age_limit_minutes': age_limit, 'metrics': {}, 'signals': [],
              'risk_conflicts': risk_conflicts, 'profile_fit': fit,
              'definition': '20/50-session simple moving averages, 20/60-session price changes and Wilder 14-session RSI use completed daily closes. Latest provider quote is compared with the 50-session average. No weighted score or probability.',
              'limitations': 'A descriptive trend screen, not a buy recommendation or profit forecast. Daily indicators lag and can reverse. News, earnings, spreads, liquidity and portfolio suitability require separate review. Daily bars are not an intraday feed.'}
    try:
        prices = completed_prices(history or {}, today)
        if not history.get('currency') or history.get('currency') != (quote or {}).get('currency'):
            raise ValueError('Daily price currency does not match the quote')
    except (TypeError, KeyError, ValueError) as exc:
        result['reason'] = str(exc) if isinstance(exc, ValueError) else 'Daily price evidence is incomplete'
        return result

    values = [row[1] for row in prices]
    sma20, sma50 = mean(values[-20:]), mean(values[-50:])
    # Price closes are split adjusted, without dividend adjustment, matching the quote price basis.
    current = validated.get('price') if fresh else values[-1]
    trend = 'SUPPORTIVE' if current > sma50 and sma20 > sma50 else 'WEAK' if current < sma50 and sma20 < sma50 else 'MIXED'
    strength = rsi(values)
    momentum20, momentum60 = (values[-1] / values[-21] - 1) * 100, (values[-1] / values[-61] - 1) * 100
    relative = None
    try:
        other = dict(completed_prices(benchmark or {}, today))
        start, end = prices[-61][0], prices[-1][0]
        if benchmark.get('currency') == history.get('currency') and start in other and end in other:
            other_return = (other[end] / other[start] - 1) * 100
            relative = {'symbol': benchmark.get('symbol'), 'start': start.isoformat(), 'end': end.isoformat(),
                        'stock_return_percent': round(momentum60, 2), 'benchmark_return_percent': round(other_return, 2),
                        'excess_return_points': round(momentum60 - other_return, 2)}
    except (TypeError, KeyError, ValueError):
        pass  # Missing benchmark is an explicit context gap, not an invented neutral score.
    signals = [
        {'label': 'Price trend', 'state': trend.lower(), 'detail': f'20-session average {sma20:.2f}; 50-session average {sma50:.2f}. ' + ('Latest quote' if fresh else 'Last completed close') + f' {current:.2f}.'},
        {'label': 'Recent momentum', 'state': 'positive' if momentum20 > 0 else 'negative' if momentum20 < 0 else 'flat',
         'detail': f'{momentum20:+.2f}% over 20 completed sessions; {momentum60:+.2f}% over 60.'},
        {'label': 'Momentum temperature', 'state': 'elevated' if strength >= 70 else 'low' if strength <= 30 else 'mid_range',
         'detail': f'14-session RSI {strength:.1f}. Above 70 suggests elevated momentum; below 30 suggests depressed momentum. Neither is an automatic entry or exit.'},
        {'label': 'Recent benchmark comparison', 'state': 'unavailable' if relative is None else 'leading' if relative['excess_return_points'] > 0 else 'lagging' if relative['excess_return_points'] < 0 else 'matching',
         'detail': 'Matching-date benchmark evidence is unavailable.' if relative is None else f"{relative['excess_return_points']:+.2f} percentage points versus {relative['symbol']} from {relative['start']} to {relative['end']}."},
    ]
    status, label = 'available', f'{trend} TREND'
    reason = {'SUPPORTIVE': 'Price and short-term trend are above the 50-session average. Review current news and entry risk before acting.',
              'WEAK': 'Price and short-term trend are below the 50-session average. A falling price alone does not establish a bargain.',
              'MIXED': 'Price and moving-average trends disagree or are flat. There is no clear trend alignment.'}[trend]
    if not fresh:
        status, label = 'quote_required', 'FRESH TRADE QUOTE NEEDED'
        reason = f'Trend context uses the last completed close. A trade quote within your {age_limit}-minute limit is needed for a current-price comparison; daily bars do not qualify.'
    elif not fit or risk_conflicts:
        status, label = 'risk_conflict', 'REVIEW YOUR RISK LIMITS'
        reason = 'The price trend is descriptive. This stock conflicts with your selected markets/assets or historical risk limits; a favorable trend does not clear those conflicts.'
    elif trend == 'SUPPORTIVE' and strength >= 70:
        label = 'SUPPORTIVE BUT EXTENDED'
        reason = 'Trend alignment is supportive, but daily RSI is elevated. Chasing a rise can expose you to a pullback; this is not an automatic entry.'
    result.update(status=status, label=label, trend=trend, reason=reason, as_of=prices[-1][0].isoformat(),
                  metrics={'sma20': round(sma20, 4), 'sma50': round(sma50, 4),
                           'distance_from_sma50_percent': round((current / sma50 - 1) * 100, 2),
                           'momentum20_percent': round(momentum20, 2), 'momentum60_percent': round(momentum60, 2),
                           'rsi14': round(strength, 2), 'relative_strength': relative}, signals=signals)
    return result
