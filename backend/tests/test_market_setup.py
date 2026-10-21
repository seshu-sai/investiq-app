from copy import deepcopy
from datetime import datetime, timezone, timedelta

import pandas as pd
import pytest

from app.market_setup import build_market_setup, rsi
from app.position_plan import build_position_plan
from app.price_validation import validate_market_quote

NOW = datetime(2026, 10, 21, 16, tzinfo=timezone.utc)


@pytest.fixture
def market_sample():
    dates = pd.bdate_range(end='2026-10-20', periods=100)
    prices = [{'date': day.date().isoformat(), 'close': 100 + index / 2} for index, day in enumerate(dates)]
    return {'history': {'currency': 'USD', 'symbol': 'TEST', 'price_closes': prices, 'prices': deepcopy(prices)},
            'quote': {'current': 150, 'currency': 'USD', 'timestamp': NOW.timestamp() - 20,
                      'price_type': 'provider_quote', 'realtime_entitled': False},
            'preferences': {'markets': ['US'], 'assets': ['stocks'], 'max_quote_age_minutes': 15}}


def setup(sample, **kw):
    return build_market_setup(sample['history'], sample.get('benchmark'), sample['quote'],
                              sample['preferences'], kw.pop('checks', []), market='US', now=kw.pop('now', NOW), **kw)


def test_trends_are_descriptive_and_quote_can_change_alignment(market_sample):
    result = setup(market_sample)
    assert result['trend'] == 'SUPPORTIVE'
    assert result['label'] == 'SUPPORTIVE BUT EXTENDED'
    assert result['metrics']['rsi14'] == 100
    assert result['quote_fresh'] and not result['is_realtime']
    market_sample['quote']['current'] = 110
    changed = setup(market_sample)
    assert changed['trend'] == 'MIXED'
    assert changed['metrics']['distance_from_sma50_percent'] < 0
    assert changed['metrics']['momentum20_percent'] == result['metrics']['momentum20_percent']
    assert 'BUY' not in changed['label']


def test_provisional_today_bar_does_not_change_daily_indicators(market_sample):
    before = setup(market_sample)
    market_sample['history']['price_closes'].append({'date': '2026-10-21', 'close': 10000})
    after = setup(market_sample)
    assert before['metrics'] == after['metrics']
    assert after['as_of'] == '2026-10-20'


@pytest.mark.parametrize('kind', ['stale_quote', 'daily_bar', 'future_quote', 'missing_quote'])
def test_current_entry_context_requires_a_fresh_trade(market_sample, kind):
    if kind == 'stale_quote': market_sample['quote']['timestamp'] -= 3600
    if kind == 'daily_bar': market_sample['quote']['price_type'] = 'daily_bar'
    if kind == 'future_quote': market_sample['quote']['timestamp'] += 3600
    if kind == 'missing_quote': market_sample['quote']['timestamp'] = None
    result = setup(market_sample)
    assert result['status'] == 'quote_required'
    assert not result['quote_fresh']
    assert result['metrics']['sma50'] > 0


@pytest.mark.parametrize('kind', ['short', 'stale', 'future', 'gap', 'duplicate', 'nan', 'currency', 'missing'])
def test_bad_daily_history_withholds_trend_metrics(market_sample, kind):
    rows = market_sample['history']['price_closes']
    if kind == 'short': market_sample['history']['price_closes'] = rows[-50:]
    if kind == 'stale': market_sample['history']['price_closes'] = rows[:-10]
    if kind == 'future': rows[-1]['date'] = '2026-10-22'
    if kind == 'gap': del rows[40:55]
    if kind == 'duplicate': rows[-1]['date'] = rows[-2]['date']
    if kind == 'nan': rows[-1]['close'] = float('nan')
    if kind == 'currency': market_sample['history']['currency'] = 'CAD'
    if kind == 'missing': market_sample['history'].pop('price_closes')
    result = setup(market_sample)
    assert result['status'] == 'unavailable'
    assert not result['metrics']


def test_risk_conflicts_stay_visible_while_valuation_failures_are_separate(market_sample):
    checks = [{'label': 'Downside sensitivity', 'passed': False, 'detail': 'Scenario loss exceeds 1%'},
              {'label': 'Return goal', 'passed': False, 'detail': 'Scenario misses goal'}]
    assert setup(market_sample, checks=checks)['status'] == 'available'
    checks.append({'label': 'Risk profile', 'passed': False, 'detail': 'Volatility exceeds your limit'})
    result = setup(market_sample, checks=checks)
    assert result['status'] == 'risk_conflict'
    assert result['trend'] == 'SUPPORTIVE'
    assert result['risk_conflicts'] == ['Volatility exceeds your limit']
    market_sample['preferences']['markets'] = ['CA']
    assert setup(market_sample)['status'] == 'risk_conflict'


def test_benchmark_comparison_uses_same_recent_dates_and_currency(market_sample):
    other = deepcopy(market_sample['history'])
    other['symbol'] = 'SPY'
    for row in other['price_closes']: row['close'] = 100
    market_sample['benchmark'] = other
    result = setup(market_sample)
    relative = result['metrics']['relative_strength']
    assert relative['excess_return_points'] == result['metrics']['momentum60_percent']
    assert relative['end'] == result['as_of']
    other['price_closes'].pop()
    assert setup(market_sample)['metrics']['relative_strength'] is None
    assert setup(market_sample)['signals'][-1]['state'] == 'unavailable'


def test_rsi_flat_and_falling_series_have_defined_results():
    assert rsi([100] * 100) == 50
    assert rsi(list(range(100, 0, -1))) == 0


def test_daily_bar_cutoff_uses_exchange_date(market_sample):
    # UTC Wednesday, still Tuesday in New York: Tuesday's bar can be provisional.
    now = NOW.replace(hour=1)
    result = setup(market_sample, now=now)
    assert result['as_of'] == '2026-10-19'


def test_position_size_distinguishes_one_percent_budget_risk_from_stock_loss(market_sample):
    market_sample['quote']['current'] = 20
    quote = validate_market_quote(market_sample['quote'], now=NOW)
    plan = build_position_plan(quote, 5000, .75, risk_budget=1, planned_stop=18, planned_target=25)
    assert plan['status'] == 'calculated'
    assert plan['shares'] == 18
    assert plan['planned_loss'] == 48
    assert plan['planned_loss_percent'] <= 1
    assert plan['price_to_stop_percent'] == 10
    assert plan['target_gain'] == 120
    assert plan['reward_to_risk'] == 2.5
    assert plan['position_value'] == 480


def test_position_size_never_exceeds_cash_and_handles_zero_whole_shares(market_sample):
    quote = validate_market_quote(market_sample['quote'], now=NOW)
    plan = build_position_plan(quote, 1000, 1, risk_budget=100, planned_stop=149)
    assert plan['shares'] == 6
    assert plan['position_value'] <= 1000
    tiny = build_position_plan(quote, 100, 1, risk_budget=1, planned_stop=140)
    assert tiny['shares'] == 0


@pytest.mark.parametrize('kind', ['stale', 'daily', 'fx', 'stop', 'target'])
def test_position_plan_withholds_amounts_for_bad_quotes_fx_or_levels(market_sample, kind):
    if kind == 'stale': market_sample['quote']['timestamp'] -= 3600
    if kind == 'daily': market_sample['quote']['price_type'] = 'daily_bar'
    quote = validate_market_quote(market_sample['quote'], now=NOW)
    plan = build_position_plan(quote, 5000, None if kind == 'fx' else 1, risk_budget=1,
                               planned_stop=151 if kind == 'stop' else 140,
                               planned_target=149 if kind == 'target' else 160)
    assert plan['status'] in ('unavailable', 'invalid_levels')
    assert 'shares' not in plan


@pytest.mark.parametrize('payload', [
    {'risk_budget': 1}, {'planned_stop': 18}, {'planned_target': 25},
    {'risk_budget': 0, 'planned_stop': 18}, {'risk_budget': 101, 'planned_stop': 18},
    {'risk_budget': True, 'planned_stop': 18}, {'risk_budget': 1, 'planned_stop': -1},
    {'risk_budget': 1, 'planned_stop': 18, 'planned_target': 'nan'},
])
def test_api_rejects_incomplete_or_invalid_position_plans_before_network(client, payload):
    assert client.get('/api/valuation/US/TEST', params=payload).status_code == 422
    assert client.post('/api/valuation/US/TEST/research', json=payload).status_code == 422


def test_history_keeps_dividend_adjusted_returns_separate_from_price_trends(monkeypatch):
    from app import price_history
    dates = pd.bdate_range(end='2026-10-20', periods=100)
    frame = pd.DataFrame({'Close': [200] * 100, 'Adj Close': [100] * 100}, index=dates)
    class Ticker:
        history_metadata = {'currency': 'USD'}
        def history(self, **kw):
            assert kw['auto_adjust'] is False
            return frame
    monkeypatch.setattr(price_history.yf, 'Ticker', lambda symbol: Ticker())
    price_history.get_price_history.cache_clear()
    try:
        data = price_history.get_price_history('US', 'TEST')
        assert data['prices'][-1]['close'] == 100
        assert data['price_closes'][-1]['close'] == 200
    finally:
        price_history.get_price_history.cache_clear()


def test_valuation_service_can_show_recent_trend_without_long_term_earnings(monkeypatch, sample):
    from app import valuation_service
    now = datetime.now(timezone.utc)
    dates = pd.bdate_range(end=now.date() - timedelta(days=1), periods=100)
    rows = [{'date': day.date().isoformat(), 'close': 100 + index / 2} for index, day in enumerate(dates)]
    sample['profile'].update(amount=5000, risk='high')
    sample['quote']['current'] = 150
    snapshot = {'market':'US', 'symbol':'TEST', 'fundamentals':{}, 'historical_financials':{},
                'quote':sample['quote'], 'warnings':[], 'sources':[{'title':'Fixture'}]}
    monkeypatch.setattr(valuation_service, 'collect_snapshot', lambda *args: deepcopy(snapshot))
    monkeypatch.setattr(valuation_service, 'get_price_history', lambda *args: {'currency':'USD', 'symbol':'TEST', 'prices':rows, 'price_closes':rows})
    monkeypatch.setattr(valuation_service, 'get_fx_rate', lambda *args: {'rate':1})
    result = valuation_service.valuation_snapshot('US', 'TEST', sample['profile'], max_downside=1)
    assert result['buy_assessment']['verdict'] == 'INSUFFICIENT DATA'
    assert result['market_setup']['status'] == 'available'
    assert result['market_setup']['trend'] == 'SUPPORTIVE'
