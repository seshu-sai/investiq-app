from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, String, Numeric, DateTime, JSON, ForeignKey, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./investiq.db')
engine = create_engine(DATABASE_URL, connect_args={'check_same_thread': False} if DATABASE_URL.startswith('sqlite') else {}, pool_pre_ping=True)
Session = sessionmaker(bind=engine)

class Base(DeclarativeBase):
    pass

class SettingsRow(Base):
    __tablename__ = 'settings'
    id: Mapped[int] = mapped_column(primary_key=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal('5000'))
    currency: Mapped[str] = mapped_column(String(3), default='CAD')
    markets: Mapped[list] = mapped_column(JSON, default=lambda: ['IN','CA','US'])
    assets: Mapped[list] = mapped_column(JSON, default=lambda: ['stocks','funds','etfs'])
    risk: Mapped[str] = mapped_column(String(12), default='high')
    horizon: Mapped[str] = mapped_column(String(12), default='3-5')
    frequency: Mapped[str] = mapped_column(String(12), default='daily')

class WatchlistRow(Base):
    __tablename__ = 'watchlist'
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    market: Mapped[str] = mapped_column(String(2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class SettingsInput(BaseModel):
    amount: Decimal = Field(default=Decimal('5000'), gt=0, max_digits=18, decimal_places=2)
    currency: str = Field(default='CAD', pattern='^(CAD|USD|INR)$')
    markets: list[str] = Field(default_factory=lambda: ['IN','CA','US'], min_length=1)
    assets: list[str] = Field(default_factory=lambda: ['stocks','funds','etfs'], min_length=1)
    risk: str = Field(default='high', pattern='^(low|medium|high)$')
    horizon: str = Field(default='3-5', pattern=r'^(0-1|1-3|3-5|5\+)$')
    frequency: str = Field(default='daily', pattern='^(daily|weekly)$')

class WatchlistInput(BaseModel):
    symbol: str = Field(min_length=1, max_length=32, pattern=r'^[A-Za-z0-9.\-]+$')
    market: str = Field(pattern='^(IN|CA|US)$')

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)  # MVP only; use Alembic migrations before production
    yield

app = FastAPI(title='InvestIQ API', version='0.1.0', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.getenv('CORS_ORIGINS','http://localhost:5173').split(','), allow_credentials=False, allow_methods=['GET','POST','DELETE'], allow_headers=['Content-Type'])

@app.get('/api/health')
def health():
    return {'status':'ok', 'service':'investiq-api'}

@app.get('/api/settings', response_model=SettingsInput)
def get_settings():
    with Session() as db:
        row = db.get(SettingsRow, 1)
        if row is None:
            return SettingsInput()
        return SettingsInput.model_validate({k:getattr(row,k) for k in SettingsInput.model_fields})

@app.post('/api/settings', response_model=SettingsInput)
def save_settings(payload: SettingsInput):
    if any(x not in ('IN','CA','US') for x in payload.markets) or any(x not in ('stocks','funds','etfs') for x in payload.assets):
        raise HTTPException(422,'Unsupported market or asset')
    with Session.begin() as db:
        row = db.get(SettingsRow, 1)
        if row is None:
            row = SettingsRow(id=1)
            db.add(row)
        for key, value in payload.model_dump().items():
            setattr(row,key,value)
    return payload

@app.get('/api/watchlist')
def list_watchlist():
    with Session() as db:
        rows = db.scalars(select(WatchlistRow).order_by(WatchlistRow.id.desc())).all()
        return [{'id':r.id,'symbol':r.symbol,'market':r.market} for r in rows]

@app.post('/api/watchlist', status_code=201)
def add_watchlist(payload: WatchlistInput):
    with Session.begin() as db:
        row = WatchlistRow(symbol=payload.symbol.upper(), market=payload.market)
        db.add(row)
        db.flush()
        return {'id':row.id,'symbol':row.symbol,'market':row.market}

@app.delete('/api/watchlist/{item_id}', status_code=204)
def delete_watchlist(item_id: int):
    with Session.begin() as db:
        row = db.get(WatchlistRow,item_id)
        if row is None:
            raise HTTPException(404,'Not found')
        db.delete(row)

@app.get('/api/research/{market}/{symbol}')
def research(market: str, symbol: str):
    if market not in ('IN','CA','US'):
        raise HTTPException(422,'Unsupported market')
    if market in ('IN', 'CA'):
        from .international import MarketDataError, get_international_research

        try:
            return get_international_research(market, symbol)
        except MarketDataError as exc:
            raise HTTPException(
                status_code=503,
                detail=str(exc)
            ) from exc

    from .finnhub import FinnhubError, get_research

    try:
        return get_research(symbol.upper())
    except FinnhubError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc)
        ) from exc


@app.get('/api/analysis/{market}/{symbol}')
def investment_analysis(market: str, symbol: str):
    from .fundamentals import FundamentalsError, get_fundamentals
    from .trajectory import calculate_trajectory

    if market not in ('US', 'IN', 'CA'):
        raise HTTPException(status_code=422, detail='Unsupported market')

    try:
        fundamentals = get_fundamentals(market, symbol)
    except FundamentalsError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc)
        ) from exc

    eps = fundamentals.get('trailing_eps')
    pe = fundamentals.get('trailing_pe')

    # Derive an indicative current price from EPS and P/E.
    # This is not necessarily the latest traded price.
    indicative_price = eps * pe if eps and pe else None

    if indicative_price is None:
        trajectory = {
            'status': 'insufficient_data',
            'assessment': 'Insufficient data',
            'scenarios': [],
            'reason': 'Positive EPS and trailing P/E are required.',
        }
    else:
        trajectory = calculate_trajectory(
            current_price=indicative_price,
            trailing_eps=eps,
            current_pe=pe,
            years=3,
        )

    return {
        'market': market,
        'symbol': fundamentals['symbol'],
        'fundamentals': fundamentals,
        'trajectory': trajectory,
        'message': (
            'Illustrative valuation scenarios based on reported '
            'fundamentals and assumed earnings growth. '
            'Not a personalized investment recommendation.'
        ),
    }


@app.get('/api/ai-analysis/{market}/{symbol}')
def ai_investment_analysis(market: str, symbol: str):
    from .ai_research import analyze_stock_with_ai

    if market not in ('US', 'IN', 'CA'):
        raise HTTPException(status_code=422, detail='Unsupported market')

    analysis = investment_analysis(market, symbol)
    research_data = research(market, symbol)

    from .fundamentals import get_historical_financials, FundamentalsError

    try:
        historical_financials = get_historical_financials(market, symbol)
    except FundamentalsError:
        historical_financials = {}

    if market == 'US':
        from .sec_filings import (
            SECDataError,
            get_sec_annual_financials,
            lookup_sec_cik,
        )
        try:
            cik = lookup_sec_cik(symbol)
            historical_financials = get_sec_annual_financials(cik)
        except SECDataError:
            # Retain clearly labeled Yahoo Finance data if SEC is unavailable.
            pass

    try:
        ai_summary = analyze_stock_with_ai(
            market=market,
            symbol=analysis['symbol'],
            fundamentals=analysis['fundamentals'],
            trajectory=analysis['trajectory'],
            news=research_data.get('sources', []),
            quote=research_data.get('quote'),
            historical_financials=historical_financials,
        )
    except Exception:
        # Avoid exposing API keys or provider internals in error responses.
        raise HTTPException(
            status_code=503,
            detail='AI analysis is temporarily unavailable. Check backend logs.',
        )

    return {
        'market': market,
        'symbol': analysis['symbol'],
        'ai_summary': ai_summary,
        'fundamentals': analysis['fundamentals'],
        'trajectory': analysis['trajectory'],
        'sources': research_data.get('sources', [])[:5],
        'disclaimer': (
            'AI-generated research based on available data. '
            'Not personalized financial advice or a guarantee of returns.'
        ),
    }



@app.get('/api/valuation/{market}/{symbol}')
def stock_valuation(market: str, symbol: str):
    from .sec_filings import SECDataError, lookup_sec_cik, get_sec_annual_financials
    from .valuation import ValuationError, calculate_cash_flow_valuation

    if market != 'US':
        raise HTTPException(
            status_code=422,
            detail='SEC-based valuation currently supports US stocks only.',
        )

    try:
        cik = lookup_sec_cik(symbol.upper())
        financials = get_sec_annual_financials(cik)

        history = financials.get('history') or []
        balance_sheet = financials.get('balance_sheet') or {}

        if not history:
            raise HTTPException(
                status_code=422,
                detail='No SEC annual cash-flow history available.',
            )

        latest = history[-1]
        cash_flow = latest.get('cash_after_productive_asset_purchases')
        shares_record = balance_sheet.get('shares_outstanding') or {}
        shares = shares_record.get('value')

        if not isinstance(cash_flow, (int, float)) or cash_flow <= 0:
            raise HTTPException(
                status_code=422,
                detail='Positive SEC cash-flow proxy is unavailable.',
            )

        if not isinstance(shares, (int, float)) or shares <= 0:
            raise HTTPException(
                status_code=422,
                detail='Valid SEC shares outstanding are unavailable.',
            )

        scenarios = []
        for name, growth, discount in [
            ('Conservative', 0.00, 0.12),
            ('Moderate', 0.05, 0.10),
            ('Optimistic', 0.10, 0.08),
        ]:
            result = calculate_cash_flow_valuation(
                annual_cash_flow=cash_flow,
                shares_outstanding=shares,
                growth_rate=growth,
                discount_rate=discount,
                terminal_growth_rate=0.02,
                years=5,
                net_financial_assets=0,
                margin_of_safety=0.25,
            )

            explicit_pv = sum(
                item['present_value']
                for item in result['projected_cash_flows']
            )
            total_value = result['fair_value_per_share'] * shares
            terminal_share = (
                (total_value - explicit_pv) / total_value
                if total_value > 0 else None
            )

            scenarios.append({
                'name': name,
                'illustrative_value_per_share_usd': result['fair_value_per_share'],
                'illustrative_25pct_buffer_usd': result['margin_of_safety_price'],
                'terminal_value_share_approx': (
                    round(terminal_share, 4)
                    if terminal_share is not None else None
                ),
                'assumptions': result['assumptions'],
            })

        return {
            'market': market,
            'symbol': symbol.upper(),
            'status': 'illustrative_only',
            'currency': 'USD',
            'sec_inputs': {
                'cash_flow_proxy_usd': cash_flow,
                'cash_flow_fiscal_year_end': latest.get('fiscal_year_end'),
                'cash_flow_filed': latest.get('operating_cash_flow_filed'),
                'shares_outstanding': shares,
                'shares_as_of': shares_record.get('as_of'),
                'shares_filed': shares_record.get('filed'),
            },
            'scenarios': scenarios,
            'limitations': (
                'Illustrative sensitivity analysis, not a validated intrinsic '
                'value or investment recommendation. Cash flow after productive '
                'asset purchases is not fully adjusted FCFE or FCFF. '
                'Growth, discount, and terminal rates are hypothetical. '
                'No net-financial-assets adjustment is included. '
                'Share-count timing, dilution, financing flows, and other '
                'equity adjustments require further validation.'
            ),
        }

    except HTTPException:
        raise
    except (SECDataError, ValuationError) as exc:
        raise HTTPException(
            status_code=503,
            detail='SEC-based valuation inputs are unavailable or invalid.',
        ) from exc


@app.get('/api/stocks/search')
def stock_search(q: str = '', market: str = 'US'):
    """Return stock suggestions for the selected market."""
    if market not in ('US', 'CA', 'IN'):
        raise HTTPException(status_code=400, detail='Unsupported market')

    if len(q.strip()) < 2:
        return []

    if market in ('CA', 'IN'):
        from app.international import search_international_stocks, MarketDataError

        try:
            return search_international_stocks(market, q)
        except MarketDataError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    from app.finnhub import search_stocks, FinnhubError

    try:
        return search_stocks(q)
    except FinnhubError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
