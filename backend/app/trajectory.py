from math import isfinite


def calculate_trajectory(
    current_price: float,
    trailing_eps: float,
    current_pe: float,
    years: int = 3,
):
    """
    Illustrative EPS/P-E scenario model.
    Growth and valuation adjustments are assumptions,
    not AI predictions or analyst consensus.
    """
    values = (current_price, trailing_eps, current_pe)

    if (
        not all(isinstance(v, (int, float)) and isfinite(v) for v in values)
        or current_price <= 0
        or trailing_eps <= 0
        or current_pe <= 0
    ):
        return {
            "status": "insufficient_data",
            "assessment": "Insufficient data",
            "reason": "Positive earnings and a valid valuation are required.",
            "scenarios": [],
        }

    assumptions = {
        "bear": {
            "eps_growth": -0.05,
            "pe_multiplier": 0.70,
        },
        "base": {
            "eps_growth": 0.08,
            "pe_multiplier": 1.00,
        },
        "bull": {
            "eps_growth": 0.18,
            "pe_multiplier": 1.15,
        },
    }

    scenarios = []

    for name, assumption in assumptions.items():
        future_eps = trailing_eps * (
            1 + assumption["eps_growth"]
        ) ** years

        future_pe = current_pe * assumption["pe_multiplier"]
        future_price = future_eps * future_pe

        total_return = (future_price / current_price - 1) * 100
        annualized_return = (
            (future_price / current_price) ** (1 / years) - 1
        ) * 100

        scenarios.append({
            "scenario": name,
            "years": years,
            "eps_growth_assumption": assumption["eps_growth"] * 100,
            "future_pe_assumption": round(future_pe, 2),
            "target_price": round(future_price, 2),
            "total_return_percent": round(total_return, 2),
            "annualized_return_percent": round(annualized_return, 2),
        })

    base = next(
        item for item in scenarios
        if item["scenario"] == "base"
    )

    if base["annualized_return_percent"] >= 12:
        assessment = "Potential opportunity — further research required"
    elif base["annualized_return_percent"] >= 5:
        assessment = "Watch — valuation needs review"
    else:
        assessment = "Avoid for now — illustrative return is limited"

    return {
        "status": "illustrative",
        "assessment": assessment,
        "current_price": round(current_price, 2),
        "trailing_eps": round(trailing_eps, 2),
        "current_pe": round(current_pe, 2),
        "scenarios": scenarios,
        "disclaimer": (
            "Scenario assumptions are illustrative, not forecasts. "
            "This assessment excludes dividends, taxes, currency changes, "
            "and company-specific risk analysis. "
            "Do not use it alone to make an investment decision."
        ),
    }
