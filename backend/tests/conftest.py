from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def no_credentials(monkeypatch):
    for name in ('OPENAI_API_KEY', 'FINNHUB_API_KEY', 'SEC_USER_AGENT'):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def sample():
    today = date.today()
    latest_year = today.year - (1 if today.month <= 6 else 0)
    history = []
    for offset, revenue in enumerate((100, 150, 180)):
        end = date(latest_year - 2 + offset, 6, 30)
        filed = min(today, end + timedelta(days=30)).isoformat()
        history.append({
            'fiscal_year_end': end.isoformat(), 'revenue': revenue,
            'revenue_filed': filed, 'revenue_accession': f'filing-{offset}',
            'net_income': 10 + offset, 'operating_cash_flow': 25 + offset * 5,
            'productive_asset_purchases': 5,
            'cash_after_productive_asset_purchases': 20 + offset * 5,
            'operating_cash_flow_filed': filed, 'productive_asset_purchases_filed': filed,
            'operating_cash_flow_accession': f'filing-{offset}',
            'productive_asset_purchases_accession': f'filing-{offset}',
        })
    return {
        'fundamentals': {'symbol': 'TEST', 'company': 'Test Company', 'currency': 'USD',
                         'trailing_eps': 2, 'trailing_pe': 10},
        'quote': {'current': 120, 'timestamp': datetime.now(timezone.utc).timestamp() - 20,
                  'currency': 'USD', 'price_type': 'provider_quote', 'realtime_entitled': False},
        'financials': {'source': 'SEC EDGAR companyfacts', 'period_type': 'annual', 'history': history,
                       'balance_sheet': {'shares_outstanding': {'value': 10, 'as_of': history[-1]['fiscal_year_end'],
                                                               'filed': history[-1]['revenue_filed']}}},
        'profile': {'risk': 'medium', 'horizon': '3-5', 'currency': 'USD', 'markets': ['US'], 'assets': ['stocks']},
    }


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app import main
    engine = create_engine(f'sqlite:///{tmp_path / "test.db"}', connect_args={'check_same_thread': False})
    monkeypatch.setattr(main, 'engine', engine)
    monkeypatch.setattr(main, 'Session', sessionmaker(bind=engine))
    with TestClient(main.app) as test_client:
        yield test_client
    engine.dispose()
