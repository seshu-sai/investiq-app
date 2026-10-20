import math
import re

import yfinance as yf


class FundamentalsError(Exception):
    pass


def get_fundamentals(market: str, symbol: str):
    if market not in ("US", "IN", "CA"):
        raise FundamentalsError("Unsupported market")

    ticker_symbol = symbol.strip().upper()

    if not re.fullmatch(r"[A-Z0-9.\-]{1,32}", ticker_symbol):
        raise FundamentalsError("Invalid ticker symbol")

    if market == "IN" and not ticker_symbol.endswith((".NS", ".BO")):
        ticker_symbol += ".NS"
    elif market == "CA" and not ticker_symbol.endswith((".TO", ".V")):
        ticker_symbol += ".TO"

    try:
        info = yf.Ticker(ticker_symbol).info

        if not isinstance(info, dict) or not info:
            raise FundamentalsError("No company fundamentals available")

        def positive_number(value):
            try:
                result = float(value)
                return result if math.isfinite(result) and result > 0 else None
            except (TypeError, ValueError):
                return None

        return {
            "symbol": ticker_symbol,
            "company": info.get("longName") or info.get("shortName"),
            "currency": info.get("currency"),
            "trailing_eps": positive_number(info.get("trailingEps")),
            "trailing_pe": positive_number(info.get("trailingPE")),
            "market_cap": positive_number(info.get("marketCap")),
            "revenue_growth": info.get("revenueGrowth"),
            "revenue_growth_period": "Provider-reported; reporting period not verified",
            "earnings_report_date": None,
            "profit_margin": info.get("profitMargins"),
            "total_debt": info.get("totalDebt"),
            "total_cash": info.get("totalCash"),
            "provider": "Yahoo Finance (unofficial)",
            "data_freshness": "Fundamental reporting dates are not verified",
        }

    except FundamentalsError:
        raise
    except Exception as exc:
        raise FundamentalsError(
            f"Unable to retrieve fundamentals for {ticker_symbol}"
        ) from exc


def get_historical_financials(market: str, symbol: str) -> dict:
    """Retrieve annual financial history and calculate revenue growth."""
    import pandas as pd

    if market not in ("US", "CA", "IN"):
        raise FundamentalsError("Unsupported market")

    ticker_symbol = symbol.strip().upper()

    if not re.fullmatch(r"[A-Z0-9.\-]{1,32}", ticker_symbol):
        raise FundamentalsError("Invalid ticker symbol")

    if market == "IN" and not ticker_symbol.endswith((".NS", ".BO")):
        ticker_symbol += ".NS"
    elif market == "CA" and not ticker_symbol.endswith((".TO", ".V")):
        ticker_symbol += ".TO"

    try:
        statement = yf.Ticker(ticker_symbol).income_stmt

        if statement.empty or "Total Revenue" not in statement.index:
            raise FundamentalsError("Historical revenue unavailable")

        records = []

        for date in sorted(statement.columns):
            revenue = statement.at["Total Revenue", date]

            if pd.isna(revenue) or float(revenue) <= 0:
                continue

            def metric(name):
                if name not in statement.index:
                    return None
                value = statement.at[name, date]
                return None if pd.isna(value) else float(value)

            records.append({
                "fiscal_year_end": date.strftime("%Y-%m-%d"),
                "revenue": float(revenue),
                "net_income": metric("Net Income"),
                "diluted_eps": metric("Diluted EPS"),
            })

        if not records:
            raise FundamentalsError("No valid historical revenue records")

        for index, record in enumerate(records):
            record["revenue_growth_yoy"] = None

            if index > 0:
                previous = records[index - 1]["revenue"]
                if previous > 0:
                    record["revenue_growth_yoy"] = round(
                        (record["revenue"] / previous - 1) * 100, 2
                    )

        return {
            "symbol": ticker_symbol,
            "source": "Yahoo Finance (unofficial)",
            "period_type": "annual",
            "history": records[-5:],
        }

    except FundamentalsError:
        raise
    except Exception as exc:
        raise FundamentalsError(
            f"Unable to retrieve historical financials for {ticker_symbol}"
        ) from exc
