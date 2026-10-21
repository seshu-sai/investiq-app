from datetime import datetime, timezone

import pytest


def mock_providers(monkeypatch, sample):
    from app import research_service as service
    monkeypatch.setattr(service, 'get_fundamentals', lambda *args: sample['fundamentals'])
    monkeypatch.setattr(service, 'get_research', lambda *args: {'quote': sample['quote'], 'sources': []})
    monkeypatch.setattr(service, 'financial_history', lambda *args: (sample['financials'], []))


def test_health(client):
    response = client.get('/api/health')
    assert response.json()['status'] == 'ok'
    assert response.headers['Cache-Control'] == 'no-store'


def test_research_without_credentials_is_explicit(client):
    response = client.get('/api/research/US/NVDA')
    assert response.status_code == 503
    assert 'not configured' in response.json()['detail']


@pytest.mark.parametrize('endpoint', ['research', 'analysis', 'ai-analysis', 'valuation', 'analysis-history'])
@pytest.mark.parametrize('path', ['US/INVALID!', 'XX/TEST', 'US/SHOP.TO'])
def test_input_validation_before_providers(client, endpoint, path):
    assert client.get(f'/api/{endpoint}/{path}').status_code == 422


def test_trajectory_uses_provider_price(client, monkeypatch, sample):
    mock_providers(monkeypatch, sample)
    result = client.get('/api/analysis/US/TEST').json()
    assert result['trajectory']['current_price'] == 120  # EPS * reported P/E would incorrectly be 20.
    assert result['trajectory']['current_pe'] == 60
    assert result['trajectory']['assessment'] == 'Hypothetical sensitivity analysis'


def test_no_synthetic_price_on_outage(client, monkeypatch, sample):
    from app import research_service as service
    mock_providers(monkeypatch, sample)
    def unavailable(*args):
        raise RuntimeError('provider down')
    monkeypatch.setattr(service, 'get_research', unavailable)
    result = client.get('/api/analysis/US/TEST').json()
    assert result['quote'] is None
    assert result['trajectory']['scenarios'] == []
    assert result['fundamentals']['company'] == 'Test Company'


def test_saved_profile_and_audit_snapshot(client, monkeypatch, sample):
    mock_providers(monkeypatch, sample)
    response = client.post('/api/settings', json={**sample['profile'], 'risk': 'low', 'horizon': '0-1'})
    assert response.status_code == 200
    response = client.get('/api/ai-analysis/US/TEST?owns_position=true')
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['ai_summary']['decision'] == 'WAIT'
    assert result['ai_summary']['analysis_mode'] == 'rules'
    assert result['ai_summary']['time_horizon'] == 'under 1 year'
    assert result['assessment']['investor_fit']['owns_position'] is True
    assert result['assessment']['investor_fit']['warnings']
    runs = client.get('/api/analysis-history/US/TEST').json()
    assert runs[0]['id'] == result['analysis_id']
    assert runs[0]['snapshot']['profile']['risk'] == 'low'
    assert runs[0]['snapshot']['result']['quote']['current'] == 120


def test_stale_quote_withholds_decision(client, monkeypatch, sample):
    sample['quote']['timestamp'] = datetime.now(timezone.utc).timestamp() - 5 * 86400
    mock_providers(monkeypatch, sample)
    result = client.get('/api/ai-analysis/US/TEST').json()
    assert result['ai_summary']['decision'] == 'INSUFFICIENT DATA'
    assert result['ai_summary']['entry_price'] is None
    assert result['assessment']['quote']['status'] == 'stale'


def test_watchlist_normalizes_venture_suffix_and_deduplicates(client):
    first = client.post('/api/watchlist', json={'market': 'CA', 'symbol': 'abc.v'}).json()
    second = client.post('/api/watchlist', json={'market': 'CA', 'symbol': 'ABC.V'}).json()
    assert first == second
    assert first['symbol'] == 'ABC.V'
    assert len(client.get('/api/watchlist').json()) == 1


def test_invalid_profile_is_rejected(client):
    assert client.post('/api/settings', json={'markets': ['XX']}).status_code == 422
    assert client.post('/api/settings', json={'amount': -1}).status_code == 422
    assert client.post('/api/settings', json={'risk': 'guaranteed'}).status_code == 422
