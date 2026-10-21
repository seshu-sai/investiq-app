from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import json
from types import SimpleNamespace

import pandas as pd
import pytest

from app.gain_valuation import build_gain_view, earnings_scenarios
from app.price_history import historical_performance, get_fx_rate
from app.web_research import cited_output, research_valuation


@pytest.fixture
def gain_sample(sample):
    sample['profile'].update(amount='5000', currency='CAD', risk='medium', horizon='5+')
    sample['quote']['current'] = 20
    for index, row in enumerate(sample['financials']['history']):
        row['diluted_eps'] = 1 * 2 ** index
    sample['snapshot'] = {'market': 'US', 'symbol': 'TEST', 'fundamentals': sample['fundamentals'],
                          'historical_financials': sample['financials'], 'quote': sample['quote'], 'sources': [], 'warnings': []}
    sample['history'] = {'status': 'available', 'years_available': 10, 'annualized_volatility_percent': 20,
                         'max_drawdown_percent': -20, 'benchmark': {'excess_cagr_percentage_points': 3},
                         'rolling_history': {'status': 'available', 'downside_percent': -10, 'median_percent': 40, 'upside_percent': 80}}
    sample['fx'] = {'rate': .75, 'base': 'CAD', 'quote': 'USD', 'as_of': date.today().isoformat()}
    return sample


def gain_view(sample, **options):
    return build_gain_view(sample['snapshot'], sample['history'], sample['profile'], sample['fx'], **options)


def test_budget_conversion_and_scenarios_are_in_saved_currency(gain_sample):
    result = gain_view(gain_sample, annual_goal=8, max_loss=30)
    assert result['budget']['amount_in_stock_currency'] == 3750
    assert result['budget']['hypothetical_fractional_shares'] == 187.5
    base = result['valuation']['scenarios'][1]
    assert base['gain_in_base_currency'] == pytest.approx(5000 * base['total_return_percent'] / 100, abs=.01)
    assert base['ending_value_in_base_currency'] == pytest.approx(5000 + base['gain_in_base_currency'])
    assert result['buy_assessment']['quantitative_candidate']
    assert result['buy_assessment']['verdict'] == 'WAIT'  # Requires web review; never an automatic BUY.


def test_no_cash_gains_when_fx_fails(gain_sample):
    gain_sample['fx'] = None
    result = gain_view(gain_sample)
    assert result['valuation']['scenarios'][1]['total_return_percent'] is not None
    assert result['valuation']['scenarios'][1]['gain_in_base_currency'] is None
    assert not result['buy_assessment']['quantitative_candidate']


def test_low_risk_profile_blocks_large_historical_losses(gain_sample):
    gain_sample['profile']['risk'] = 'low'
    result = gain_view(gain_sample)
    assert result['buy_assessment']['verdict'] == 'NOT SUITABLE'
    assert result['preferences']['modeled_years'] == 5


def test_current_position_gain_uses_cost_not_historical_returns(gain_sample):
    result = gain_view(gain_sample, cost_basis=25, shares=10)
    assert result['unrealized_gain']['gain'] == -50
    assert result['unrealized_gain']['return_percent'] == -20
    assert result['unrealized_gain']['currency'] == 'USD'


def test_intraday_freshness_required_for_candidate(gain_sample):
    gain_sample['quote']['timestamp'] -= 3600
    result = gain_view(gain_sample)
    assert not result['buy_assessment']['quantitative_candidate']
    assert result['valuation']['status'] == 'illustrative'


def test_daily_bar_never_passes_buy_candidate(gain_sample):
    gain_sample['quote']['price_type'] = 'daily_bar'
    assert not gain_view(gain_sample)['buy_assessment']['quantitative_candidate']


def test_unverified_eps_history_withholds_earnings_projection(gain_sample):
    gain_sample['financials']['history'][1]['diluted_eps'] = None
    result = gain_view(gain_sample)
    assert result['valuation']['status'] == 'unavailable'
    assert not result['buy_assessment']['quantitative_candidate']


def test_preference_changes_affect_horizon_and_hurdles(gain_sample):
    gain_sample['profile']['horizon'] = '1-3'
    result = gain_view(gain_sample, annual_goal=25, max_loss=10)
    assert result['preferences']['modeled_years'] == 2
    assert result['preferences']['annual_return_goal_percent'] == 25
    assert result['preferences']['max_loss_percent'] == 10
    assert not result['buy_assessment']['quantitative_candidate']


def test_higher_return_hurdle_lowers_conditional_entry(gain_sample):
    low = gain_view(gain_sample, annual_goal=5)
    high = gain_view(gain_sample, annual_goal=15)
    assert high['valuation']['goal_entry_price'] < low['valuation']['goal_entry_price']


def price_series(years=8):
    end = pd.Timestamp(datetime.now(timezone.utc).date())
    dates = pd.bdate_range(end=end, periods=round(252 * years))
    return {'currency': 'USD', 'symbol': 'TEST', 'prices': [
        {'date': day.strftime('%Y-%m-%d'), 'close': 100 * (1.0003 ** index)} for index, day in enumerate(dates)]}


def test_historical_windows_are_dated_not_forecast_probabilities():
    series = price_series()
    result = historical_performance(series, 5, series)
    assert result['status'] == 'available'
    assert result['max_drawdown_percent'] == 0
    assert result['rolling_history']['sample_count'] >= 12
    assert result['rolling_history']['positive_windows_percent'] == 100
    assert result['rolling_history']['independent_periods_approx'] < result['rolling_history']['sample_count']
    assert 'not probabilities' in result['rolling_history']['warning']
    assert result['benchmark']['excess_cagr_percentage_points'] == 0
    assert result['chart'][0]['growth_of_100'] == 100


def test_historical_drawdown_is_peak_to_trough():
    series = price_series(1)
    for row in series['prices']:
        row['close'] = 100
    series['prices'][120]['close'] = 50
    assert historical_performance(series, 1)['max_drawdown_percent'] == -50


def test_missing_price_sessions_do_not_create_false_risk_statistics():
    series = price_series()
    del series['prices'][80:100]
    assert historical_performance(series, 5)['status'] == 'insufficient'


def test_stale_history_is_not_used_for_current_buy_screen():
    series = price_series()
    result = historical_performance(series, 5, today=date.today() + timedelta(days=10))
    assert result['status'] == 'insufficient'


def test_fx_same_currency_never_contacts_provider(monkeypatch):
    import app.price_history as prices
    monkeypatch.setattr(prices.yf, 'Ticker', lambda *a: pytest.fail('No FX provider request required'))
    assert get_fx_rate('CAD', 'CAD')['rate'] == 1


class SearchResponse:
    status = 'completed'
    def model_dump(self):
        return {'status': 'completed', 'output': [
            {'type': 'web_search_call', 'status': 'completed'},
            {'type': 'message', 'content': [{'type': 'output_text', 'text': 'Results [a] risks [b]', 'annotations': [
                {'type': 'url_citation', 'start_index': 8, 'end_index': 11, 'url': 'https://issuer.test/results', 'title': 'Issuer'},
                {'type': 'url_citation', 'start_index': 18, 'end_index': 21, 'url': 'https://news.test/report', 'title': 'News'}]}]},
        ]}


def review_payload(verdict='WAIT'):
    return {'verdict': verdict, 'reason': 'Review the assumptions and current evidence.', 'bull_case': 'Reported sales improved.',
            'bear_case': 'Valuation can compress.', 'next_step': 'Review the primary source.', 'events': [
                {'event_date': date.today().isoformat(), 'description': 'Results reported', 'impact': 'positive', 'source_url': 'https://issuer.test/results'},
                {'event_date': date.today().isoformat(), 'description': 'Results covered', 'impact': 'unclear', 'source_url': 'https://news.test/report'}]}


def mock_web(monkeypatch, output):
    from app import web_research
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    class Client:
        def __init__(self, **kw): self.responses = self
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def create(self, **kw):
            assert kw['store'] is False
            if 'tools' in kw:
                assert kw['tools'] == [{'type': 'web_search'}]
                assert kw['tool_choice'] == 'required'
                return SearchResponse()
            return SimpleNamespace(status='completed', output_text=json.dumps(output))
    monkeypatch.setattr(web_research, 'OpenAI', Client)


def test_web_citations_remain_clickable():
    result = cited_output(SearchResponse())
    assert len(result['sources']) == 2
    assert [row['url'] for row in result['segments'] if row['url']] == ['https://issuer.test/results', 'https://news.test/report']


def test_search_cannot_claim_success_without_tool_execution():
    class NoSearch(SearchResponse):
        def model_dump(self):
            result = super().model_dump()
            result['output'] = result['output'][1:]
            return result
    with pytest.raises(ValueError): cited_output(NoSearch())


def test_unconfigured_web_keeps_quantitative_view(gain_sample):
    result = research_valuation(gain_view(gain_sample))
    assert result['web_research']['status'] == 'not_configured'
    assert result['valuation']['scenarios']


def test_no_web_output_can_override_risk_conflict(monkeypatch, gain_sample):
    gain_sample['profile']['risk'] = 'low'
    mock_web(monkeypatch, review_payload('BUY CANDIDATE'))
    result = research_valuation(gain_view(gain_sample))
    assert result['buy_assessment']['verdict'] == 'NOT SUITABLE'


def test_buy_candidate_requires_two_domains_and_recent_event(monkeypatch, gain_sample):
    mock_web(monkeypatch, review_payload('BUY CANDIDATE'))
    result = research_valuation(gain_view(gain_sample))
    assert result['buy_assessment']['verdict'] == 'BUY CANDIDATE'
    assert not result['buy_assessment']['research_required']


@pytest.mark.parametrize('kind', ['future', 'uncited', 'old', 'no_negative'])
def test_bad_web_evidence_keeps_original_verdict(monkeypatch, gain_sample, kind):
    output = review_payload('AVOID')
    if kind == 'future': output['events'][0]['event_date'] = (date.today() + timedelta(days=1)).isoformat()
    if kind == 'uncited': output['events'][0]['source_url'] = 'https://invented.test/'
    if kind == 'old': output['events'][0]['event_date'] = '2000-01-01'
    mock_web(monkeypatch, output)
    assert research_valuation(gain_view(gain_sample))['buy_assessment']['verdict'] == 'WAIT'


def test_one_source_cannot_justify_a_buy_candidate(monkeypatch, gain_sample):
    output = review_payload('BUY CANDIDATE')
    output['events'] = output['events'][:1]
    mock_web(monkeypatch, output)
    assert research_valuation(gain_view(gain_sample))['buy_assessment']['verdict'] == 'WAIT'


def test_api_valuation_uses_saved_preferences_without_mutating_them(client, monkeypatch, gain_sample):
    from app import valuation_service
    def snapshot(market, symbol, profile, **options):
        assert market == 'CA' and symbol == 'TEST.V'
        sample = deepcopy(gain_sample)
        sample['snapshot'].update(market=market, symbol=symbol)
        return build_gain_view(sample['snapshot'], sample['history'], profile, sample['fx'], **options)
    monkeypatch.setattr(valuation_service, 'valuation_snapshot', snapshot)
    response = client.get('/api/valuation/CA/TEST.V?amount=2000&annual_goal=12&max_loss=20&cost_basis=10&shares=5')
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['budget']['amount'] == 2000
    assert body['preferences']['annual_return_goal_percent'] == 12
    assert body['unrealized_gain']['gain'] == 50
    assert client.get('/api/settings').json()['amount'] == '5000'


@pytest.mark.parametrize('query', ['amount=-1', 'annual_goal=0', 'max_loss=101', 'cost_basis=10', 'shares=5', 'cost_basis=nan&shares=1'])
def test_bad_valuation_inputs_are_rejected_before_network(client, query):
    assert client.get(f'/api/valuation/US/TEST?{query}').status_code == 422


def test_manual_web_research_is_audited(client, monkeypatch, gain_sample):
    from app import valuation_service
    monkeypatch.setattr(valuation_service, 'valuation_snapshot', lambda *args, **kw: gain_view(gain_sample))
    response = client.post('/api/valuation/US/TEST/research', json={})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['web_research']['status'] == 'not_configured'
    runs = client.get('/api/analysis-history/US/TEST').json()
    assert runs[0]['id'] == body['analysis_id']
    assert runs[0]['snapshot']['valuation']['budget']['amount'] == 5000


def test_markdown_source_annotations_use_readable_inline_labels():
    class MarkdownResponse(SearchResponse):
        def model_dump(self):
            label = '([issuer.test](https://issuer.test/results))'
            return {'status': 'completed', 'output': [
                {'type': 'web_search_call', 'status': 'completed'},
                {'type': 'message', 'content': [{'type': 'output_text', 'text': label, 'annotations': [
                    {'type': 'url_citation', 'start_index': 0, 'end_index': len(label), 'url': 'https://issuer.test/results', 'title': 'Quarterly results'}]}]}]}
    result = cited_output(MarkdownResponse())
    link = next(row for row in result['segments'] if row['url'])
    assert link['text'].strip() == '[Quarterly results]'
    assert link['url'] == 'https://issuer.test/results'


def test_web_payload_rejects_boolean_amount_before_providers(client):
    assert client.post('/api/valuation/US/TEST/research', json={'amount': True}).status_code == 422
