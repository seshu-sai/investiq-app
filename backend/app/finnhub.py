import os
from datetime import date, timedelta

import httpx

BASE_URL = "https://finnhub.io/api/v1"


class FinnhubError(Exception):
    pass


def get_research(symbol: str):
    api_key = os.getenv("FINNHUB_API_KEY")
    if not api_key:
        raise FinnhubError("FINNHUB_API_KEY is not configured")

    today = date.today()
    start = today - timedelta(days=14)

    try:
        with httpx.Client(timeout=12.0) as client:
            quote_response = client.get(
                f"{BASE_URL}/quote",
                params={"symbol": symbol, "token": api_key},
            )
            quote_response.raise_for_status()
            quote = quote_response.json()

            news_response = client.get(
                f"{BASE_URL}/company-news",
                params={
                    "symbol": symbol,
                    "from": start.isoformat(),
                    "to": today.isoformat(),
                    "token": api_key,
                },
            )
            news_response.raise_for_status()
            news = news_response.json()

    except (httpx.HTTPError, ValueError) as exc:
        raise FinnhubError("Finnhub request failed") from exc

    if not isinstance(quote, dict) or not quote.get("c"):
        raise FinnhubError("No valid quote returned for this symbol")

    if not isinstance(news, list):
        raise FinnhubError("Invalid news response from Finnhub")

    return {
        "market": "US",
        "symbol": symbol,
        "status": "connected",
        "provider": "Finnhub",
        "quote": {
            "current": quote.get("c"),
            "change": quote.get("d"),
            "percent_change": quote.get("dp"),
            "high": quote.get("h"),
            "low": quote.get("l"),
            "open": quote.get("o"),
            "previous_close": quote.get("pc"),
            "timestamp": quote.get("t"),
            "currency": "USD",
        },
        "sources": [
            {
                "title": item.get("headline"),
                "url": item.get("url"),
                "source": item.get("source"),
                "published_at": item.get("datetime"),
                "summary": item.get("summary"),
            }
            for item in news[:10]
            if isinstance(item, dict) and item.get("url")
        ],
        "catalysts": [],
        "forecasts": [],
        "message": (
            "Live quote and recent news retrieved from Finnhub. "
            "AI catalyst analysis and financial forecasting are not yet implemented."
        ),
    }


def search_stocks(query: str):
    """Search US stock symbols and company names using Finnhub."""
    api_key = os.getenv("FINNHUB_API_KEY")
    if not api_key:
        raise FinnhubError("FINNHUB_API_KEY is not configured")

    query = query.strip()
    if len(query) < 2:
        return []

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                f"{BASE_URL}/search",
                params={"q": query, "token": api_key},
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise FinnhubError("Stock search failed") from exc

    results = payload.get("result", []) if isinstance(payload, dict) else []

    return [
        {
            "symbol": item["symbol"],
            "name": item.get("description") or item["symbol"],
            "market": "US",
        }
        for item in results
        if isinstance(item, dict)
        and item.get("symbol")
        and item.get("type") == "Common Stock"
        and "." not in item["symbol"]
    ][:10]
