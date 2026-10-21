"""Official SEC annual financial history for US-listed companies."""

import datetime as dt
import os

import httpx

from .data_utils import finite_number, ttl_cache


class SECDataError(Exception):
    pass


@ttl_cache(300)
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

    if not isinstance(data, dict) or not isinstance(data.get("facts"), dict):
        raise SECDataError("Invalid SEC company facts")
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
                if item.get("form") not in ("10-K", "10-K/A") or not end <= filed <= today:
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
                if finite_number(value) is None:
                    continue

                record = {
                    "value": value,
                    "filed": filed,
                    "accession": item.get("accn"),
                    "tag": tag,
                    "start": start,
                }

                previous = records.get(end)
                if previous is None or filed > previous["filed"]:
                    records[end] = record

        return records

    def matching_annual_records(tags, reference_records, unit="USD"):
        """Select annual values from the same filing as reference records."""
        matches = {}

        for year_end, reference in reference_records.items():
            accession = reference.get("accession")
            filed = reference.get("filed")

            if not accession or not filed:
                continue

            for tag in tags:
                items = facts.get(tag, {}).get("units", {}).get(unit, [])

                for item in items:
                    if (
                        item.get("form") not in ("10-K", "10-K/A")
                        or item.get("end") != year_end
                        or item.get("accn") != accession
                        or item.get("filed") != filed
                        or item.get("filed") > today
                        or item.get("start") != reference.get("start")
                        or finite_number(item.get("val")) is None
                    ):
                        continue

                    try:
                        duration = (
                            dt.date.fromisoformat(item["end"])
                            - dt.date.fromisoformat(item["start"])
                        ).days
                    except (KeyError, TypeError, ValueError):
                        continue

                    if not 330 <= duration <= 380:
                        continue

                    matches[year_end] = {
                        "value": item["val"],
                        "filed": filed,
                        "accession": accession,
                        "tag": tag,
                        "start": item["start"],
                    }
                    break

                if year_end in matches:
                    break

        return matches

    def latest_instant_record(namespace, tag, unit):
        """Find the latest reported balance or share count."""
        records = data.get("facts", {}).get(namespace, {}).get(
            tag, {}
        ).get("units", {}).get(unit, [])

        eligible = [
            item for item in records
            if (
                item.get("form") in ("10-K", "10-Q", "10-K/A", "10-Q/A")
                and item.get("end")
                and item["end"] <= item.get("filed", "") <= today
                and not item.get("start")
                and finite_number(item.get("val")) is not None
            )
        ]

        if not eligible:
            return None

        # Current research uses the latest available filing, including restatements.
        latest_date = max(item["end"] for item in eligible)
        matching = [
            item for item in eligible
            if item["end"] == latest_date
        ]
        item = max(matching, key=lambda x: x["filed"])

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
        "marketable_securities_current": latest_instant_record(
            "us-gaap", "MarketableSecuritiesCurrent", "USD"
        ),
        "marketable_securities_noncurrent": latest_instant_record(
            "us-gaap", "MarketableSecuritiesNoncurrent", "USD"
        ),
        "long_term_debt_current": latest_instant_record(
            "us-gaap", "LongTermDebtCurrent", "USD"
        ),
        "long_term_debt_noncurrent": latest_instant_record(
            "us-gaap", "LongTermDebtNoncurrent", "USD"
        ),
        "commercial_paper": latest_instant_record(
            "us-gaap", "CommercialPaper", "USD"
        ),
    }

    revenues = annual_records([
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ])
    earnings = matching_annual_records(["NetIncomeLoss"], revenues)
    diluted_eps = matching_annual_records(["EarningsPerShareDiluted"], revenues, "USD/shares")
    operating_cash_flows = matching_annual_records([
        "NetCashProvidedByUsedInOperatingActivities",
    ], revenues)
    productive_asset_purchases = matching_annual_records(
        [
            "PaymentsToAcquireProductiveAssets",
            "PaymentsToAcquirePropertyPlantAndEquipment",
        ],
        operating_cash_flows,
    )

    history = []
    for year_end in sorted(revenues)[-5:]:
        revenue = revenues[year_end]
        income = earnings.get(year_end)
        operating_cash = operating_cash_flows.get(year_end)
        asset_purchases = productive_asset_purchases.get(year_end)

        cash_after_purchases = (
            operating_cash["value"] - asset_purchases["value"]
            if operating_cash is not None and asset_purchases is not None
            and asset_purchases["value"] >= 0
            else None
        )

        history.append({
            "fiscal_year_end": year_end,
            "revenue": revenue["value"],
            "revenue_filed": revenue["filed"],
            "revenue_accession": revenue["accession"],
            "fiscal_year_start": revenue["start"],
            "net_income": income["value"] if income else None,
            "diluted_eps": diluted_eps[year_end]["value"] if year_end in diluted_eps else None,
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
            "operating_cash_flow_accession": (
                operating_cash["accession"] if operating_cash else None
            ),
            "productive_asset_purchases_filed": (
                asset_purchases["filed"] if asset_purchases else None
            ),
            "productive_asset_purchases_accession": (
                asset_purchases["accession"] if asset_purchases else None
            ),
        })

    for index, record in enumerate(history):
        record["revenue_growth_yoy"] = None
        if index > 0:
            previous = history[index - 1]["revenue"]
            interval = (dt.date.fromisoformat(record["fiscal_year_end"]) - dt.date.fromisoformat(history[index - 1]["fiscal_year_end"])).days
            if previous > 0 and 330 <= interval <= 400:
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
        "currency": "USD",
        "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "revision_policy": "Latest available filing for each period; not point-in-time backtest data",
        "balance_sheet": balance_sheet,
        "history": history,
    }


@ttl_cache(86400, maxsize=1)
def _ticker_directory() -> dict:
    user_agent = os.getenv("SEC_USER_AGENT")
    if not user_agent:
        raise SECDataError("SEC_USER_AGENT must contain a real contact identity")
    try:
        response = httpx.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers={"User-Agent": user_agent}, timeout=20,
        )
        response.raise_for_status()
        companies = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise SECDataError("Unable to retrieve SEC ticker directory") from exc
    if not isinstance(companies, dict):
        raise SECDataError("Invalid SEC ticker directory")
    return companies


@ttl_cache(86400)
def lookup_sec_cik(symbol: str) -> int:
    """Resolve a ticker; SEC uses hyphens for share classes such as BRK-B."""
    import re
    ticker = symbol.strip().upper().replace(".", "-")
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9\-]{0,31}", ticker):
        raise SECDataError("Invalid stock ticker")
    for company in _ticker_directory().values():
        if isinstance(company, dict) and company.get("ticker", "").upper() == ticker:
            try:
                return int(company["cik_str"])
            except (ValueError, TypeError, KeyError) as exc:
                raise SECDataError("Invalid SEC CIK") from exc
    raise SECDataError(f"No SEC CIK found for {ticker}")
