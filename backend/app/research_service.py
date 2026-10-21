"""Collect one research snapshot without repeating provider requests."""
from concurrent.futures import ThreadPoolExecutor
import logging

from .finnhub import get_research
from .international import get_international_research
from .fundamentals import get_fundamentals, get_historical_financials
from .sec_filings import SECDataError, get_sec_annual_financials, lookup_sec_cik
from .price_validation import validate_market_quote
from .trajectory import calculate_trajectory

logger = logging.getLogger(__name__)


def financial_history(market, symbol):
    warnings = []
    if market == "US":
        try:
            return get_sec_annual_financials(lookup_sec_cik(symbol)), warnings
        except SECDataError:
            warnings.append("SEC statements unavailable; using unofficial financial history if available.")
    return get_historical_financials(market, symbol), warnings


def collect_snapshot(market, symbol, include_history=True):
    warnings = []
    loaders = {
        "fundamentals": lambda: get_fundamentals(market, symbol),
        "research": lambda: get_research(symbol) if market == "US" else get_international_research(market, symbol),
    }
    if include_history:
        loaders["history"] = lambda: financial_history(market, symbol)
    data = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = {name: pool.submit(loader) for name, loader in loaders.items()}
        for name, job in jobs.items():
            try:
                data[name] = job.result()
            except Exception as exc:
                logger.warning("Research component %s unavailable (%s)", name, type(exc).__name__)
                data[name] = None
                warnings.append(f"{name.capitalize()} provider unavailable; no substitute values were inferred.")
    fundamentals = data.get("fundamentals") or {"symbol": symbol}
    research = data.get("research") or {}
    quote = research.get("quote")
    quote_validation = validate_market_quote(quote)
    history, history_warnings = data.get("history") or ({}, [])
    if history and not history.get("currency"):
        history["currency"] = fundamentals.get("financial_currency")
        history["currency_note"] = "Currency from provider company profile; statement currency is unverified"
    warnings.extend(history_warnings)
    warnings.extend(research.get("warnings") or [])
    eps = fundamentals.get("trailing_eps")
    same_currency = bool(quote and quote.get("currency") == fundamentals.get("currency"))
    if quote_validation["valid"] and same_currency and isinstance(eps, (int, float)) and eps > 0:
        # P/E and starting price now share a consistent, observed quote.
        trajectory = calculate_trajectory(quote_validation["price"], eps, quote_validation["price"] / eps)
    else:
        trajectory = {"status": "insufficient_data", "assessment": "Insufficient data", "scenarios": [],
                      "reason": "A usable provider price and positive EPS in the same currency are required."}
    return {"market": market, "symbol": symbol, "fundamentals": fundamentals,
            "quote": quote, "quote_validation": quote_validation, "trajectory": trajectory,
            "historical_financials": history, "sources": research.get("sources") or [], "warnings": warnings}
