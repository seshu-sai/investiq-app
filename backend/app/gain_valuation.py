"""Preference-based earnings sensitivities and transparent research screening."""
from datetime import date, datetime, timezone
import math
import hashlib
import json
from statistics import median

from .data_utils import finite_number

RISK_LIMITS = {'low': {'goal': 6, 'loss': 15, 'volatility': 20},
               'medium': {'goal': 10, 'loss': 30, 'volatility': 40},
               'high': {'goal': 14, 'loss': 50, 'volatility': 70}}
HORIZON_YEARS = {'0-1': 1, '1-3': 2, '3-5': 4, '5+': 5}


def earnings_scenarios(fundamentals, financials, price, years, annual_goal):
    eps = finite_number(fundamentals.get('trailing_eps'))
    if not price.get('valid') or eps is None or eps <= 0 or fundamentals.get('currency') != price.get('currency'):
        return {'status': 'unavailable', 'reason': 'Positive trailing EPS and a usable same-currency quote are required', 'scenarios': []}
    rows = sorted(financials.get('history') or [], key=lambda row: row.get('fiscal_year_end', ''))[-4:]
    growth, eps_history = [], []
    for row in rows:
        value = finite_number(row.get('diluted_eps'))
        try:
            end = date.fromisoformat(row.get('fiscal_year_end'))
        except (TypeError, ValueError):
            continue
        if value is not None and value > 0 and end <= datetime.now(timezone.utc).date():
            eps_history.append((end, value))
    if len(eps_history) < 3 or any(not 330 <= (b[0] - a[0]).days <= 400 for a, b in zip(eps_history, eps_history[1:])):
        return {'status': 'unavailable', 'reason': 'Three consecutive positive annual diluted-EPS records are needed for company-specific growth sensitivities', 'scenarios': []}
    if (datetime.now(timezone.utc).date() - eps_history[-1][0]).days > 540:
        return {'status': 'unavailable', 'reason': 'Annual earnings evidence is stale', 'scenarios': []}
    growth = [b[1] / a[1] - 1 for a, b in zip(eps_history, eps_history[1:])]
    if any(not math.isfinite(value) for value in growth):
        return {'status': 'unavailable', 'reason': 'Invalid earnings growth', 'scenarios': []}
    # A cautious shrinkage/cap policy, not an estimated or calibrated forecast.
    central = max(-.10, min(.10, median(growth) * .5))
    current_pe = price['price'] / eps
    assumptions = [('Downside', min(0, central - .10), min(current_pe, 15) * .8),
                   ('Base', central, min(current_pe, 20)),
                   ('Upside', min(.15, central + .05), min(current_pe, 25))]
    scenarios = []
    for name, rate, multiple in assumptions:
        future_eps = eps * (1 + rate) ** years
        future_price = future_eps * multiple
        total = future_price / price['price'] - 1
        scenarios.append({'name': name, 'future_price': round(future_price, 2),
                          'total_return_percent': round(total * 100, 2),
                          'annualized_return_percent': round(((1 + total) ** (1 / years) - 1) * 100, 2),
                          'eps_growth_percent': round(rate * 100, 2), 'exit_pe': round(multiple, 2)})
    base = scenarios[1]
    entry = (eps * (1 + central) ** years * min(current_pe, 20)) / (1 + annual_goal / 100) ** years
    return {'status': 'illustrative', 'years': years, 'scenarios': scenarios,
            'historical_eps_growth_percent': [round(value * 100, 2) for value in growth],
            'goal_entry_price': round(entry, 2), 'current_trailing_pe': round(current_pe, 2),
            'definition': 'Future trailing EPS × assumed exit P/E. Base growth is half the median annual EPS growth, capped at -10% to +10%. Exit P/E caps: downside 15× with 20% compression, base 20×, upside 25×.',
            'limitations': 'Sensitivity calculations, not calibrated predictions or intrinsic values. No dividends, taxes, trading/FX fees or future currency moves. Historical EPS may be restated or affected by splits. A terminal loss limit is not a stop-loss or an interim drawdown limit.'}


def build_gain_view(snapshot, history, profile, fx, *, annual_goal=None, max_loss=None,
                    max_volatility=None, max_downside=None, min_history_years=None,
                    max_quote_age_minutes=None, min_excess_return=None, cost_basis=None, shares=None):
    from .advisor import assess_evidence
    from .price_validation import validate_market_quote
    risk = profile.get('risk', 'medium')
    limits = RISK_LIMITS.get(risk, RISK_LIMITS['medium'])
    goal = annual_goal if annual_goal is not None else limits['goal']
    loss = max_loss if max_loss is not None else limits['loss']
    volatility_limit = max_volatility if max_volatility is not None else limits['volatility']
    downside_limit = max_downside if max_downside is not None else loss
    minimum_history = min_history_years if min_history_years is not None else 3
    quote_age_limit = max_quote_age_minutes if max_quote_age_minutes is not None else 15
    excess_return_limit = min_excess_return if min_excess_return is not None else 0
    years = HORIZON_YEARS.get(profile.get('horizon'), 4)
    criteria = {'annual_goal': float(goal), 'max_loss': float(loss),
                'max_volatility': float(volatility_limit), 'max_downside': float(downside_limit),
                'min_history_years': int(minimum_history), 'max_quote_age_minutes': int(quote_age_limit),
                'min_excess_return': float(excess_return_limit)}
    defaults = {'annual_goal': limits['goal'], 'max_loss': limits['loss'],
                'max_volatility': limits['volatility'], 'max_downside': limits['loss'],
                'min_history_years': 3, 'max_quote_age_minutes': 15, 'min_excess_return': 0}
    context = {'market': snapshot['market'], 'symbol': snapshot['symbol'],
               'criteria': criteria, 'risk': risk, 'horizon': profile.get('horizon'),
               'currency': profile.get('currency'), 'amount': float(profile['amount']),
               'markets': sorted(profile.get('markets', [])), 'assets': sorted(profile.get('assets', []))}
    screening_key = hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()
    custom = any(value is not None for value in (annual_goal, max_loss, max_volatility, max_downside,
                                                min_history_years, max_quote_age_minutes, min_excess_return))
    quote = validate_market_quote(snapshot.get('quote'))
    assessment = assess_evidence(snapshot['market'], snapshot['symbol'], snapshot['fundamentals'],
                                 snapshot['historical_financials'], snapshot.get('quote'), profile)
    valuation = earnings_scenarios(snapshot['fundamentals'], snapshot['historical_financials'], quote, years, goal)
    amount = float(profile['amount'])
    currency = (snapshot.get('quote') or {}).get('currency')
    fx_rate = finite_number((fx or {}).get('rate'))
    if fx_rate is not None and fx_rate <= 0:
        fx_rate = None
    budget_in_quote = amount * fx_rate if fx_rate is not None else None
    units = budget_in_quote / quote['price'] if budget_in_quote is not None and quote['valid'] else None
    for scenario in valuation.get('scenarios', []):
        # Translate the price change to the saved budget, keeping FX fixed; do not invent an FX forecast.
        gain = amount * scenario['total_return_percent'] / 100 if units is not None else None
        scenario['gain_in_base_currency'] = round(gain, 2) if gain is not None else None
        scenario['ending_value_in_base_currency'] = round(amount + gain, 2) if gain is not None else None
    replay = history.get('rolling_history') or {}
    historical_cases = []
    if replay.get('status') == 'available':
        for name, key in [('Historical 10th percentile', 'downside_percent'), ('Historical median', 'median_percent'), ('Historical 90th percentile', 'upside_percent')]:
            total = replay[key]
            gain = amount * total / 100 if units is not None else None
            historical_cases.append({'name': name, 'return_percent': total,
                                     'gain_in_base_currency': round(gain, 2) if gain is not None else None})
    unrealized = None
    if cost_basis is not None and shares is not None and quote['valid']:
        unrealized = {'shares': shares, 'average_buy_price': cost_basis, 'currency': currency,
                      'gain': round((quote['price'] - cost_basis) * shares, 2),
                      'return_percent': round((quote['price'] / cost_basis - 1) * 100, 2),
                      'market_value': round(quote['price'] * shares, 2)}

    checks = []
    def check(label, passed, detail):
        checks.append({'label': label, 'passed': bool(passed), 'detail': detail})
    check('Usable price', quote['valid'], quote['reason'])
    check('Recent trade timestamp', quote['valid'] and quote.get('age_seconds', 1e9) <= quote_age_limit * 60 and (snapshot.get('quote') or {}).get('price_type') != 'daily_bar',
          f'A buy candidate requires a provider trade timestamp within your {quote_age_limit} minute limit; daily bars do not qualify.')
    check('Financial evidence', not assessment['missing_data'], '; '.join(assessment['missing_data']) or 'Three consecutive recent annual periods available.')
    check('Historical coverage', history.get('status') == 'available' and history.get('years_available', 0) >= max(minimum_history, years),
          f'Your minimum is {minimum_history} years; the {years}-year modeled holding period also requires coverage. Required: {max(minimum_history, years)} years.')
    drawdown = abs(history.get('max_drawdown_percent') or 0)
    volatility = history.get('annualized_volatility_percent')
    check('Loss tolerance', history.get('status') == 'available' and drawdown <= loss,
          f'Observed maximum drawdown {drawdown:.1f}% versus your {loss:g}% loss limit. Future losses can be worse.')
    check('Risk profile', volatility is not None and volatility <= volatility_limit,
          f'Historical annualized volatility {volatility if volatility is not None else "unknown"}% versus your {volatility_limit:g}% volatility limit. Saved risk label: {risk}.')
    fit = profile.get('horizon') != '0-1' and snapshot['market'] in profile.get('markets', []) and 'stocks' in profile.get('assets', [])
    check('Preference fit', fit, 'Individual stock must match saved markets/assets and a horizon longer than one year.')
    check('Earnings valuation', valuation['status'] == 'illustrative', valuation.get('reason') or 'Positive dated earnings and explicit growth/multiple assumptions available.')
    scenarios = valuation.get('scenarios') or []
    base = next((row for row in scenarios if row['name'] == 'Base'), {})
    downside = next((row for row in scenarios if row['name'] == 'Downside'), {})
    check('Return goal', base.get('annualized_return_percent', -1e9) >= goal,
          f'Base annualized sensitivity is {base.get("annualized_return_percent", "unavailable")}% versus your {goal:g}% annual return hurdle; this is not an expected return.')
    check('Downside sensitivity', downside.get('total_return_percent', -1e9) >= -downside_limit,
          f'Modeled terminal downside return is {downside.get("total_return_percent", "unavailable")}% versus your {downside_limit:g}% maximum scenario-loss limit; interim falls may be larger.')
    benchmark = history.get('benchmark') or {}
    check('Benchmark comparison', benchmark.get('excess_cagr_percentage_points', -1e9) >= excess_return_limit,
          f'Historical excess return is {benchmark.get("excess_cagr_percentage_points", "unknown")} percentage points per year versus your {excess_return_limit:g} point minimum. Past outperformance may reverse.')
    check('Currency conversion', units is not None, 'A dated conversion rate is required for budget gain figures.')
    reasons = [row['detail'] for row in checks if not row['passed']]
    insufficient = not quote['valid'] or history.get('status') != 'available' or bool(assessment['missing_data'])
    unsuitable = not fit or (history.get('status') == 'available' and (drawdown > loss or (volatility is not None and volatility > volatility_limit)))
    eligible = all(row['passed'] for row in checks)
    verdict = 'INSUFFICIENT DATA' if insufficient else 'NOT SUITABLE' if unsuitable else 'WAIT'
    reason = reasons[0] if reasons else 'Quantitative checks pass. Review current company-specific web evidence before treating this as a buy candidate.'
    if unsuitable and not insufficient:
        reason = next(row['detail'] for row in checks if not row['passed'] and row['label'] in ('Loss tolerance', 'Risk profile', 'Preference fit'))
    return {'market': snapshot['market'], 'symbol': snapshot['symbol'], 'company': snapshot['fundamentals'].get('company'),
            'generated_at': datetime.now(timezone.utc).isoformat(), 'quote': snapshot.get('quote'), 'quote_validation': quote,
            'preferences': {**profile, 'annual_return_goal_percent': goal, 'max_loss_percent': loss,
                            'max_volatility_percent': volatility_limit, 'max_downside_percent': downside_limit,
                            'min_history_years': minimum_history, 'required_history_years': max(minimum_history, years),
                            'max_quote_age_minutes': quote_age_limit,
                            'min_excess_return_percentage_points': excess_return_limit,
                            'modeled_years': years, 'applied_screening': criteria, 'screening_defaults': defaults,
                            'screening_key': screening_key,
                            'screening_mode': 'custom' if custom else 'profile_defaults',
                            'screening_note': 'The explicit applied screening values are authoritative for this review, including overrides of risk presets. The saved risk label is context; a permissive custom screen does not make a stock low risk. The amount models a hypothetical full-budget allocation, not a position-size recommendation.'},
            'budget': {'amount': amount, 'base_currency': profile['currency'], 'stock_currency': currency,
                       'amount_in_stock_currency': round(budget_in_quote, 2) if budget_in_quote is not None else None,
                       'hypothetical_fractional_shares': round(units, 6) if units is not None else None,
                       'fx': fx, 'fx_note': 'Base-currency gain examples assume unchanged FX. Rates are daily, not real-time; costs and tax are excluded.'},
            'historical': history, 'historical_budget_cases': historical_cases, 'valuation': valuation,
            'unrealized_gain': unrealized,
            'buy_assessment': {'verdict': verdict, 'reason': reason, 'quantitative_candidate': eligible,
                               'checks': checks, 'research_required': True,
                               'method': 'Uncalibrated research screen combining earnings sensitivities, historical risk/benchmark evidence and saved preferences; not an execution instruction.'},
            'sources': snapshot['sources'], 'warnings': list(dict.fromkeys(snapshot['warnings'] + assessment['warnings'] + assessment['investor_fit']['warnings'])),
            'web_research': {'status': 'not_requested', 'summary': '', 'segments': [], 'sources': []},
            'disclaimer': 'Future gains and buy signals are uncertain. Scenarios are conditional calculations, not promises. The stock can lose more than the modeled downside.'}
