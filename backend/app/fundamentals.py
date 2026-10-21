import math
import re

import yfinance as yf
from datetime import date, datetime, timezone

from .data_utils import finite_number, normalize_symbol, ttl_cache


class FundamentalsError(Exception):
    pass


@ttl_cache(300)
def get_fundamentals(market: str, symbol: str):
    if market not in ("US", "IN", "CA"):
        raise FundamentalsError("Unsupported market")

    ticker_symbol = normalize_symbol(market, symbol)

    if not re.fullmatch(r"[A-Z0-9.\-]{1,32}", ticker_symbol):
        raise FundamentalsError("Invalid ticker symbol")

    if market == "IN" and not ticker_symbol.endswith((".NS", ".BO")):
        ticker_symbol += ".NS"
    elif market == "CA" and not ticker_symbol.endswith((".TO", ".V")):
        ticker_symbol += ".TO"

    try:
        info = yf.Ticker(ticker_symbol.replace(".", "-") if market == "US" else ticker_symbol).info

        if not isinstance(info, dict) or not info:
            raise FundamentalsError("No company fundamentals available")

        def positive_number(value):
            result = finite_number(value)
            return result if result is not None and result > 0 else None

        return {
            "symbol": ticker_symbol,
            "company": info.get("longName") or info.get("shortName"),
            "currency": info.get("currency"),
            "trailing_eps": finite_number(info.get("trailingEps")),
            "trailing_pe": positive_number(info.get("trailingPE")),
            "market_cap": positive_number(info.get("marketCap")),
            "revenue_growth": finite_number(info.get("revenueGrowth")),
            "revenue_growth_period": "Provider-reported; reporting period not verified",
            "earnings_report_date": None,
            "profit_margin": finite_number(info.get("profitMargins")),
            "total_debt": finite_number(info.get("totalDebt")),
            "total_cash": finite_number(info.get("totalCash")),
            "sector": info.get("sector"),
            "financial_currency": info.get("financialCurrency"),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "provider": "Yahoo Finance (unofficial)",
            "data_freshness": "Fundamental reporting dates are not verified",
        }

    except FundamentalsError:
        raise
    except Exception as exc:
        raise FundamentalsError(
            f"Unable to retrieve fundamentals for {ticker_symbol}"
        ) from exc


@ttl_cache(300)
def get_historical_financials(market: str, symbol: str) -> dict:
    """Retrieve annual financial history and calculate revenue growth."""
    import pandas as pd

    if market not in ("US", "CA", "IN"):
        raise FundamentalsError("Unsupported market")

    ticker_symbol = normalize_symbol(market, symbol)

    if not re.fullmatch(r"[A-Z0-9.\-]{1,32}", ticker_symbol):
        raise FundamentalsError("Invalid ticker symbol")

    if market == "IN" and not ticker_symbol.endswith((".NS", ".BO")):
        ticker_symbol += ".NS"
    elif market == "CA" and not ticker_symbol.endswith((".TO", ".V")):
        ticker_symbol += ".TO"

    try:
        ticker = yf.Ticker(ticker_symbol.replace(".", "-") if market == "US" else ticker_symbol)
        statement = ticker.income_stmt
        try:
            cash_statement = ticker.cashflow
        except Exception:
            cash_statement = pd.DataFrame()

        if statement.empty or "Total Revenue" not in statement.index:
            raise FundamentalsError("Historical revenue unavailable")

        records = []

        for period in sorted(statement.columns):
            revenue = statement.at["Total Revenue", period]

            if pd.isna(revenue) or not math.isfinite(float(revenue)) or float(revenue) <= 0:
                continue

            def metric(name):
                if name not in statement.index:
                    return None
                value = statement.at[name, period]
                return None if pd.isna(value) else finite_number(float(value))

            def cash_metric(name):
                if name not in cash_statement.index or period not in cash_statement.columns:
                    return None
                value = cash_statement.at[name, period]
                return None if pd.isna(value) else finite_number(float(value))

            operating = cash_metric("Operating Cash Flow")
            capex = cash_metric("Capital Expenditure")
            # Yahoo normally reports capex as a negative cash outflow. Never guess reversed signs.
            purchases = -capex if capex is not None and capex <= 0 else None

            records.append({
                "fiscal_year_end": period.strftime("%Y-%m-%d"),
                "revenue": float(revenue),
                "net_income": metric("Net Income"),
                "diluted_eps": metric("Diluted EPS"),
                "operating_cash_flow": operating,
                "productive_asset_purchases": purchases,
                "cash_after_productive_asset_purchases": operating - purchases if operating is not None and purchases is not None else None,
                "cash_flow_definition": "Operating cash flow minus provider-reported capital expenditure outflows; unofficial proxy",
            })

        if not records:
            raise FundamentalsError("No valid historical revenue records")

        for index, record in enumerate(records):
            record["revenue_growth_yoy"] = None

            if index > 0:
                previous = records[index - 1]["revenue"]
                interval = (date.fromisoformat(record["fiscal_year_end"]) - date.fromisoformat(records[index - 1]["fiscal_year_end"])).days
                if previous > 0 and 330 <= interval <= 400:
                    record["revenue_growth_yoy"] = round(
                        (record["revenue"] / previous - 1) * 100, 2
                    )

        return {
            "symbol": ticker_symbol,
            "source": "Yahoo Finance (unofficial)",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "period_type": "annual",
            "history": records[-5:],
        }

    except FundamentalsError:
        raise
    except Exception as exc:
        raise FundamentalsError(
            f"Unable to retrieve historical financials for {ticker_symbol}"
        ) from exc
