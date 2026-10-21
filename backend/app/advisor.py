"""Reproducible research checks. Thresholds are policy, not return forecasts."""
from datetime import date, datetime, timezone

from .data_utils import finite_number
from .price_validation import validate_market_quote

POLICY_VERSION = "2026-10-21.1"
HORIZONS = {"0-1": "under 1 year", "1-3": "1-3 years", "3-5": "3-5 years", "5+": "5+ years"}


def assess_evidence(market, symbol, fundamentals, financials, quote, profile=None, owns_position=False):
    profile = profile or {}
    price = validate_market_quote(quote)
    warnings, missing, risks, evidence = [], [], [], []
    today = datetime.now(timezone.utc).date()
    records = []
    for row in financials.get("history") or []:
        if not isinstance(row, dict):
            continue
        try:
            end = date.fromisoformat(row.get("fiscal_year_end"))
        except (ValueError, TypeError):
            continue
        if end > today:
            warnings.append("Future financial period excluded.")
            continue
        revenue = finite_number(row.get("revenue"))
        if revenue is None or revenue <= 0:
            continue
        records.append({**row, "fiscal_year_end": end.isoformat(), "revenue": revenue})
    records.sort(key=lambda row: row["fiscal_year_end"])
    if len({row["fiscal_year_end"] for row in records}) != len(records):
        missing.append("Unique annual financial periods")
        records = []
    if not price["valid"]:
        missing.append(price["reason"])
    if not fundamentals.get("company"):
        missing.append("Company identity and fundamentals")
    if fundamentals.get("currency") != (quote or {}).get("currency") or not fundamentals.get("currency"):
        missing.append("Matching quote and per-share earnings currency")
    if len(records) < 3:
        missing.append("At least three dated annual revenue records")
    elif (today - date.fromisoformat(records[-1]["fiscal_year_end"])).days > 540:
        missing.append("Annual financial statements within 540 days")
    if len(records) >= 3 and any(not 330 <= (date.fromisoformat(b["fiscal_year_end"]) - date.fromisoformat(a["fiscal_year_end"])).days <= 400
                                 for a, b in zip(records[-3:], records[-2:])):
        missing.append("Three consecutive annual financial periods")
    if not price["is_realtime"]:
        warnings.append(price["reason"])
    if "SEC" not in str(financials.get("source", "")):
        warnings.append("Historical statements use an unofficial source; filing provenance is unverified.")
    warnings.append("Valuation scenarios are illustrative; validated intrinsic value and downside analysis are unavailable.")
    if not price["valid"]:
        risks.append("The available price cannot support a current entry decision.")

    annual_growth, cash_flows = [], []
    for index, row in enumerate(records):
        end = row["fiscal_year_end"]
        evidence.append({"id": f"annual-{end}", "source": financials.get("source"),
                         "currency": financials.get("currency"),
                         "period": end, "revenue": row["revenue"],
                         "net_income": finite_number(row.get("net_income")),
                         "cash_after_purchases": finite_number(row.get("cash_after_productive_asset_purchases")),
                         "filed": row.get("revenue_filed"), "accession": row.get("revenue_accession")})
        if index:
            previous = records[index - 1]
            days = (date.fromisoformat(end) - date.fromisoformat(previous["fiscal_year_end"])).days
            if 330 <= days <= 400:
                annual_growth.append(round((row["revenue"] / previous["revenue"] - 1) * 100, 2))
            else:
                annual_growth = []
                warnings.append("Missing annual periods; multi-year gaps are not year-over-year growth.")
        cash_flows.append(finite_number(row.get("cash_after_productive_asset_purchases")))

    recent_growth = annual_growth[-3:]
    growth_trend = "insufficient data"
    if len(recent_growth) >= 2:
        growth_trend = "slowing" if all(b < a for a, b in zip(recent_growth, recent_growth[1:])) else (
            "accelerating" if all(b > a for a, b in zip(recent_growth, recent_growth[1:])) else "mixed")
    if recent_growth and recent_growth[-1] < 0:
        risks.append("Latest comparable annual revenue declined.")
    recent_cash = cash_flows[-3:]
    cash_trend = "insufficient data"
    recent_periods = [date.fromisoformat(row["fiscal_year_end"]) for row in records[-3:]]
    consecutive_cash = all(330 <= (b - a).days <= 400 for a, b in zip(recent_periods, recent_periods[1:]))
    if len(recent_cash) >= 2 and consecutive_cash and all(value is not None for value in recent_cash):
        cash_trend = "increasing" if all(b > a for a, b in zip(recent_cash, recent_cash[1:])) else (
            "decreasing" if all(b < a for a, b in zip(recent_cash, recent_cash[1:])) else "mixed")
        if recent_cash[-1] <= 0:
            risks.append("Latest annual cash generation after productive-asset purchases is non-positive.")
    eps = finite_number(fundamentals.get("trailing_eps"))
    if eps is not None and eps <= 0:
        risks.append("Provider-reported trailing earnings per share are non-positive.")
    actual_pe = round(price["price"] / eps, 2) if price["valid"] and eps and eps > 0 and not any("currency" in item for item in missing) else None
    if actual_pe is not None and actual_pe > 40:
        risks.append("Price exceeds 40 times reported trailing earnings; growth disappointment can compress the multiple.")
    latest_income = finite_number(records[-1].get("net_income")) if records else None
    latest_margin = round(latest_income / records[-1]["revenue"] * 100, 2) if latest_income is not None else None
    earnings_growth = None
    if len(records) >= 2 and consecutive_cash:
        previous_income = finite_number(records[-2].get("net_income"))
        if latest_income is not None and previous_income is not None and previous_income > 0:
            earnings_growth = round((latest_income / previous_income - 1) * 100, 2)
            if earnings_growth < 0:
                risks.append("Net income fell in the latest comparable annual period.")
    if latest_income is not None and latest_income < 0:
        risks.append("The latest dated annual statement reports a net loss.")

    fit = []
    if profile.get("risk") == "low":
        fit.append("A single stock can suffer large losses and may conflict with low risk tolerance.")
    if profile.get("horizon") == "0-1":
        fit.append("A horizon under one year is unsuitable for relying on long-term equity valuation.")
    if profile.get("markets") and market not in profile["markets"]:
        fit.append("This market is outside your saved preferences.")
    if profile.get("assets") and "stocks" not in profile["assets"]:
        fit.append("Individual stocks are outside your saved asset preferences.")
    has_fit_blocker = bool(fit)
    if profile.get("currency") and profile["currency"] != (quote or {}).get("currency"):
        fit.append("Foreign-exchange movements and conversion costs affect returns in your base currency.")
    warnings.append("Holdings, concentration, liquidity needs, taxes and loss capacity are unknown; position sizing is unavailable.")
    allowed = ["INSUFFICIENT DATA"] if missing else ["WAIT", "AVOID", "INSUFFICIENT DATA"]
    if owns_position and not missing and not has_fit_blocker:
        allowed.append("HOLD")
    return {
        "policy_version": POLICY_VERSION, "market": market, "symbol": symbol,
        "generated_at": datetime.now(timezone.utc).isoformat(), "quote": price,
        "financial_period_end": records[-1]["fiscal_year_end"] if records else None,
        "data_quality": "insufficient" if missing else "limited",
        "missing_data": missing, "warnings": list(dict.fromkeys(warnings)), "risk_flags": risks,
        "investor_fit": {"risk": profile.get("risk", "unknown"),
                         "horizon": HORIZONS.get(profile.get("horizon"), "not specified"),
                         "owns_position": owns_position, "warnings": fit,
                         "position_size": None},
        "metrics": {"trailing_pe_at_quote": actual_pe,
                    "revenue_growth_trend": growth_trend,
                    "annual_revenue_growth_rates_percent": recent_growth,
                    "latest_annual_net_margin_percent": latest_margin,
                    "latest_annual_net_income_growth_percent": earnings_growth,
                    "cash_flow_trend": cash_trend},
        "evidence": evidence, "allowed_decisions": allowed, "buy_eligible": False,
        "required_before_buy": ["Verified current executable price and market session",
                                "Company-specific valuation with validated cash flows, dilution and capital structure",
                                "Downside stress test, portfolio concentration and investor suitability review"],
    }


def fallback_decision(assessment):
    missing = assessment["missing_data"]
    return {
        "decision": "INSUFFICIENT DATA" if missing else "WAIT",
        "headline": "More verified evidence is needed" if missing else "Research further before committing capital",
        "reason": "; ".join(missing[:3]) if missing else "Available financial history does not establish an attractive buying valuation.",
        "upside": "Historical growth is descriptive; future returns are uncertain.",
        "risk": " ".join((assessment["risk_flags"] or ["A single equity can suffer a substantial loss."])[:2]),
        "entry_price": None, "target_price": None,
        "time_horizon": assessment["investor_fit"]["horizon"],
        "next_action": " ".join(assessment["investor_fit"]["warnings"][:1]) or assessment["required_before_buy"][1] + ".",
        "data_as_of": assessment["quote"].get("timestamp"), "evidence_refs": [],
    }
