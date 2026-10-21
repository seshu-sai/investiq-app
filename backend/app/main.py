from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import create_engine, String, Numeric, DateTime, JSON, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .data_utils import normalize_symbol

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

class ResearchRunRow(Base):
    __tablename__ = 'research_runs'
    id: Mapped[int] = mapped_column(primary_key=True)
    market: Mapped[str] = mapped_column(String(2))
    symbol: Mapped[str] = mapped_column(String(40), index=True)
    decision: Mapped[str] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    snapshot: Mapped[dict] = mapped_column(JSON)


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

@app.middleware('http')
async def api_cache_policy(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response


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
    symbol = checked_symbol(payload.market, payload.symbol)
    with Session.begin() as db:
        existing = db.scalar(select(WatchlistRow).where(WatchlistRow.symbol == symbol, WatchlistRow.market == payload.market))
        if existing:
            return {'id': existing.id, 'symbol': existing.symbol, 'market': existing.market}
        row = WatchlistRow(symbol=symbol, market=payload.market)
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
    symbol = checked_symbol(market, symbol)
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


def checked_symbol(market: str, symbol: str) -> str:
    try:
        return normalize_symbol(market, symbol)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get('/api/analysis/{market}/{symbol}')
def investment_analysis(market: str, symbol: str):
    from .research_service import collect_snapshot
    symbol = checked_symbol(market, symbol)
    snapshot = collect_snapshot(market, symbol, include_history=False)
    return {**snapshot, 'message': 'Hypothetical sensitivity scenarios using a provider quote. Assumptions are not forecasts.'}


@app.get('/api/ai-analysis/{market}/{symbol}')
def ai_investment_analysis(market: str, symbol: str, owns_position: bool = False):
    from .ai_research import analyze_stock_with_ai
    from .advisor import assess_evidence
    from .research_service import collect_snapshot

    symbol = checked_symbol(market, symbol)
    profile = get_settings().model_dump(mode='json')
    snapshot = collect_snapshot(market, symbol)
    assessment = assess_evidence(market, symbol, snapshot['fundamentals'],
                                 snapshot['historical_financials'], snapshot['quote'], profile, owns_position)
    assessment['warnings'].extend(snapshot['warnings'])
    summary = analyze_stock_with_ai(
        market, symbol, snapshot['fundamentals'], snapshot['trajectory'], snapshot['sources'],
        quote=snapshot['quote'], historical_financials=snapshot['historical_financials'],
        investor_profile=profile, owns_position=owns_position, assessment=assessment,
    )
    result = {**snapshot, 'ai_summary': summary, 'assessment': assessment,
              'generated_at': assessment['generated_at'],
              'disclaimer': 'Research based on available evidence and saved preferences. Portfolio suitability is incomplete. No guarantee of returns.'}
    with Session.begin() as db:
        run = ResearchRunRow(market=market, symbol=symbol, decision=summary['decision'],
                             snapshot={'profile': profile, 'result': result})
        db.add(run)
        db.flush()
        result['analysis_id'] = run.id
    return result


@app.get('/api/analysis-history/{market}/{symbol}')
def analysis_history(market: str, symbol: str):
    symbol = checked_symbol(market, symbol)
    with Session() as db:
        runs = db.scalars(select(ResearchRunRow).where(
            ResearchRunRow.market == market, ResearchRunRow.symbol == symbol
        ).order_by(ResearchRunRow.id.desc()).limit(10)).all()
        return [{'id': run.id, 'decision': run.decision, 'created_at': run.created_at,
                 'snapshot': run.snapshot} for run in runs]


class ValuationOptions(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    amount: float | None = Field(default=None, gt=0, le=1_000_000_000_000, allow_inf_nan=False)
    annual_goal: float | None = Field(default=None, gt=0, le=100, allow_inf_nan=False)
    max_loss: float | None = Field(default=None, gt=0, le=100, allow_inf_nan=False)
    cost_basis: float | None = Field(default=None, gt=0, le=1_000_000_000, allow_inf_nan=False)
    shares: float | None = Field(default=None, gt=0, le=1_000_000_000_000, allow_inf_nan=False)

    @model_validator(mode='after')
    def paired_position(self):
        if (self.cost_basis is None) != (self.shares is None):
            raise ValueError('Supply both average buy price and shares owned to calculate unrealized gains')
        return self


def valuation_result(market, symbol, options):
    from .valuation_service import valuation_snapshot
    symbol = checked_symbol(market, symbol)
    profile = get_settings().model_dump(mode='json')
    values = options.model_dump(exclude_none=True)
    if 'amount' in values:
        profile['amount'] = values.pop('amount')
    return valuation_snapshot(market, symbol, profile, **values)


@app.get('/api/valuation/{market}/{symbol}')
def stock_valuation(
    market: str, symbol: str,
    amount: float | None = Query(default=None, gt=0, le=1_000_000_000_000, allow_inf_nan=False),
    annual_goal: float | None = Query(default=None, gt=0, le=100, allow_inf_nan=False),
    max_loss: float | None = Query(default=None, gt=0, le=100, allow_inf_nan=False),
    cost_basis: float | None = Query(default=None, gt=0, le=1_000_000_000, allow_inf_nan=False),
    shares: float | None = Query(default=None, gt=0, le=1_000_000_000_000, allow_inf_nan=False),
):
    if (cost_basis is None) != (shares is None):
        raise HTTPException(422, 'Supply both average buy price and shares owned')
    options = ValuationOptions(amount=amount, annual_goal=annual_goal, max_loss=max_loss, cost_basis=cost_basis, shares=shares)
    return valuation_result(market, symbol, options)


@app.post('/api/valuation/{market}/{symbol}/research')
def valuation_web_research(market: str, symbol: str, options: ValuationOptions):
    from .web_research import research_valuation
    result = research_valuation(valuation_result(market, symbol, options))
    with Session.begin() as db:
        run = ResearchRunRow(market=market, symbol=result['symbol'], decision=result['buy_assessment']['verdict'],
                             snapshot={'profile': result['preferences'], 'valuation': result})
        db.add(run)
        db.flush()
        result['analysis_id'] = run.id
    return result


@app.get('/api/cash-flow-valuation/{market}/{symbol}')
def cash_flow_valuation(market: str, symbol: str):
    from .sec_filings import SECDataError, lookup_sec_cik, get_sec_annual_financials
    from .valuation import ValuationError, calculate_cash_flow_valuation
    from .financial_validation import validate_financial_evidence
    from .growth_analysis import analyze_cash_flow_growth
    from .growth_scenarios import build_growth_scenarios
    from .valuation_risk import assess_valuation_risk
    from .capital_structure import assess_capital_structure

    symbol = checked_symbol(market, symbol)
    if market != 'US':
        raise HTTPException(
            status_code=422,
            detail='SEC-based valuation currently supports US stocks only.',
        )

    try:
        cik = lookup_sec_cik(symbol.upper())
        financials = get_sec_annual_financials(cik)

        validation = validate_financial_evidence(financials)
        if not validation['valid']:
            raise HTTPException(
                status_code=422,
                detail='SEC financial validation failed: ' + validation['reason'],
            )

        history = financials.get('history') or []
        balance_sheet = financials.get('balance_sheet') or {}
        capital_structure = assess_capital_structure(balance_sheet)

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

        growth_analysis = analyze_cash_flow_growth(history)
        growth_scenarios = build_growth_scenarios(growth_analysis)

        if not growth_scenarios['valid']:
            raise HTTPException(
                status_code=422,
                detail='Company-specific growth analysis unavailable.',
            )

        discount_rates = {
            'Conservative': 0.12,
            'Moderate': 0.10,
            'Optimistic': 0.08,
        }

        scenarios = []
        for scenario in growth_scenarios['scenarios']:
            name = scenario['name']
            growth = scenario['growth_rate']
            discount = discount_rates[name]
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

        risk_assessment = assess_valuation_risk(scenarios)

        if not risk_assessment['valid']:
            raise HTTPException(
                status_code=422,
                detail='Valuation risk assessment failed.',
            )

        return {
            'market': market,
            'symbol': symbol.upper(),
            'status': 'illustrative_only',
            'risk_assessment': risk_assessment,
            'capital_structure': capital_structure,
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
def stock_search(q: str = Query(default='', max_length=100), market: str = 'US'):
    """Return stock suggestions for the selected market."""
    if market not in ('US', 'CA', 'IN'):
        raise HTTPException(status_code=400, detail='Unsupported market')

    if len(q.strip()) < 2:
        return []

    if market in ('CA', 'IN'):
        from .international import search_international_stocks, MarketDataError

        try:
            return search_international_stocks(market, q)
        except MarketDataError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    from .finnhub import search_stocks, FinnhubError

    try:
        return search_stocks(q)
    except FinnhubError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
