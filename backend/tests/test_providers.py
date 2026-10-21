from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pandas as pd
import pytest

from app import finnhub, fundamentals, international, sec_filings
from app.data_utils import normalize_symbol, safe_url, ttl_cache


@pytest.fixture(autouse=True)
def clear_provider_cache():
    cached = [finnhub._quote, finnhub._news, fundamentals.get_fundamentals,
              fundamentals.get_historical_financials, international.get_international_research,
              sec_filings.get_sec_annual_financials, sec_filings.lookup_sec_cik, sec_filings._ticker_directory]
    for function in cached:
        function.cache_clear()
    yield
    for function in cached:
        function.cache_clear()


def test_news_failure_does_not_discard_quote(monkeypatch):
    monkeypatch.setattr(finnhub, '_quote', lambda *args: {'current': 10, 'currency': 'USD', 'timestamp': 1})
    def unavailable(*args):
        raise finnhub.FinnhubError('news unavailable')
    monkeypatch.setattr(finnhub, '_news', unavailable)
    result = finnhub.get_research('TEST')
    assert result['quote']['current'] == 10
    assert result['sources'] == [] and result['warnings']


def test_news_sorts_and_rejects_unsafe_future_and_duplicate_links(monkeypatch):
    now = datetime.now(timezone.utc).timestamp()
    records = [
        {'url': 'https://example.com/old', 'datetime': now - 100},
        {'url': 'javascript:alert(1)', 'datetime': now},
        {'url': 'https://example.com/future', 'datetime': now + 3600},
        {'url': 'https://example.com/new', 'datetime': now - 10},
        {'url': 'https://example.com/new', 'datetime': now - 10},
    ]
    monkeypatch.setattr(finnhub, '_request', lambda *args, **kw: records)
    news = finnhub._news('TEST')
    assert [row['url'] for row in news] == ['https://example.com/new', 'https://example.com/old']


def test_canadian_venture_ticker_is_not_changed_to_toronto(monkeypatch):
    def ticker(symbol):
        assert symbol == 'ABC.V'
        frame = pd.DataFrame({'Close': [10., 11.], 'High': [12., 12.], 'Low': [9., 9.], 'Open': [10., 10.]},
                             index=pd.date_range('2026-10-19', periods=2, tz='America/Toronto'))
        return SimpleNamespace(history=lambda **kw: frame)
    monkeypatch.setattr(international.yf, 'Ticker', ticker)
    result = international.get_international_research('CA', 'ABC.V')
    assert result['symbol'] == 'ABC.V'
    assert result['quote']['price_type'] == 'daily_bar'
    assert not result['quote_validation']['is_realtime']


def test_fundamentals_preserve_losses_and_reject_nonfinite(monkeypatch):
    monkeypatch.setattr(fundamentals.yf, 'Ticker', lambda *args: SimpleNamespace(info={
        'longName': 'Test', 'trailingEps': -2, 'trailingPE': float('inf'),
        'totalDebt': 0, 'profitMargins': float('nan'),
    }))
    result = fundamentals.get_fundamentals('US', 'TEST')
    assert result['trailing_eps'] == -2
    assert result['trailing_pe'] is None and result['profit_margin'] is None
    assert result['total_debt'] == 0


def test_cache_copies_results_and_never_caches_exceptions():
    calls = []
    @ttl_cache(60, maxsize=1)
    def fetch(key):
        calls.append(key)
        if key == 'fail':
            raise ValueError('failed')
        return {'values': [key]}
    fetch('a')['values'].append('mutated')
    assert fetch('a') == {'values': ['a']}
    assert calls == ['a']
    for _ in range(2):
        with pytest.raises(ValueError):
            fetch('fail')
    assert calls == ['a', 'fail', 'fail']
    fetch('b')
    fetch('a')
    assert calls[-2:] == ['b', 'a']


@pytest.mark.parametrize('url', ['javascript:alert(1)', 'data:text/html,evil', '//example.com', 'https://user:pass@example.com', None])
def test_unsafe_source_urls_are_rejected(url):
    assert safe_url(url) is None


def test_sec_uses_latest_restatements_and_same_filing_cash_components(monkeypatch):
    monkeypatch.setenv('SEC_USER_AGENT', 'Test contact@example.com')
    def record(value, filed, accession, **kw):
        return {'start': '2023-01-01', 'end': '2023-12-31', 'form': '10-K',
                'filed': filed, 'accn': accession, 'val': value, **kw}
    old = ('2024-02-01', 'old')
    new = ('2025-02-01', 'new')
    facts = {'facts': {'us-gaap': {
        'Revenues': {'units': {'USD': [record(100, *old), record(90, *new)]}},
        'NetIncomeLoss': {'units': {'USD': [record(20, *old), record(15, *new)]}},
        'NetCashProvidedByUsedInOperatingActivities': {'units': {'USD': [record(50, *old), record(40, *new)]}},
        'PaymentsToAcquireProductiveAssets': {'units': {'USD': [record(10, *old)]}},
        'PaymentsToAcquirePropertyPlantAndEquipment': {'units': {'USD': [record(8, *new)]}},
    }}}
    response = httpx.Response(200, json=facts, request=httpx.Request('GET', 'https://data.sec.gov/test'))
    monkeypatch.setattr(sec_filings.httpx, 'get', lambda *args, **kwargs: response)
    result = sec_filings.get_sec_annual_financials(1)
    row = result['history'][0]
    assert row['revenue'] == 90 and row['net_income'] == 15
    assert row['cash_after_productive_asset_purchases'] == 32
    assert row['operating_cash_flow_accession'] == row['productive_asset_purchases_accession'] == 'new'
    assert 'not point-in-time' in result['revision_policy']


def test_share_classes_use_yahoo_symbol_format(monkeypatch):
    def ticker(symbol):
        assert symbol == 'BRK-B'
        return SimpleNamespace(info={'longName': 'Test Class B'})
    monkeypatch.setattr(fundamentals.yf, 'Ticker', ticker)
    assert fundamentals.get_fundamentals('US', 'BRK.B')['symbol'] == 'BRK.B'


def test_directory_is_shared_across_sec_ticker_lookups(monkeypatch):
    monkeypatch.setenv('SEC_USER_AGENT', 'Test contact@example.com')
    calls = []
    def get(*args, **kw):
        calls.append(args)
        return httpx.Response(200, json={'0': {'ticker': 'BRK-B', 'cik_str': 1}, '1': {'ticker': 'BF-B', 'cik_str': 2}},
                              request=httpx.Request('GET', 'https://www.sec.gov/test'))
    monkeypatch.setattr(sec_filings.httpx, 'get', get)
    assert sec_filings.lookup_sec_cik('BRK.B') == 1
    assert sec_filings.lookup_sec_cik('BF-B') == 2
    assert len(calls) == 1


def test_yahoo_cashflow_matches_period_and_outflow_sign(monkeypatch):
    periods = pd.to_datetime(['2023-06-30', '2024-06-30', '2025-06-30'])
    income = pd.DataFrame([[100, 150, 180]], index=['Total Revenue'], columns=periods)
    cash = pd.DataFrame([[25, 30, 35], [-5, -6, 7]], index=['Operating Cash Flow', 'Capital Expenditure'], columns=periods)
    monkeypatch.setattr(fundamentals.yf, 'Ticker', lambda *args: SimpleNamespace(income_stmt=income, cashflow=cash))
    rows = fundamentals.get_historical_financials('IN', 'TEST')['history']
    assert rows[0]['cash_after_productive_asset_purchases'] == 20
    assert rows[1]['cash_after_productive_asset_purchases'] == 24
    assert rows[2]['cash_after_productive_asset_purchases'] is None  # Unrecognized positive capex is not guessed.


def test_finnhub_entitlement_is_explicit_configuration(monkeypatch):
    calls = []
    def request(path, **kw):
        calls.append(kw['symbol'])
        return {'c': 100, 't': datetime.now(timezone.utc).timestamp()}
    monkeypatch.setattr(finnhub, '_request', request)
    monkeypatch.setenv('FINNHUB_REALTIME_ENTITLED', 'false')
    assert not finnhub._quote('BRK-B')['realtime_entitled']
    finnhub._quote.cache_clear()
    monkeypatch.setenv('FINNHUB_REALTIME_ENTITLED', 'true')
    assert finnhub._quote('BRK-B')['realtime_entitled']
    assert calls == ['BRK.B', 'BRK.B']
