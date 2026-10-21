from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

import pytest

from app.advisor import assess_evidence, fallback_decision
from app.ai_research import analyze_stock_with_ai
from app.price_validation import validate_market_quote


def assess(sample, **kwargs):
    return assess_evidence('US', 'TEST', sample['fundamentals'], sample['financials'],
                           sample['quote'], sample['profile'], **kwargs)


@pytest.mark.parametrize('value', [True, float('nan'), float('inf'), 10 ** 1000, -1, 0, '100', None])
def test_invalid_market_price(value, sample):
    sample['quote']['current'] = value
    assert validate_market_quote(sample['quote'])['valid'] is False


@pytest.mark.parametrize('timestamp', [True, float('inf'), 1e300, 0, None, 'today'])
def test_invalid_timestamp(timestamp, sample):
    sample['quote']['timestamp'] = timestamp
    assert validate_market_quote(sample['quote'])['valid'] is False


def test_closure_is_usable_but_not_realtime(sample):
    sample['quote']['timestamp'] -= 2 * 86400
    result = validate_market_quote(sample['quote'])
    assert result['valid'] and not result['is_realtime']
    assert result['status'] == 'delayed_or_closed'


def test_future_timestamp_is_invalid(sample):
    sample['quote']['timestamp'] = datetime.now(timezone.utc).timestamp() + 600
    assert not validate_market_quote(sample['quote'])['valid']


def test_recent_quote_requires_entitlement(sample):
    assert not validate_market_quote(sample['quote'])['is_realtime']
    sample['quote']['realtime_entitled'] = True
    assert validate_market_quote(sample['quote'])['is_realtime']
    sample['quote']['price_type'] = 'daily_bar'
    assert not validate_market_quote(sample['quote'])['is_realtime']


def test_growth_and_valuation_are_separate(sample):
    result = assess(sample)
    assert result['metrics']['revenue_growth_trend'] == 'slowing'
    assert result['metrics']['annual_revenue_growth_rates_percent'] == [50, 20]
    assert result['metrics']['cash_flow_trend'] == 'increasing'
    assert result['metrics']['trailing_pe_at_quote'] == 60
    assert result['buy_eligible'] is False
    assert fallback_decision(result)['decision'] == 'WAIT'


def test_hold_requires_known_ownership_and_profile_fit(sample):
    assert 'HOLD' not in assess(sample)['allowed_decisions']
    assert 'HOLD' in assess(sample, owns_position=True)['allowed_decisions']
    sample['profile']['horizon'] = '0-1'
    assert 'HOLD' not in assess(sample, owns_position=True)['allowed_decisions']


def test_missing_and_mismatched_evidence(sample):
    sample['fundamentals']['currency'] = 'CAD'
    assert assess(sample)['metrics']['trailing_pe_at_quote'] is None
    assert assess(sample)['allowed_decisions'] == ['INSUFFICIENT DATA']


def test_missing_year_is_not_annual_growth(sample):
    sample['financials']['history'][0]['fiscal_year_end'] = '2010-06-30'
    result = assess(sample)
    assert result['metrics']['annual_revenue_growth_rates_percent'] == [20]
    assert result['metrics']['revenue_growth_trend'] == 'insufficient data'


def test_missing_cash_year_does_not_invent_trend(sample):
    sample['financials']['history'][1]['cash_after_productive_asset_purchases'] = None
    assert assess(sample)['metrics']['cash_flow_trend'] == 'insufficient data'


def ai_output(sample, **overrides):
    return {**fallback_decision(assess(sample)), 'evidence_refs': [assess(sample)['evidence'][-1]['id']], **overrides}


def mock_ai(monkeypatch, output, status='completed'):
    from app import ai_research
    monkeypatch.setenv('OPENAI_API_KEY', 'test-placeholder')
    class FakeClient:
        def __init__(self, **kwargs):
            self.responses = self
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def create(self, **kwargs):
            assert kwargs['store'] is False
            assert kwargs['text']['format']['strict'] is True
            return SimpleNamespace(status=status, output_text=json.dumps(output))
    monkeypatch.setattr(ai_research, 'OpenAI', FakeClient)


def run_ai(sample):
    return analyze_stock_with_ai('US', 'TEST', sample['fundamentals'], {}, [], sample['quote'],
                                 sample['financials'], sample['profile'])


@pytest.mark.parametrize('overrides', [
    {'decision': 'BUY', 'headline': 'Buy immediately'},
    {'decision': 'HOLD'},
    {'target_price': 1000},
    {'entry_price': 80},
    {'evidence_refs': ['invented-evidence']},
    {'evidence_refs': []},
    {'decision': 'GUARANTEED PROFITS'},
    {'unexpected': 'field'},
])
def test_unsupported_ai_output_replaces_entire_narrative(monkeypatch, sample, overrides):
    mock_ai(monkeypatch, ai_output(sample, **overrides))
    result = run_ai(sample)
    assert result['decision'] == 'WAIT'
    assert result['analysis_mode'] == 'rules'
    assert result['headline'] != 'Buy immediately'
    assert result['entry_price'] is None and result['target_price'] is None


def test_completed_grounded_ai_output_preserves_server_dates(monkeypatch, sample):
    mock_ai(monkeypatch, ai_output(sample, data_as_of='1900-01-01', time_horizon='100 years'))
    result = run_ai(sample)
    assert result['analysis_mode'] == 'ai'
    assert result['time_horizon'] == '3-5 years'
    assert result['data_as_of'] == validate_market_quote(sample['quote'])['timestamp']


def test_incomplete_response_falls_back(monkeypatch, sample):
    mock_ai(monkeypatch, ai_output(sample), status='incomplete')
    assert run_ai(sample)['analysis_mode'] == 'rules'


def test_missing_essential_data_skips_ai(monkeypatch, sample):
    from app import ai_research
    monkeypatch.setenv('OPENAI_API_KEY', 'test-placeholder')
    monkeypatch.setattr(ai_research, 'OpenAI', lambda **kw: pytest.fail('AI must not be called'))
    sample['quote']['timestamp'] -= 10 * 86400
    assert run_ai(sample)['decision'] == 'INSUFFICIENT DATA'


def test_fx_warning_is_not_an_ownership_or_horizon_conflict(sample):
    sample['profile']['currency'] = 'CAD'
    result = assess(sample, owns_position=True)
    assert result['investor_fit']['warnings']
    assert 'HOLD' in result['allowed_decisions']


def test_loss_and_earnings_decline_are_visible(sample):
    sample['financials']['history'][-1]['net_income'] = -10
    result = assess(sample)
    assert result['metrics']['latest_annual_net_margin_percent'] < 0
    assert result['metrics']['latest_annual_net_income_growth_percent'] < 0
    assert any('net loss' in risk for risk in result['risk_flags'])


def test_annual_gap_forces_insufficient_evidence(sample):
    sample['financials']['history'][0]['fiscal_year_end'] = '2010-06-30'
    result = assess(sample)
    assert result['data_quality'] == 'insufficient'
    assert result['metrics']['cash_flow_trend'] == 'insufficient data'
