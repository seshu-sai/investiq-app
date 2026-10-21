"""Analyze historical cash-flow growth without treating it as a forecast."""

import math
from datetime import date


def analyze_cash_flow_growth(history: list) -> dict:
    records = sorted(
        [
            record
            for record in history
            if isinstance(
                record.get("cash_after_productive_asset_purchases"),
                (int, float),
            )
            and not isinstance(
                record.get("cash_after_productive_asset_purchases"),
                bool,
            )
            and math.isfinite(
                record["cash_after_productive_asset_purchases"]
            )
            and record["cash_after_productive_asset_purchases"] > 0
        ],
        key=lambda record: record["fiscal_year_end"],
    )

    if len(records) < 3:
        return {
            "valid": False,
            "reason": "At least 3 positive annual cash-flow records required",
        }
    # Do not hide a loss year or missing period by filtering it out of a trend.
    if len(records) != len(history):
        return {"valid": False, "reason": "Incomplete or non-positive annual cash-flow history"}
    try:
        dates = [date.fromisoformat(row["fiscal_year_end"]) for row in records]
    except (TypeError, ValueError):
        return {"valid": False, "reason": "Invalid annual reporting date"}
    if any(not 330 <= (b - a).days <= 400 for a, b in zip(dates, dates[1:])):
        return {"valid": False, "reason": "Annual cash-flow periods are not consecutive"}

    values = [
        float(record["cash_after_productive_asset_purchases"])
        for record in records
    ]

    annual_growth = [
        values[i] / values[i - 1] - 1
        for i in range(1, len(values))
    ]

    cagr = (values[-1] / values[0]) ** (
        365.25 / (dates[-1] - dates[0]).days
    ) - 1

    volatility = (
        sum((rate - sum(annual_growth) / len(annual_growth)) ** 2
            for rate in annual_growth)
        / len(annual_growth)
    ) ** 0.5

    return {
        "valid": True,
        "years": len(values),
        "historical_cagr": round(cagr, 4),
        "annual_growth_rates": [
            round(rate, 4) for rate in annual_growth
        ],
        "growth_volatility": round(volatility, 4),
        "latest_cash_flow": values[-1],
        "warning": (
            "Historical growth and volatility are descriptive only; "
            "they are not validated future growth forecasts."
        ),
    }
