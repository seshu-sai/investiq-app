"""Illustrative discounted cash-flow valuation using explicit assumptions."""

import math


class ValuationError(ValueError):
    pass


def calculate_cash_flow_valuation(
    annual_cash_flow: float,
    shares_outstanding: float,
    growth_rate: float,
    discount_rate: float,
    terminal_growth_rate: float,
    years: int = 5,
    net_financial_assets: float = 0,
    margin_of_safety: float = 0.25,
) -> dict:
    """Discount projected cash flows and calculate illustrative value per share.

    This simplified model treats cash flow after productive-asset purchases
    as an equity cash-flow proxy. It is not a fully adjusted FCFE or FCFF model.
    """
    values = (
        annual_cash_flow,
        shares_outstanding,
        growth_rate,
        discount_rate,
        terminal_growth_rate,
        net_financial_assets,
        margin_of_safety,
    )

    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values):
        raise ValuationError("All valuation inputs must be finite numbers")

    if annual_cash_flow <= 0 or shares_outstanding <= 0:
        raise ValuationError("Positive cash flow and share count are required")

    if not 1 <= years <= 10:
        raise ValuationError("Projection years must be between 1 and 10")

    if not -0.5 <= growth_rate <= 1:
        raise ValuationError("Growth assumption must be between -50% and 100%")

    if not 0 < discount_rate <= 0.5:
        raise ValuationError("Discount rate must be between 0% and 50%")

    if not -0.05 <= terminal_growth_rate <= 0.05:
        raise ValuationError("Terminal growth must be between -5% and 5%")

    if discount_rate <= terminal_growth_rate:
        raise ValuationError("Discount rate must exceed terminal growth")

    if not 0 <= margin_of_safety < 1:
        raise ValuationError("Margin of safety must be between 0% and 100%")

    projections = []
    cash_flow = annual_cash_flow
    present_value = 0.0

    for year in range(1, years + 1):
        cash_flow *= 1 + growth_rate
        discounted = cash_flow / (1 + discount_rate) ** year
        present_value += discounted
        projections.append({
            "year": year,
            "projected_cash_flow": round(cash_flow, 2),
            "present_value": round(discounted, 2),
        })

    terminal_value = (
        cash_flow * (1 + terminal_growth_rate)
        / (discount_rate - terminal_growth_rate)
    )
    discounted_terminal = terminal_value / (1 + discount_rate) ** years

    total_value = present_value + discounted_terminal + net_financial_assets
    fair_value_per_share = total_value / shares_outstanding

    return {
        "model": "illustrative_cash_flow_discounting",
        "fair_value_per_share": round(fair_value_per_share, 2),
        "margin_of_safety_price": round(
            fair_value_per_share * (1 - margin_of_safety), 2
        ),
        "projected_cash_flows": projections,
        "assumptions": {
            "growth_rate": growth_rate,
            "discount_rate": discount_rate,
            "terminal_growth_rate": terminal_growth_rate,
            "years": years,
            "margin_of_safety": margin_of_safety,
            "net_financial_assets": net_financial_assets,
        },
        "limitations": (
            "Illustrative model only. Cash flow after productive-asset "
            "purchases is not fully adjusted FCFE or FCFF. "
            "Growth and discount rates are assumptions, not verified forecasts. "
            "Net financial assets must not be added without checking for "
            "double-counting and consistency with the cash-flow definition."
        ),
    }
