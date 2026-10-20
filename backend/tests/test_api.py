from fastapi.testclient import TestClient
from app.main import app

def test_health():
    with TestClient(app) as client:
        assert client.get('/api/health').json()['status'] == 'ok'

def test_research_never_fabricates():
    with TestClient(app) as client:
        data = client.get('/api/research/US/NVDA').json()
        assert data['status'] == 'not_connected'
        assert data['forecasts'] == []
