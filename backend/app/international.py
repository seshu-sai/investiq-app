from datetime import datetime, timezone
import math
import re

import yfinance as yf


class MarketDataError(Exception):
    pass


def get_international_research(market: str, symbol: str):
    if market not in ("IN", "CA"):
        raise MarketDataError("Unsupported market")

    symbol = symbol.strip().upper()

    if not re.fullmatch(r"[A-Z0-9.\-]{1,32}", symbol):
        raise MarketDataError("Invalid ticker symbol")

    if market == "IN":
        if not symbol.endswith((".NS", ".BO")):
            symbol += ".NS"
        currency = "INR"
    else:
        if not symbol.endswith(".TO"):
            symbol += ".TO"
        currency = "CAD"

    try:
        ticker = yf.Ticker(symbol)
        history = ticker.history(period="5d", auto_adjust=False)

        if history.empty:
            raise MarketDataError(f"No price data available for {symbol}")

        latest = history.iloc[-1]
        previous_close = (
            float(history.iloc[-2]["Close"])
            if len(history) > 1
            else None
        )

        def number(value):
            if value is None:
                return None
            value = float(value)
            return value if math.isfinite(value) else None

        current = number(latest["Close"])
        change = (
            current - previous_close
            if current is not None and previous_close is not None
            else None
        )
        percent_change = (
            change / previous_close * 100
            if change is not None and previous_close
            else None
        )

        return {
            "market": market,
            "symbol": symbol,
            "status": "connected",
            "provider": "Yahoo Finance (unofficial)",
            "quote": {
                "current": current,
                "change": change,
                "percent_change": percent_change,
                "high": number(latest["High"]),
                "low": number(latest["Low"]),
                "open": number(latest["Open"]),
                "previous_close": previous_close,
                "timestamp": int(history.index[-1].timestamp()),
                "currency": currency,
            },
            "sources": [],
            "catalysts": [],
            "forecasts": [],
            "message": (
                "Historical daily price data retrieved from Yahoo Finance. "
                "The displayed close is not a real-time quote. "
                "Verified company news and AI forecasts are not yet available."
            ),
        }

    except MarketDataError:
        raise
    except Exception as exc:
        raise MarketDataError(
            f"Unable to retrieve market data for {symbol}"
        ) from exc


def search_international_stocks(market: str, query: str):
    """Search Indian or Canadian listed stocks by name or ticker."""
    import httpx

    if market not in ("IN", "CA"):
        raise MarketDataError("Unsupported market")

    query = query.strip()
    if len(query) < 2:
        return []

    try:
        with httpx.Client(
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"},
            follow_redirects=True,
        ) as client:
            response = client.get(
                "https://query1.finance.yahoo.com/v1/finance/search",
                params={
                    "q": query,
                    "quotesCount": 30,
                    "newsCount": 0,
                },
            )
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise MarketDataError("International stock search failed") from exc

    suffixes = (".NS", ".BO") if market == "IN" else (".TO", ".V")

    matches = []
    for item in data.get("quotes", []):
        if not isinstance(item, dict):
            continue

        symbol = item.get("symbol", "")
        if (
            isinstance(symbol, str)
            and symbol.upper().endswith(suffixes)
            and item.get("quoteType") == "EQUITY"
        ):
            matches.append({
                "symbol": symbol.upper(),
                "name": item.get("shortname") or item.get("longname") or symbol,
                "market": market,
            })

    return matches[:10]
