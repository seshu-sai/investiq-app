"""Adjusted historical returns and daily FX. Historical outcomes are not forecasts."""
from bisect import bisect_left, bisect_right
from datetime import date, datetime, timedelta, timezone
import math
from statistics import stdev

import yfinance as yf

from .data_utils import finite_number, normalize_symbol, ttl_cache

BENCHMARKS = {'US': ('SPY', 'S&P 500 ETF'), 'CA': ('XIC.TO', 'Canadian broad-market ETF'),
              'IN': ('NIFTYBEES.NS', 'Nifty 50 ETF')}


class HistoryError(ValueError):
    pass


def _rows(frame):
    if frame.empty or 'Close' not in frame:
        raise HistoryError('Historical prices are unavailable')
    result = []
    for index, row in frame.iterrows():
        value = finite_number(float(row['Close']))
        session = index.date()
        if value is not None and value > 0 and session <= datetime.now(timezone.utc).date():
            result.append({'date': session.isoformat(), 'close': value})
    result.sort(key=lambda row: row['date'])
    if len(result) < 2 or len({row['date'] for row in result}) != len(result):
        raise HistoryError('Insufficient unique historical sessions')
    return result


@ttl_cache(900, maxsize=128)
def get_price_history(market, symbol, benchmark=False):
    ticker = BENCHMARKS[market][0] if benchmark else normalize_symbol(market, symbol)
    if market == 'US':
        ticker = ticker.replace('.', '-')
    try:
        data = yf.Ticker(ticker)
        frame = data.history(period='10y', interval='1d', auto_adjust=True, timeout=15)
        rows = _rows(frame)
        metadata = data.history_metadata or {}
        currency = metadata.get('currency')
    except HistoryError:
        raise
    except Exception as exc:
        raise HistoryError('Historical provider is unavailable') from exc
    return {'symbol': ticker, 'currency': currency, 'prices': rows,
            'provider': 'Yahoo Finance (unofficial)', 'adjusted': True,
            'retrieved_at': datetime.now(timezone.utc).isoformat(),
            'definition': 'Provider dividend/split-adjusted daily closes; approximate reinvested total returns before tax and costs'}


@ttl_cache(900, maxsize=12)
def get_fx_rate(base, quote):
    if base not in ('CAD', 'USD', 'INR') or quote not in ('CAD', 'USD', 'INR'):
        raise HistoryError('Currency conversion is unavailable')
    if base == quote:
        return {'rate': 1.0, 'base': base, 'quote': quote, 'as_of': None, 'provider': 'Same currency'}
    try:
        rows = _rows(yf.Ticker(f'{base}{quote}=X').history(period='5d', auto_adjust=False, timeout=12))
        latest = rows[-1]
        if (datetime.now(timezone.utc).date() - date.fromisoformat(latest['date'])).days > 4:
            raise HistoryError('Daily FX rate is stale')
        return {'rate': latest['close'], 'base': base, 'quote': quote,
                'as_of': latest['date'], 'provider': 'Yahoo Finance daily FX (unofficial)'}
    except HistoryError:
        raise
    except Exception as exc:
        raise HistoryError('Currency conversion provider is unavailable') from exc


def percentile(values, fraction):
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def historical_performance(history, years, benchmark=None, *, today=None):
    rows = history.get('prices') or []
    if len(rows) < 60:
        return {'status': 'insufficient', 'reason': 'At least 60 daily sessions are required', 'returns': [], 'chart': []}
    dates = [date.fromisoformat(row['date']) for row in rows]
    values = [finite_number(row.get('close')) for row in rows]
    if any(value is None or value <= 0 for value in values) or any(b <= a for a, b in zip(dates, dates[1:])):
        return {'status': 'insufficient', 'reason': 'Invalid or unordered historical prices', 'returns': [], 'chart': []}
    as_of = dates[-1]
    age = ((today or datetime.now(timezone.utc).date()) - as_of).days
    if age < 0 or age > 4:
        return {'status': 'insufficient', 'reason': 'Historical price series is stale or in the future', 'returns': [], 'chart': []}
    max_gap = max((b - a).days for a, b in zip(dates, dates[1:]))
    if max_gap > 10:
        return {'status': 'insufficient', 'reason': 'Historical sessions have gaps over ten days; risk estimates withheld', 'returns': [], 'chart': []}
    daily = [values[i] / values[i - 1] - 1 for i in range(1, len(values))]
    volatility = stdev(daily) * math.sqrt(252) * 100
    peak, drawdown = values[0], 0.0
    for value in values:
        peak = max(peak, value)
        drawdown = min(drawdown, value / peak - 1)
    span = (as_of - dates[0]).days / 365.25
    cagr = ((values[-1] / values[0]) ** (1 / span) - 1) * 100

    def period_return(days):
        target = as_of - timedelta(days=days)
        index = bisect_right(dates, target) - 1
        if index < 0 or (target - dates[index]).days > 7:
            return None
        return {'start': dates[index].isoformat(), 'end': as_of.isoformat(),
                'return_percent': round((values[-1] / values[index] - 1) * 100, 2)}
    returns = []
    for label, days in [('1 month', 30), ('3 months', 91), ('1 year', 365), ('3 years', 1096), ('5 years', 1826), ('10 years', 3652)]:
        item = period_return(days)
        returns.append({'period': label, **item} if item else {'period': label, 'return_percent': None})

    # Start once per month; overlapping holding periods are explicitly not independent trials.
    holding_days = round(years * 365.25)
    outcomes, month = [], None
    for index, start in enumerate(dates):
        if (start.year, start.month) == month:
            continue
        month = (start.year, start.month)
        target = start + timedelta(days=holding_days)
        end = bisect_left(dates, target)
        if end < len(dates) and (dates[end] - target).days <= 7:
            outcomes.append(values[end] / values[index] - 1)
    replay = {'status': 'insufficient', 'sample_count': len(outcomes), 'holding_years': years}
    if len(outcomes) >= 12:
        replay.update(status='available', downside_percent=round(percentile(outcomes, .10) * 100, 2),
                      median_percent=round(percentile(outcomes, .50) * 100, 2),
                      upside_percent=round(percentile(outcomes, .90) * 100, 2),
                      positive_windows_percent=round(sum(value > 0 for value in outcomes) / len(outcomes) * 100, 1),
                      worst_percent=round(min(outcomes) * 100, 2),
                      independent_periods_approx=int(span // years),
                      warning='Overlapping historical holding periods, not probabilities or a forecast. Future losses may exceed the historical worst.')
    chart_step = max(1, len(rows) // 150)
    chart = [{'date': rows[i]['date'], 'growth_of_100': round(values[i] / values[0] * 100, 2)} for i in range(0, len(rows), chart_step)]
    if chart[-1]['date'] != rows[-1]['date']:
        chart.append({'date': rows[-1]['date'], 'growth_of_100': round(values[-1] / values[0] * 100, 2)})
    result = {'status': 'available', 'currency': history.get('currency'), 'start': dates[0].isoformat(), 'as_of': as_of.isoformat(),
              'years_available': round(span, 2), 'session_count': len(rows), 'cagr_percent': round(cagr, 2),
              'annualized_volatility_percent': round(volatility, 2), 'max_drawdown_percent': round(drawdown * 100, 2),
              'returns': returns, 'rolling_history': replay, 'chart': chart, 'definition': history.get('definition'),
              'benchmark': None}
    if benchmark and benchmark.get('prices'):
        # Compare precisely the same available dates; never mix two different return windows.
        other = {row['date']: row['close'] for row in benchmark['prices']}
        common = [i for i, row in enumerate(rows) if row['date'] in other]
        if len(common) >= 60:
            first, last = common[0], common[-1]
            elapsed = (dates[last] - dates[first]).days / 365.25
            same_currency = bool(history.get('currency') and history.get('currency') == benchmark.get('currency'))
            if elapsed > 0 and same_currency:
                stock_rate = ((values[last] / values[first]) ** (1 / elapsed) - 1) * 100
                benchmark_rate = ((other[rows[last]['date']] / other[rows[first]['date']]) ** (1 / elapsed) - 1) * 100
                result['benchmark'] = {'symbol': benchmark['symbol'], 'start': rows[first]['date'], 'end': rows[last]['date'],
                                       'stock_cagr_percent': round(stock_rate, 2), 'benchmark_cagr_percent': round(benchmark_rate, 2),
                                       'excess_cagr_percentage_points': round(stock_rate - benchmark_rate, 2)}
    return result
