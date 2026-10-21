"""One valuation snapshot with independent, bounded provider caches."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
import logging

import yfinance as yf

from .data_utils import finite_number, normalize_symbol, safe_url, ttl_cache
from .gain_valuation import HORIZON_YEARS, build_gain_view
from .market_setup import build_market_setup
from .price_history import get_price_history, get_fx_rate, historical_performance
from .research_service import collect_snapshot

logger = logging.getLogger(__name__)


@ttl_cache(300, maxsize=128)
def company_news(market, symbol):
    ticker = normalize_symbol(market, symbol)
    if market == 'US':
        ticker = ticker.replace('.', '-')
    try:
        payload = yf.Ticker(ticker).news or []
    except Exception:
        return []
    sources = []
    now = datetime.now(timezone.utc)
    for row in payload:
        content = row.get('content', row) if isinstance(row, dict) else {}
        if not isinstance(content, dict):
            continue
        canonical = content.get('canonicalUrl') or content.get('clickThroughUrl') or {}
        url = safe_url(canonical.get('url') if isinstance(canonical, dict) else canonical) or safe_url(content.get('link'))
        published = content.get('pubDate') or content.get('providerPublishTime')
        try:
            when = datetime.fromtimestamp(published, timezone.utc) if isinstance(published, (int, float)) else datetime.fromisoformat(published.replace('Z', '+00:00'))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError, AttributeError, OverflowError, OSError):
            continue
        if not url or not now - timedelta(days=30) <= when <= now:
            continue
        provider = content.get('provider') or {}
        sources.append({'title': str(content.get('title') or 'Article')[:500], 'url': url,
                        'source': str(provider.get('displayName') if isinstance(provider, dict) else provider)[:100],
                        'published_at': when.timestamp(), 'summary': str(content.get('summary') or '')[:2000],
                        'relevance': 'Provider-associated; relevance requires review'})
    unique = {row['url']: row for row in sources}
    return sorted(unique.values(), key=lambda row: row['published_at'], reverse=True)[:8]


def valuation_snapshot(market, symbol, profile, **options):
    warnings = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = {'snapshot': pool.submit(collect_snapshot, market, symbol),
                'history': pool.submit(get_price_history, market, symbol),
                'benchmark': pool.submit(get_price_history, market, symbol, True)}
        data = {}
        for name, job in jobs.items():
            try:
                data[name] = job.result()
            except Exception as exc:
                logger.warning('Valuation component %s unavailable (%s)', name, type(exc).__name__)
                data[name] = None
                warnings.append(f'{name.capitalize()} component unavailable.')
    snapshot = data['snapshot'] or {'market': market, 'symbol': symbol, 'fundamentals': {}, 'quote': None,
                                   'historical_financials': {}, 'sources': [], 'warnings': []}
    if not snapshot['sources']:
        snapshot['sources'] = company_news(market, symbol)
    currency = (snapshot.get('quote') or {}).get('currency')
    fx = None
    try:
        fx = get_fx_rate(profile['currency'], currency)
    except Exception:
        warnings.append('Currency conversion unavailable. Percentage returns remain visible; cash gains are withheld.')
    years = HORIZON_YEARS.get(profile.get('horizon'), 4)
    history = historical_performance(data['history'] or {}, years, data['benchmark'])
    if data['history'] and currency != data['history'].get('currency'):
        history = {'status': 'insufficient', 'reason': 'Price-history currency does not match the current quote', 'returns': [], 'chart': []}
    snapshot['warnings'].extend(warnings)
    result = build_gain_view(snapshot, history, profile, fx, **options)
    result['market_setup'] = build_market_setup(data['history'], data['benchmark'], snapshot.get('quote'),
                                               result['preferences'], result['buy_assessment']['checks'], market=market)
    return result
