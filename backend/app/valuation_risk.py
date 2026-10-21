"""Assess the reliability of illustrative valuation scenarios."""

import math


def assess_valuation_risk(scenarios: list) -> dict:
    if not isinstance(scenarios, list) or len(scenarios) < 3:
        return {
            "valid": False,
            "reason": "At least three valuation scenarios are required",
        }

    values = []
    terminal_shares = []

    for scenario in scenarios:
        value = scenario.get("illustrative_value_per_share_usd")
        terminal = scenario.get("terminal_value_share_approx")

        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
            or value <= 0
            or not isinstance(terminal, (int, float))
            or isinstance(terminal, bool)
            or not math.isfinite(terminal)
            or not 0 <= terminal <= 1
        ):
            return {
                "valid": False,
                "reason": "Invalid valuation or terminal-value data",
            }

        values.append(float(value))
        terminal_shares.append(float(terminal))

    spread = (max(values) - min(values)) / min(values)
    max_terminal_share = max(terminal_shares)

    high_sensitivity = (
        spread > 1.0
        or max_terminal_share > 0.70
    )

    return {
        "valid": True,
        "scenario_spread_ratio": round(spread, 4),
        "maximum_terminal_value_share": round(max_terminal_share, 4),
        "high_sensitivity": high_sensitivity,
        "risk_level": "HIGH" if high_sensitivity else "REVIEW",
        "buy_eligible": False,
        "reason": (
            "Illustrative valuations cannot independently justify BUY. "
            "Cash-flow definition, capital structure, forecast assumptions, "
            "market price and downside risk require further validation."
        ),
    }
