"""Basic SEC financial-data checks for valuation eligibility."""

import math
from datetime import date


def validate_financial_evidence(financials: dict) -> dict:
    history = financials.get("history") or []
    balance = financials.get("balance_sheet") or {}

    if len(history) < 3:
        return {"valid": False, "reason": "Fewer than 3 annual records"}

    recent = history[-3:]
    cash_flows = []
    previous_date = None

    for record in recent:
        value = record.get("cash_after_productive_asset_purchases")
        fiscal_end = record.get("fiscal_year_end")

        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
            or value <= 0
        ):
            return {"valid": False, "reason": "Invalid annual cash flow"}

        try:
            reporting_date = date.fromisoformat(fiscal_end)
        except (TypeError, ValueError):
            return {"valid": False, "reason": "Invalid reporting date"}

        if reporting_date > date.today():
            return {"valid": False, "reason": "Future reporting date"}
        if previous_date is not None and not 330 <= (reporting_date - previous_date).days <= 400:
            return {"valid": False, "reason": "Annual records must be consecutive and unique"}
        previous_date = reporting_date
        operating = record.get("operating_cash_flow")
        purchases = record.get("productive_asset_purchases")
        if not all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in (operating, purchases)) or purchases < 0:
            return {"valid": False, "reason": "Invalid cash-flow components"}
        if not math.isclose(value, operating - purchases, rel_tol=1e-9, abs_tol=0.01):
            return {"valid": False, "reason": "Cash-flow proxy does not reconcile"}

        # Verify the annual operating cash-flow filing date.
        filed = record.get("operating_cash_flow_filed")
        if not filed:
            return {
                "valid": False,
                "reason": "Missing SEC cash-flow filing date",
            }

        try:
            filing_date = date.fromisoformat(filed)
        except (TypeError, ValueError):
            return {
                "valid": False,
                "reason": "Invalid SEC filing date",
            }

        if filing_date < reporting_date or filing_date > date.today():
            return {
                "valid": False,
                "reason": "Inconsistent SEC filing date",
            }

        # Both cash-flow components must come from the same SEC filing.
        operating_accession = record.get("operating_cash_flow_accession")
        purchases_accession = record.get("productive_asset_purchases_accession")
        purchases_filed = record.get("productive_asset_purchases_filed")

        if not operating_accession or not purchases_accession:
            return {
                "valid": False,
                "reason": "Missing SEC cash-flow accession numbers",
            }

        if operating_accession != purchases_accession:
            return {
                "valid": False,
                "reason": "Cash-flow components come from different SEC filings",
            }

        if purchases_filed != filed:
            return {
                "valid": False,
                "reason": "Cash-flow component filing dates do not match",
            }

        cash_flows.append(float(value))

    latest_date = date.fromisoformat(recent[-1]["fiscal_year_end"])

    if (date.today() - latest_date).days > 540:
        return {"valid": False, "reason": "Annual financial data is stale"}

    shares_record = balance.get("shares_outstanding") or {}
    shares = shares_record.get("value")

    if (
        not isinstance(shares, (int, float))
        or isinstance(shares, bool)
        or not math.isfinite(shares)
        or shares <= 0
    ):
        return {"valid": False, "reason": "Invalid shares outstanding"}

    try:
        shares_date = date.fromisoformat(shares_record.get("as_of"))
    except (TypeError, ValueError):
        return {"valid": False, "reason": "Missing shares reporting date"}

    if shares_date > date.today():
        return {"valid": False, "reason": "Future shares reporting date"}

    if (date.today() - shares_date).days > 540:
        return {"valid": False, "reason": "Share-count data is stale"}
    try:
        shares_filed = date.fromisoformat(shares_record.get("filed"))
    except (TypeError, ValueError):
        return {"valid": False, "reason": "Missing shares filing date"}
    if not shares_date <= shares_filed <= date.today():
        return {"valid": False, "reason": "Inconsistent shares filing date"}

    return {
        "valid": True,
        "cash_flow_history": cash_flows,
        "latest_cash_flow": cash_flows[-1],
        "shares_outstanding": float(shares),
        "latest_fiscal_year_end": latest_date.isoformat(),
        "shares_as_of": shares_date.isoformat(),
    }
