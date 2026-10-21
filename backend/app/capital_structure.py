"""Check SEC debt components for potential double-counting."""

import math


def check_debt_components(
    total_long_term_debt,
    current_long_term_debt,
    noncurrent_long_term_debt,
    commercial_paper,
):
    values = (
        total_long_term_debt,
        current_long_term_debt,
        noncurrent_long_term_debt,
        commercial_paper,
    )

    if not all(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
        for value in values
    ):
        return {
            "valid": False,
            "reason": "Missing or invalid debt components",
        }

    component_total = (
        current_long_term_debt + noncurrent_long_term_debt
    )

    difference = abs(total_long_term_debt - component_total)
    tolerance = max(total_long_term_debt * 0.01, 1_000_000)

    consistent = difference <= tolerance

    return {
        "valid": consistent,
        "reported_long_term_debt": total_long_term_debt,
        "component_total": component_total,
        "difference": difference,
        "commercial_paper": commercial_paper,
        "potential_total_debt": (
            total_long_term_debt + commercial_paper
            if consistent else None
        ),
        "warning": (
            "Debt reconciliation is a preliminary consistency check. "
            "Commercial paper classification and other financing "
            "liabilities require verification before valuation use."
        ),
    }


def assess_capital_structure(balance_sheet):
    """Validate filing consistency and calculate preliminary balances."""

    required = (
        "cash_and_equivalents",
        "marketable_securities_current",
        "marketable_securities_noncurrent",
        "long_term_debt_including_current",
        "long_term_debt_current",
        "long_term_debt_noncurrent",
        "commercial_paper",
    )

    records = {}
    for field in required:
        record = balance_sheet.get(field)
        if not isinstance(record, dict):
            return {"valid": False, "reason": f"Missing {field}"}

        value = record.get("value")
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
            or value < 0
        ):
            return {"valid": False, "reason": f"Invalid {field}"}

        records[field] = record

    dates = {r.get("as_of") for r in records.values()}
    accessions = {
        r.get("accn") or r.get("accession")
        for r in records.values()
    }

    if len(dates) != 1 or None in dates:
        return {"valid": False, "reason": "Reporting dates differ"}

    if len(accessions) != 1 or None in accessions:
        return {"valid": False, "reason": "SEC filings differ"}

    values = {key: record["value"] for key, record in records.items()}

    debt_check = check_debt_components(
        values["long_term_debt_including_current"],
        values["long_term_debt_current"],
        values["long_term_debt_noncurrent"],
        values["commercial_paper"],
    )

    if not debt_check["valid"]:
        return {
            "valid": False,
            "reason": "Debt components do not reconcile",
            "debt_check": debt_check,
        }

    financial_assets = (
        values["cash_and_equivalents"]
        + values["marketable_securities_current"]
        + values["marketable_securities_noncurrent"]
    )

    preliminary_debt = debt_check["potential_total_debt"]

    return {
        "valid": True,
        "as_of": next(iter(dates)),
        "accession": next(iter(accessions)),
        "financial_assets": financial_assets,
        "preliminary_debt": preliminary_debt,
        "preliminary_net_financial_assets": (
            financial_assets - preliminary_debt
        ),
        "debt_check": debt_check,
        "valuation_ready": False,
        "reason": (
            "SEC balances are internally consistent, but financing "
            "classification, excess cash, and FCFF/FCFE treatment "
            "are not yet validated."
        ),
    }
