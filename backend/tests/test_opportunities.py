from copy import deepcopy
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

from app.market_setup import build_market_setup
from app.opportunities import build_opportunity
from app.price_validation import validate_market_quote
from app.web_research import canonical_source, research_valuation
from test_gain_valuation import gain_sample, gain_view, mock_web, review_payload


@pytest.fixture(autouse=True)
def source_pages(monkeypatch):
    from app import web_research
    text = f'{date.today().isoformat()} {(date.today() - timedelta(days=60)).isoformat()} Results reported. Results covered.'
    monkeypatch.setattr(web_research, 'fetch_source_documents', lambda sources: [
        {'url': source['url'], 'title': source['title'], 'text': text} for source in sources])


@pytest.fixture
def opportunity_sample(gain_sample):
    sample = gain_sample
    sample['profile'].update(amount=10000, currency='USD', risk='low')
    sample['quote']['current'] = 100
    sample['fx']['rate'] = 1
    sample['history'].update(max_drawdown_percent=-53, annualized_volatility_percent=42)
    dates = pd.bdate_range(end=date.today() - timedelta(days=1), periods=100)
    bars = [{'date': day.date().isoformat(), 'open': 80 + index * .2, 'close': 80 + index * .2,
             'high': 81 + index * .2, 'low': 79 + index * .2} for index, day in enumerate(dates)]
    bars[50]['high'] = 130  # Observed older price range, rather than an invented target.
    sample['raw'] = {'currency': 'USD', 'bars': bars,
                     'price_closes': [{'date': row['date'], 'close': row['close']} for row in bars]}
    return sample


def opportunity_view(sample, **options):
    view = gain_view(sample)
    view['company_website'] = 'https://issuer.test'
    view['market_setup'] = build_market_setup(sample['raw'], None, sample['quote'], view['preferences'],
                                               view['buy_assessment']['checks'], market='US')
    view['opportunity'] = build_opportunity(view, sample['raw'], **options)
    return view


def test_buy_setup_exists_even_when_long_term_earnings_and_default_stock_risk_fail(opportunity_sample):
    view = opportunity_view(opportunity_sample)
    assert view['buy_assessment']['verdict'] == 'NOT SUITABLE'
    assert not view['buy_assessment']['quantitative_candidate']
    result = view['opportunity']
    assert result['verdict'] == 'BUY SETUP'
    assert result['eligible']
    assert result['inputs']['loss_amount'] == 50  # Visible low-risk starting amount, not a forecast.
    assert result['plan']['target_price'] == 130
    assert result['context']
    assert result['news_review']['status'] == 'not_requested'


def test_only_explicit_stock_limits_are_binding(opportunity_sample):
    result = opportunity_view(opportunity_sample, explicit_stock_limits=['Risk profile'])['opportunity']
    assert not result['eligible']
    assert result['verdict'] == 'WAIT'
    opportunity_sample['history']['max_drawdown_percent'] = -10
    # Default volatility still fails; the user explicitly selected only the drawdown filter.
    result = opportunity_view(opportunity_sample, explicit_stock_limits=['Loss tolerance'])['opportunity']
    assert result['eligible']


def test_wait_identifies_a_specific_lower_entry_price_after_costs(opportunity_sample):
    opportunity_sample['quote']['current'] = 118
    view = opportunity_view(opportunity_sample)
    result = view['opportunity']
    assert result['verdict'] == 'WAIT FOR BETTER PRICE'
    assert result['plan']['buy_up_to'] < 118
    opportunity_sample['quote']['current'] = result['plan']['buy_up_to'] - .01
    assert opportunity_view(opportunity_sample)['opportunity']['verdict'] == 'BUY SETUP'


def test_money_risk_and_available_cash_bound_the_position_in_base_currency(opportunity_sample):
    opportunity_sample['fx']['rate'] = .72
    result = opportunity_view(opportunity_sample, loss_amount=100)['opportunity']
    plan = result['plan']
    assert 0 < plan['planned_loss'] <= 100
    assert plan['money_used'] <= 10000
    assert plan['money_used'] + plan['money_unallocated'] == pytest.approx(10000, abs=.01)
    assert plan['estimated_round_trip_cost'] > 0
    assert plan['potential_gain'] > 0
    assert plan['shares'] == int(plan['shares'])


def test_costs_can_turn_a_buy_setup_into_wait(opportunity_sample):
    options = {'planned_stop': 90, 'planned_target': 120}
    assert opportunity_view(opportunity_sample, round_trip_cost_percent=0, **options)['opportunity']['eligible']
    costly = opportunity_view(opportunity_sample, round_trip_cost_percent=10, **options)['opportunity']
    assert costly['verdict'] == 'WAIT FOR BETTER PRICE'
    assert costly['plan']['reward_risk'] < 1.5


def test_manual_unobserved_target_cannot_manufacture_a_buy_setup(opportunity_sample):
    result = opportunity_view(opportunity_sample, planned_target=10000)['opportunity']
    assert not result['eligible']
    assert result['verdict'] == 'WAIT'
    assert 'personal scenario' in result['reason']


def test_holding_period_changes_the_observed_target_and_review_key(opportunity_sample):
    month = opportunity_view(opportunity_sample, holding_weeks=4)['opportunity']
    quarter = opportunity_view(opportunity_sample, holding_weeks=12)['opportunity']
    assert month['key'] != quarter['key']
    assert month['plan']['target_price'] < quarter['plan']['target_price']
    assert month['verdict'] == 'WAIT FOR BETTER PRICE'


@pytest.mark.parametrize('options', [{'loss_amount': 100}, {'holding_weeks': 26}, {'min_reward_risk': 2}, {'round_trip_cost_percent': .5}])
def test_each_new_answer_invalidates_previous_news_review(opportunity_sample, options):
    assert opportunity_view(opportunity_sample)['opportunity']['key'] != opportunity_view(opportunity_sample, **options)['opportunity']['key']


@pytest.mark.parametrize('kind', ['old_quote', 'daily', 'missing_company', 'fx', 'market', 'bad_bars', 'tiny_risk'])
def test_no_actionable_buy_for_missing_or_conflicting_core_evidence(opportunity_sample, kind):
    if kind == 'old_quote': opportunity_sample['quote']['timestamp'] -= 3600
    if kind == 'daily': opportunity_sample['quote']['price_type'] = 'daily_bar'
    if kind == 'missing_company': opportunity_sample['fundamentals']['company'] = None
    if kind == 'fx': opportunity_sample['fx'] = None
    if kind == 'market': opportunity_sample['profile']['markets'] = ['CA']
    if kind == 'bad_bars': opportunity_sample['raw']['bars'][-1]['high'] = 1
    result = opportunity_view(opportunity_sample, **({'loss_amount': .01} if kind == 'tiny_risk' else {}))['opportunity']
    assert not result['eligible']
    assert result['verdict'] not in ('BUY SETUP', 'BUY CANDIDATE')


def combined_payload(stance='supports'):
    output = review_payload('NOT SUITABLE')
    output['opportunity_review'] = {'stance': stance, 'reason': 'Company evidence supports this separately risk-sized plan.',
                                    'events': deepcopy(output['events'])}
    for event in output['opportunity_review']['events']:
        event['supporting_quote'] = event['description']
    return output


def test_validated_news_promotes_the_weeks_plan_independently_of_long_term_verdict(monkeypatch, opportunity_sample):
    output = combined_payload()
    # Latest quarterly evidence need not be artificially newer than 30 days.
    output['opportunity_review']['events'] = output['opportunity_review']['events'][:1]
    output['opportunity_review']['events'][0]['event_date'] = (date.today() - timedelta(days=60)).isoformat()
    calls = []
    mock_web(monkeypatch, output, calls)
    result = research_valuation(opportunity_view(opportunity_sample))
    assert result['opportunity']['verdict'] == 'BUY CANDIDATE'
    assert result['opportunity']['news_review']['status'] == 'validated'
    assert result['buy_assessment']['verdict'] == 'NOT SUITABLE'
    assert calls[1]['text']['format']['name'] == 'opportunity_news'
    assert 'valuation' not in calls[1]['input']  # News facts cannot be invented from our own five-year calculations.


def test_presentation_and_tracking_url_differences_do_not_reject_valid_citations(monkeypatch, opportunity_sample):
    assert canonical_source('https://issuer.test/results?asPDF=1&utm_source=openai#section') == canonical_source('https://issuer.test/results')
    assert canonical_source('https://issuer.test/results?id=1') != canonical_source('https://issuer.test/results?id=2')
    output = combined_payload()
    output['opportunity_review']['events'][0]['source_url'] += '?asPDF=1&utm_source=openai'
    mock_web(monkeypatch, output)
    assert research_valuation(opportunity_view(opportunity_sample))['opportunity']['verdict'] == 'BUY CANDIDATE'


@pytest.mark.parametrize('kind', ['future', 'uncited', 'old', 'no_positive'])
def test_bad_news_evidence_keeps_buy_setup_unreviewed_instead_of_fake_candidate(monkeypatch, opportunity_sample, kind):
    output = combined_payload()
    event = output['opportunity_review']['events'][0]
    if kind == 'future': event['event_date'] = (date.today() + timedelta(days=1)).isoformat()
    if kind == 'uncited': event['source_url'] = 'https://invented.test/'
    if kind == 'old': event['event_date'] = (date.today() - timedelta(days=121)).isoformat()
    if kind == 'no_positive': event['impact'] = 'unclear'
    mock_web(monkeypatch, output)
    result = research_valuation(opportunity_view(opportunity_sample))['opportunity']
    assert result['verdict'] == 'BUY SETUP'
    assert result['news_review']['status'] in ('unavailable', 'limited')


def test_negative_validated_evidence_can_overrule_a_price_setup(monkeypatch, opportunity_sample):
    output = combined_payload('negative')
    output['opportunity_review']['events'][0]['impact'] = 'negative'
    mock_web(monkeypatch, output)
    assert research_valuation(opportunity_view(opportunity_sample))['opportunity']['verdict'] == 'AVOID'


@pytest.mark.parametrize('kind', ['invented_claim', 'date_absent_from_page', 'too_many_words'])
def test_news_quotes_and_dates_must_be_grounded_in_the_actual_page(monkeypatch, opportunity_sample, kind):
    output = combined_payload()
    event = output['opportunity_review']['events'][0]
    if kind == 'invented_claim': event['supporting_quote'] = 'Our own price calculation says future gains are certain'
    if kind == 'date_absent_from_page': event['event_date'] = (date.today() - timedelta(days=2)).isoformat()
    if kind == 'too_many_words': event['supporting_quote'] = 'a ' * 26
    mock_web(monkeypatch, output)
    result = research_valuation(opportunity_view(opportunity_sample))['opportunity']
    assert result['verdict'] == 'BUY SETUP'
    assert result['news_review']['status'] == 'unavailable'


def test_provisional_today_ohlc_inconsistency_does_not_block_completed_history(opportunity_sample):
    opportunity_sample['raw']['bars'].append({'date': date.today().isoformat(), 'open': 100, 'high': 90, 'low': 80, 'close': 95})
    assert opportunity_view(opportunity_sample)['opportunity']['eligible']


def test_source_fetch_rejects_private_networks_and_retains_visible_text(monkeypatch):
    from app import source_evidence
    monkeypatch.setattr(source_evidence.socket, 'getaddrinfo', lambda *args, **kw: [(2, 1, 6, '', ('127.0.0.1', 443))])
    assert not source_evidence.public_page_url('https://issuer.test/results')
    assert not source_evidence.public_page_url('https://issuer.test:bad/results')
    parser = source_evidence.PageText()
    parser.feed('<html><meta content="2026-10-21"><script>private script</script><p>Real earnings announcement</p></html>')
    text = ' '.join(parser.parts)
    assert 'Real earnings announcement' in text
    assert '2026-10-21' in text
    assert 'private script' not in text


def test_favorable_news_cannot_override_bad_entry_arithmetic(monkeypatch, opportunity_sample):
    output = combined_payload()
    opportunity_sample['quote']['current'] = 118
    mock_web(monkeypatch, output)
    result = research_valuation(opportunity_view(opportunity_sample))['opportunity']
    assert result['verdict'] == 'WAIT FOR BETTER PRICE'
    assert result['news_review']['status'] == 'validated'


@pytest.mark.parametrize('payload', [
    {'holding_weeks': 3}, {'holding_weeks': 27}, {'holding_weeks': 4.5},
    {'loss_amount': 0}, {'loss_amount': -1}, {'loss_amount': 6000},
    {'loss_amount': 50, 'risk_budget': 1, 'planned_stop': 18},
    {'min_reward_risk': .4}, {'min_reward_risk': 11}, {'round_trip_cost_percent': -1},
])
def test_invalid_beginner_answers_are_rejected_before_providers(client, payload):
    assert client.get('/api/valuation/US/TEST', params=payload).status_code == 422
    assert client.post('/api/valuation/US/TEST/research', json=payload).status_code == 422


@pytest.mark.parametrize('scope,decision', [('opportunity', 'BUY SETUP'), ('long_term', 'NOT SUITABLE')])
def test_simple_answers_are_forwarded_and_requested_decision_is_audited(client, monkeypatch, opportunity_sample, scope, decision):
    from app import valuation_service
    def snapshot(market, symbol, profile, **options):
        assert options == {'holding_weeks': 12, 'loss_amount': 100}
        return opportunity_view(opportunity_sample, **options)
    monkeypatch.setattr(valuation_service, 'valuation_snapshot', snapshot)
    response = client.post('/api/valuation/US/TEST/research', json={'holding_weeks': 12, 'loss_amount': 100, 'review_scope': scope})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['opportunity']['verdict'] == 'BUY SETUP'
    run = client.get('/api/analysis-history/US/TEST').json()[0]
    assert run['decision'] == decision
    assert run['snapshot']['review_scope'] == scope
    assert run['snapshot']['valuation']['opportunity']['inputs']['loss_amount'] == 100
