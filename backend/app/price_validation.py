"""Separate a usable recent price from a verified real-time price."""

from datetime import datetime, timezone

from .data_utils import finite_number


def validate_market_quote(quote: dict | None, *, now: datetime | None = None) -> dict:
    result = {"valid": False, "is_realtime": False, "status": "missing", "timestamp": None}
    if not isinstance(quote, dict):
        return {**result, "reason": "Missing market quote"}
    price = finite_number(quote.get("current"))
    timestamp = finite_number(quote.get("timestamp"))
    if price is None or price <= 0:
        return {**result, "reason": "Invalid market price"}
    if timestamp is None or timestamp <= 0:
        return {**result, "reason": "Missing quote timestamp"}
    try:
        measured_at = datetime.fromtimestamp(timestamp, timezone.utc)
    except (ValueError, OverflowError, OSError):
        return {**result, "reason": "Invalid quote timestamp"}
    age = ((now or datetime.now(timezone.utc)) - measured_at).total_seconds()
    result.update(price=price, currency=quote.get("currency"), timestamp=measured_at.isoformat(),
                  age_seconds=round(max(age, 0)), age_hours=round(max(age, 0) / 3600, 2))
    if age < -60:
        return {**result, "status": "invalid", "reason": "Quote timestamp is in the future"}
    if quote.get("currency") not in ("USD", "CAD", "INR"):
        return {**result, "status": "invalid", "reason": "Quote currency is missing or unsupported"}
    # Weekend/holiday closes may remain useful for research, never for live entry decisions.
    if age > 4 * 86400:
        return {**result, "status": "stale", "reason": "Market quote is over four days old"}
    daily = quote.get("price_type") == "daily_bar"
    realtime = not daily and age <= 120 and quote.get("realtime_entitled") is True
    status = "daily_bar" if daily else "realtime" if realtime else "recent" if age <= 120 else "delayed_or_closed"
    return {**result, "valid": True, "is_realtime": realtime, "status": status,
            "reason": "Daily bar; Close may be provisional. Timestamp marks the session date, not the last trade" if daily else
                      "Configured real-time entitlement; provider timestamp is within two minutes" if realtime else
                      "Provider quote; real-time freshness or entitlement is unverified"}
