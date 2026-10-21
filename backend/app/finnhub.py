"""Finnhub quotes and news fail independently; never infer real-time entitlement."""
import os
from datetime import datetime, timezone, timedelta

import httpx

from .data_utils import finite_number, normalize_symbol, safe_url, ttl_cache
from .price_validation import validate_market_quote

BASE_URL = "https://finnhub.io/api/v1"


class FinnhubError(Exception):
    pass


def _request(path, **params):
    api_key = os.getenv("FINNHUB_API_KEY")
    if not api_key:
        raise FinnhubError("FINNHUB_API_KEY is not configured")
    try:
        response = httpx.get(f"{BASE_URL}/{path}", params={**params, "token": api_key}, timeout=12)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise FinnhubError("Finnhub data is temporarily unavailable") from exc


@ttl_cache(15)
def _quote(symbol):
    quote = _request("quote", symbol=symbol.replace("-", "."))
    if not isinstance(quote, dict):
        raise FinnhubError("Invalid quote response")
    current = finite_number(quote.get("c"))
    if current is None or current <= 0:
        raise FinnhubError("No valid quote returned for this symbol")
    return {
        "current": current, "change": finite_number(quote.get("d")),
        "percent_change": finite_number(quote.get("dp")), "high": finite_number(quote.get("h")),
        "low": finite_number(quote.get("l")), "open": finite_number(quote.get("o")),
        "previous_close": finite_number(quote.get("pc")), "timestamp": finite_number(quote.get("t")),
        "currency": "USD", "price_type": "provider_quote",
        "realtime_entitled": os.getenv("FINNHUB_REALTIME_ENTITLED", "false").lower() == "true",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }


@ttl_cache(300)
def _news(symbol):
    now = datetime.now(timezone.utc)
    news = _request("company-news", symbol=symbol.replace("-", "."), **{
        "from": (now - timedelta(days=14)).date().isoformat(), "to": now.date().isoformat(),
    })
    if not isinstance(news, list):
        raise FinnhubError("Invalid news response")
    sources, seen = [], set()
    for item in news:
        if not isinstance(item, dict):
            continue
        url = safe_url(item.get("url"))
        published = finite_number(item.get("datetime"))
        if not url or url in seen or published is None or not now.timestamp() - 14 * 86400 <= published <= now.timestamp() + 60:
            continue
        seen.add(url)
        sources.append({
            "title": str(item.get("headline") or "Article")[:500], "url": url,
            "source": str(item.get("source") or "Unknown")[:100], "published_at": published,
            "summary": str(item.get("summary") or "")[:2000],
            "relevance": "Provider-associated; company relevance requires verification",
        })
    return sorted(sources, key=lambda item: item["published_at"], reverse=True)[:10]


def get_research(symbol: str):
    symbol = normalize_symbol("US", symbol)
    quote = _quote(symbol)
    warnings = []
    try:
        sources = _news(symbol)
    except FinnhubError:
        sources = []
        warnings.append("Recent news is unavailable; the quote remains available.")
    return {
        "market": "US", "symbol": symbol, "status": "connected", "provider": "Finnhub",
        "quote": quote, "quote_validation": validate_market_quote(quote), "sources": sources,
        "warnings": warnings, "catalysts": [], "forecasts": [],
        "message": "Provider quote and recent news. Check the quote timestamp and exchange entitlements.",
    }


@ttl_cache(60)
def search_stocks(query: str):
    query = query.strip()
    if len(query) < 2:
        return []
    payload = _request("search", q=query)
    results = payload.get("result", []) if isinstance(payload, dict) else []
    return [
        {"symbol": item["symbol"], "name": item.get("description") or item["symbol"], "market": "US"}
        for item in results if isinstance(item, dict) and item.get("symbol")
        and item.get("type") == "Common Stock"
    ][:10]
