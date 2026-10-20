"""Official SEC annual financial history for US-listed companies."""

import datetime as dt
import os

import httpx


class SECDataError(Exception):
    pass


def get_sec_annual_financials(cik: int) -> dict:
    """Return annual revenue and net income from SEC company facts."""
    user_agent = os.getenv("SEC_USER_AGENT")
    if not user_agent:
        raise SECDataError("SEC_USER_AGENT must contain a real contact identity")

    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

    try:
        response = httpx.get(
            url,
            headers={
                "User-Agent": user_agent,
                "Accept-Encoding": "gzip, deflate",
            },
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise SECDataError("Unable to retrieve SEC company facts") from exc

    facts = data.get("facts", {}).get("us-gaap", {})
    today = dt.date.today().isoformat()

    def annual_records(tags):
        records = {}

        for tag in tags:
            for item in facts.get(tag, {}).get("units", {}).get("USD", []):
                start = item.get("start")
                end = item.get("end")
                filed = item.get("filed")

                if not start or not end or not filed:
                    continue
                if item.get("form") != "10-K" or filed > today:
                    continue

                try:
                    days = (
                        dt.date.fromisoformat(end)
                        - dt.date.fromisoformat(start)
                    ).days
                except ValueError:
                    continue

                if not 330 <= days <= 380:
                    continue

                value = item.get("val")
                if not isinstance(value, (int, float)):
                    continue

                record = {
                    "value": value,
                    "filed": filed,
                    "accession": item.get("accn"),
                    "tag": tag,
                }

                previous = records.get(end)
                if previous is None or filed < previous["filed"]:
                    records[end] = record

        return records

    def latest_instant_record(namespace, tag, unit):
        """Find the latest reported balance or share count."""
        records = data.get("facts", {}).get(namespace, {}).get(
            tag, {}
        ).get("units", {}).get(unit, [])

        eligible = [
            item for item in records
            if (
                item.get("form") in ("10-K", "10-Q")
                and item.get("filed", "") <= today
                and item.get("end")
                and not item.get("start")
                and isinstance(item.get("val"), (int, float))
            )
        ]

        if not eligible:
            return None

        # Prefer the latest measurement date, then the earliest
        # filing for that date to avoid silently using restatements.
        latest_date = max(item["end"] for item in eligible)
        matching = [
            item for item in eligible
            if item["end"] == latest_date
        ]
        item = min(matching, key=lambda x: x["filed"])

        return {
            "value": item["val"],
            "as_of": item["end"],
            "filed": item["filed"],
            "accession": item.get("accn"),
            "tag": f"{namespace}:{tag}",
        }

    balance_sheet = {
        "shares_outstanding": (
            latest_instant_record(
                "dei", "EntityCommonStockSharesOutstanding", "shares"
            )
            or latest_instant_record(
                "us-gaap", "CommonStockSharesOutstanding", "shares"
            )
        ),
        "cash_and_equivalents": latest_instant_record(
            "us-gaap", "CashAndCashEquivalentsAtCarryingValue", "USD"
        ),
        "current_marketable_debt_securities": latest_instant_record(
            "us-gaap", "DebtSecuritiesCurrent", "USD"
        ),
        "long_term_debt_including_current": latest_instant_record(
            "us-gaap", "LongTermDebt", "USD"
        ),
    }

    revenues = annual_records([
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
    ])
    earnings = annual_records(["NetIncomeLoss"])
    operating_cash_flows = annual_records([
        "NetCashProvidedByUsedInOperatingActivities",
    ])
    productive_asset_purchases = annual_records([
        "PaymentsToAcquireProductiveAssets",
        "PaymentsToAcquirePropertyPlantAndEquipment",
    ])

    history = []
    for year_end in sorted(revenues)[-5:]:
        revenue = revenues[year_end]
        income = earnings.get(year_end)
        operating_cash = operating_cash_flows.get(year_end)
        asset_purchases = productive_asset_purchases.get(year_end)

        cash_after_purchases = (
            operating_cash["value"] - asset_purchases["value"]
            if operating_cash is not None and asset_purchases is not None
            else None
        )

        history.append({
            "fiscal_year_end": year_end,
            "revenue": revenue["value"],
            "revenue_filed": revenue["filed"],
            "revenue_accession": revenue["accession"],
            "net_income": income["value"] if income else None,
            "net_income_filed": income["filed"] if income else None,
            "operating_cash_flow": (
                operating_cash["value"] if operating_cash else None
            ),
            "productive_asset_purchases": (
                asset_purchases["value"] if asset_purchases else None
            ),
            "cash_after_productive_asset_purchases": cash_after_purchases,
            "operating_cash_flow_filed": (
                operating_cash["filed"] if operating_cash else None
            ),
            "productive_asset_purchases_filed": (
                asset_purchases["filed"] if asset_purchases else None
            ),
        })

    for index, record in enumerate(history):
        record["revenue_growth_yoy"] = None
        if index > 0:
            previous = history[index - 1]["revenue"]
            if previous > 0:
                record["revenue_growth_yoy"] = round(
                    (record["revenue"] / previous - 1) * 100, 2
                )

    if not history:
        raise SECDataError("No annual SEC financial records found")

    return {
        "company": data.get("entityName"),
        "cik": cik,
        "source": "SEC EDGAR companyfacts",
        "period_type": "annual",
        "balance_sheet": balance_sheet,
        "history": history,
    }


def lookup_sec_cik(symbol: str) -> int:
    """Resolve a US stock ticker to its SEC CIK."""
    import re

    ticker = symbol.strip().upper()
    if not re.fullmatch(r"[A-Z0-9.\-]{1,32}", ticker):
        raise SECDataError("Invalid stock ticker")

    user_agent = os.getenv("SEC_USER_AGENT")
    if not user_agent:
        raise SECDataError("SEC_USER_AGENT must contain a real contact identity")

    try:
        response = httpx.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers={"User-Agent": user_agent},
            timeout=20,
        )
        response.raise_for_status()
        companies = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise SECDataError("Unable to retrieve SEC ticker directory") from exc

    for company in companies.values():
        if company.get("ticker", "").upper() == ticker:
            return int(company["cik_str"])

    raise SECDataError(f"No SEC CIK found for {ticker}")
