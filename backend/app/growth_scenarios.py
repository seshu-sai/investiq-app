"""Build historical-data-informed growth sensitivity scenarios."""

import math


def build_growth_scenarios(growth_analysis: dict) -> dict:
    if not growth_analysis.get("valid"):
        return {
            "valid": False,
            "reason": "Valid historical growth analysis required",
        }

    cagr = growth_analysis.get("historical_cagr")
    volatility = growth_analysis.get("growth_volatility")

    if not all(
        isinstance(x, (int, float))
        and not isinstance(x, bool)
        and math.isfinite(x)
        for x in (cagr, volatility)
    ):
        return {"valid": False, "reason": "Invalid growth statistics"}

    if volatility < 0:
        return {"valid": False, "reason": "Negative volatility"}

    # Cap assumptions to avoid extrapolating extreme historical growth.
    base = max(-0.10, min(0.08, cagr))

    conservative = max(-0.20, base - min(volatility, 0.10))
    optimistic = min(0.12, base + min(volatility / 2, 0.05))

    return {
        "valid": True,
        "scenarios": [
            {"name": "Conservative", "growth_rate": round(conservative, 4)},
            {"name": "Moderate", "growth_rate": round(base, 4)},
            {"name": "Optimistic", "growth_rate": round(optimistic, 4)},
        ],
        "status": "illustrative_only",
        "warning": (
            "Growth scenarios are derived from historical data "
            "and are not validated forecasts or BUY signals."
        ),
    }
