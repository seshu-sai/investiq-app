import { useCallback, useEffect, useRef, useState } from 'react';
import { RefreshCw, Search, TrendingUp, ShieldAlert } from 'lucide-react';
import MarketSetup, { type MarketSetupData, type PositionPlanData } from './MarketSetup';

type Case = { name: string; future_price: number; total_return_percent: number; annualized_return_percent: number;
  eps_growth_percent: number; exit_pe: number; gain_in_base_currency: number | null; ending_value_in_base_currency: number | null };
type Research = { status: string; summary: string; note?: string; retrieved_at?: string;
  segments: { text: string; url: string | null }[]; sources: { title: string; url: string }[] };
type Verdict = { verdict: string; reason: string; quantitative_candidate: boolean; research_required: boolean;
  checks: { label: string; passed: boolean; detail: string }[];
  narrative?: { bull_case: string; bear_case: string; next_step: string;
    events: { event_date: string; description: string; impact: string; source_url: string }[] } };
type ValuationData = {
  symbol: string; company: string | null; generated_at: string; analysis_id?: number;
  quote: { current: number; currency: string; timestamp: number | null } | null;
  quote_validation: { status: string; valid: boolean; reason: string };
  preferences: { amount: number | string; currency: string; risk: string; horizon: string; modeled_years: number;
    annual_return_goal_percent: number; max_loss_percent: number; max_volatility_percent: number; max_downside_percent: number;
    min_history_years: number; required_history_years: number; max_quote_age_minutes: number;
    min_excess_return_percentage_points: number; screening_key: string; screening_mode: string;
    screening_defaults: Record<ScreeningInput, number>; screening_note: string };
  budget: { amount: number; base_currency: string; stock_currency: string | null; hypothetical_fractional_shares: number | null;
    fx: { rate: number; as_of: string | null; provider: string } | null; fx_note: string };
  historical: { status: string; currency?: string; reason?: string; as_of?: string; start?: string; years_available?: number; definition?: string;
    cagr_percent?: number; annualized_volatility_percent?: number; max_drawdown_percent?: number;
    returns: { period: string; return_percent: number | null; start?: string; end?: string }[];
    chart: { date: string; growth_of_100: number }[];
    rolling_history?: { status: string; sample_count: number; positive_windows_percent?: number; independent_periods_approx?: number; warning?: string };
    benchmark?: { symbol: string; stock_cagr_percent: number; benchmark_cagr_percent: number; excess_cagr_percentage_points: number; start: string; end: string } | null };
  historical_budget_cases: { name: string; return_percent: number; gain_in_base_currency: number | null }[];
  valuation: { status: string; reason?: string; scenarios: Case[]; years?: number; definition?: string; limitations?: string; goal_entry_price?: number };
  unrealized_gain: { gain: number; currency: string; return_percent: number; shares: number; average_buy_price: number; market_value: number } | null;
  buy_assessment: Verdict; sources: { title: string; url: string; published_at: number; source: string }[];
  market_setup?: MarketSetupData; position_plan?: PositionPlanData;
  warnings: string[]; web_research: Research; disclaimer: string;
};
type ScreeningInput = 'annual_goal' | 'max_loss' | 'max_volatility' | 'max_downside' | 'min_history_years' | 'max_quote_age_minutes' | 'min_excess_return';
type Inputs = Record<ScreeningInput | 'amount' | 'cost_basis' | 'shares' | 'risk_budget' | 'planned_stop' | 'planned_target', string>;
type Options = Partial<Record<keyof Inputs, number>>;
const emptyInputs: Inputs = { amount: '', annual_goal: '', max_loss: '', max_volatility: '', max_downside: '',
  min_history_years: '', max_quote_age_minutes: '', min_excess_return: '', cost_basis: '', shares: '',
  risk_budget: '', planned_stop: '', planned_target: '' };
const money = (value: number | null | undefined, currency: string) => typeof value === 'number' && Number.isFinite(value)
  ? new Intl.NumberFormat('en-CA', { style: 'currency', currency, maximumFractionDigits: 2 }).format(value) : 'Unavailable';
const pct = (value: number | null | undefined) => typeof value === 'number' ? `${value > 0 ? '+' : ''}${value.toFixed(1)}%` : 'Unavailable';
const tone = (value: number | null | undefined) => typeof value === 'number' && value < 0 ? 'gain-negative' : 'gain-positive';

function HistoryChart({ points }: { points: { date: string; growth_of_100: number }[] }) {
  const [selected, setSelected] = useState<number | null>(null);
  if (points.length < 2) return null;
  const values = points.map(point => point.growth_of_100);
  const low = Math.min(100, ...values), high = Math.max(101, ...values);
  const y = (value: number) => 180 - (value - low) / (high - low) * 160;
  const path = points.map((point, index) => `${index ? 'L' : 'M'}${index / (points.length - 1) * 900},${y(point.growth_of_100)}`).join(' ');
  const index = Math.min(selected ?? points.length - 1, points.length - 1);
  const point = points[index];
  return <div className="history-chart">
    <div className="gain-row"><strong>Growth of 100 in the stock currency</strong><span>{point.date}: {point.growth_of_100.toFixed(2)}</span></div>
    <svg viewBox="0 0 900 200" role="img" aria-label="Historical growth of 100 with dividends and splits adjusted"
      onMouseMove={event => { const bounds = event.currentTarget.getBoundingClientRect(); setSelected(Math.max(0, Math.min(points.length - 1, Math.round((event.clientX - bounds.left) / bounds.width * (points.length - 1))))); }}>
      <line x1="0" x2="900" y1={y(100)} y2={y(100)} stroke="#556579" strokeDasharray="5 5" />
      <path d={path} fill="none" stroke="#42d5a7" strokeWidth="3" />
      <circle cx={index / (points.length - 1) * 900} cy={y(point.growth_of_100)} r="5" fill="#e7eaf0" />
    </svg>
    <input aria-label="Explore historical return dates" type="range" min="0" max={points.length - 1} value={index} onChange={event => setSelected(Number(event.target.value))} />
    <div className="gain-row gain-small"><span>{points[0].date}</span><span>{points[points.length - 1].date}</span></div>
  </div>;
}

export default function Valuation({ market, symbol }: { market: string; symbol: string }) {
  const [view, setView] = useState<'market' | 'valuation'>('market');
  const [data, setData] = useState<ValuationData | null>(null);
  const [review, setReview] = useState<ValuationData | null>(null);
  const [inputs, setInputs] = useState<Inputs>(emptyInputs);
  const [dirty, setDirty] = useState(false);
  const [loading, setLoading] = useState(true);
  const [researching, setResearching] = useState(false);
  const [error, setError] = useState('');
  const [now, setNow] = useState(Date.now());
  const pending = useRef<AbortController | null>(null);
  const busy = useRef(false);
  const applied = useRef<Options>({});
  const form = useRef<HTMLFormElement>(null);

  const load = useCallback(async (options: Options, research = false, background = false) => {
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    busy.current = true;
    if (!background) setLoading(true);
    setResearching(research);
    setError('');
    try {
      const query = new URLSearchParams(Object.entries(options).map(([key, value]) => [key, String(value)]));
      const path = `/api/valuation/${encodeURIComponent(market)}/${encodeURIComponent(symbol)}`;
      const response = await fetch(research ? `${path}/research` : `${path}?${query}`, {
        signal: controller.signal, cache: 'no-store', ...(research ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(options) } : {}),
      });
      if (!response.ok) {
        const failure = await response.json().catch(() => null);
        throw new Error(typeof failure?.detail === 'string' ? failure.detail : `Valuation unavailable (${response.status})`);
      }
      const result = await response.json() as ValuationData;
      if (controller.signal.aborted) return;
      setData(result);
      if (research) setReview(result);
      setNow(Date.now());
    } catch (err) {
      if (!controller.signal.aborted) setError(err instanceof Error ? err.message : 'Valuation unavailable');
    } finally {
      if (pending.current === controller) { busy.current = false; setLoading(false); setResearching(false); }
    }
  }, [market, symbol]);

  useEffect(() => {
    setData(null); setReview(null); setInputs(emptyInputs); setDirty(false); applied.current = {};
    setView('market');
    void load({});
    const timer = setInterval(() => {
      setNow(Date.now());
      if (!document.hidden && !busy.current) void load(applied.current, false, true);
    }, 60_000);
    return () => { clearInterval(timer); pending.current?.abort(); };
  }, [load]);

  function apply(research = false) {
    if (!form.current?.reportValidity()) return;
    const options = Object.fromEntries(Object.entries(inputs).filter(([, value]) => value !== '').map(([key, value]) => [key, Number(value)])) as Options;
    applied.current = options;
    setDirty(false);
    setReview(null);
    void load(options, research);
  }
  function field(key: keyof Inputs, value: string) { setInputs(current => ({ ...current, [key]: value })); setDirty(true); }
  function reset() {
    setInputs(emptyInputs); setDirty(false); setReview(null); applied.current = {};
    void load({});
  }

  const base = data?.budget.base_currency || 'CAD';
  const stock = data?.budget.stock_currency || 'USD';
  const history = data?.historical;
  const defaults = data?.preferences.screening_defaults;
  const matchingReview = !dirty && review && data && !!data.preferences.screening_key
    && review.preferences.screening_key === data.preferences.screening_key;
  const expired = !!review && now - new Date(review.generated_at).getTime() > 15 * 60_000;
  let assessment = matchingReview && !expired ? review!.buy_assessment : data?.buy_assessment;
  if (assessment?.verdict === 'BUY CANDIDATE' && (!matchingReview || expired || !data?.buy_assessment.quantitative_candidate)) {
    assessment = { ...data!.buy_assessment, verdict: 'WAIT', research_required: true,
      reason: dirty ? 'You have edited the criteria. Apply them and request a fresh news review to assess a buy candidate.'
        : 'The news review has expired or the current price or screening inputs no longer pass. Refresh the web review before considering an entry.' };
  }
  const web = review?.web_research;
  const plan = data?.position_plan;
  const hasPlan = plan?.status === 'calculated' || plan?.status === 'review_required';
  const planQuoteFresh = !!data?.quote?.timestamp && data.quote_validation.valid && data.quote_validation.status !== 'daily_bar'
    && now - data.quote.timestamp * 1000 <= data.preferences.max_quote_age_minutes * 60_000;

  return <section className="gain-valuation">
    <div className="gain-row"><div><h3>{data?.company || symbol}</h3><p className="gain-small">Valuation, historical returns and your gain/loss scenarios</p></div>
      <button className="outline" type="button" disabled={loading} onClick={() => void load(applied.current)}><RefreshCw size={16} /> Refresh prices</button></div>
    <div className="valuation-tabs" aria-label="Analysis view">
      <button type="button" aria-pressed={view === 'market'} onClick={() => setView('market')}>Current market</button>
      <button type="button" aria-pressed={view === 'valuation'} onClick={() => setView('valuation')}>Long-term valuation</button>
    </div>
    {dirty && <p className="gain-small" role="status">You have unapplied changes. Results below still use the last applied criteria; any previous buy-candidate signal is withheld.</p>}
    {view === 'market' && <MarketSetup setup={data?.market_setup} quote={data?.quote || null} currency={stock} now={now} onResearch={() => apply(true)} disabled={loading} />}
    <form ref={form} onSubmit={event => { event.preventDefault(); apply(); }}>
      <details className="gain-details screening-settings" open={view === 'valuation'}><summary>Screening limits and your existing position</summary><div className="gain-controls">
      <label>Annual return goal (%)<input type="number" min="0.1" max="100" step="0.1" value={inputs.annual_goal} placeholder={String(defaults?.annual_goal ?? '')} onChange={event => field('annual_goal', event.target.value)} /></label>
      <label>Maximum historical drawdown (%)<input type="number" min="0.1" max="100" step="0.1" value={inputs.max_loss} placeholder={String(defaults?.max_loss ?? '')} onChange={event => field('max_loss', event.target.value)} /><small>Largest historical peak-to-trough fall you will accept.</small></label>
      <label>Maximum annualized volatility (%)<input type="number" min="0" max="300" step="0.1" value={inputs.max_volatility} placeholder={String(defaults?.max_volatility ?? '')} onChange={event => field('max_volatility', event.target.value)} /><small>Your cap on historical price variability.</small></label>
      <label>Maximum modeled downside loss (%)<input type="number" min="0" max="100" step="0.1" value={inputs.max_downside} placeholder={inputs.max_loss || String(defaults?.max_downside ?? '')} onChange={event => field('max_downside', event.target.value)} /><small>Loss at the end of the downside scenario. Blank follows your drawdown limit.</small></label>
      <details className="gain-advanced"><summary>More screening criteria</summary><div className="gain-controls">
        <label>Minimum history (years)<input type="number" min="1" max="10" step="1" value={inputs.min_history_years} placeholder={String(defaults?.min_history_years ?? '')} onChange={event => field('min_history_years', event.target.value)} /><small>Must also cover your modeled holding period.</small></label>
        <label>Maximum trade quote age (minutes)<input type="number" min="1" max="60" step="1" value={inputs.max_quote_age_minutes} placeholder={String(defaults?.max_quote_age_minutes ?? '')} onChange={event => field('max_quote_age_minutes', event.target.value)} /><small>A provider trade timestamp is required; daily bars do not qualify.</small></label>
        <label>Minimum return over benchmark (points/year)<input type="number" min="-100" max="100" step="0.1" value={inputs.min_excess_return} placeholder={String(defaults?.min_excess_return ?? '')} onChange={event => field('min_excess_return', event.target.value)} /><small>Annual stock return minus market ETF return, on matching dates.</small></label>
      </div></details>
      <label>Your average buy price ({stock}, optional)<input type="number" min="0.0001" max="1000000000" step="any" required={!!inputs.shares} value={inputs.cost_basis} onChange={event => field('cost_basis', event.target.value)} /></label>
      <label>Shares you own (optional)<input type="number" min="0.000001" max="1000000000000" step="any" required={!!inputs.cost_basis} value={inputs.shares} onChange={event => field('shares', event.target.value)} /></label>
      </div><p className="gain-small">Return goal and modeled downside loss apply to the long-term earnings screen. Historical drawdown and volatility limits remain visible in the current-market risk review.</p></details>
      <div className="gain-planner"><h4>Plan a position before considering an entry</h4>
      <p className="gain-small">Risk on a position means the budget you plan to lose between entry and an exit price. It is different from the stock's possible long-term decline.</p>
      <div className="gain-controls">
        <label>Amount to model ({base})<input type="number" min="0.01" max="1000000000000" step="0.01" value={inputs.amount} placeholder={String(data?.budget.amount || '')} onChange={event => field('amount', event.target.value)} /></label>
        <label>Budget risk per idea (%)<input type="number" min="0.01" max="100" step="0.01" value={inputs.risk_budget} required={!!inputs.planned_stop || !!inputs.planned_target} onChange={event => field('risk_budget', event.target.value)} /><small>Percentage of this modeled budget, not verified portfolio equity.</small></label>
        <label>Planned exit if price falls ({stock})<input type="number" min="0.0001" max="1000000000" step="any" value={inputs.planned_stop} required={!!inputs.risk_budget || !!inputs.planned_target} onChange={event => field('planned_stop', event.target.value)} /><small>Enter a level below the current price. Execution is not guaranteed.</small></label>
        <label>Optional target price ({stock})<input type="number" min="0.0001" max="1000000000" step="any" value={inputs.planned_target} onChange={event => field('planned_target', event.target.value)} /><small>Your assumption, not an AI price forecast.</small></label>
      </div>
      {hasPlan && plan && planQuoteFresh ? <div className="position-result" data-testid="position-result">
        {plan.status === 'review_required' && <div className="gain-negative"><strong>{plan.reason}</strong><ul>{plan.risk_conflicts?.map(conflict => <li key={conflict}>{conflict}</li>)}</ul></div>}
        <p><strong>{plan.shares} whole shares</strong> · hypothetical position {money(plan.position_value, base)} · unallocated {money(plan.unallocated_budget, base)}.</p>
        <p>Planned loss at your exit: <strong>{money(plan.planned_loss, base)}</strong> ({plan.planned_loss_percent}% of budget), against {money(plan.budget_risk_amount, base)} risk budget. The stock-to-exit distance is {plan.price_to_stop_percent}%.</p>
        {plan.target_gain !== null && plan.target_gain !== undefined && <p>Gain if your target is reached: {money(plan.target_gain, base)} · reward/risk {plan.reward_to_risk}×, before costs.</p>}
        {plan.shares === 0 && <p>Your entered budget and risk limit cannot fund one whole share at these levels.</p>}</div> : <p className="gain-small">{hasPlan ? 'The quote has passed your age limit. Refresh before using a position size.' : plan?.reason || 'Enter a budget-risk percentage and planned exit price, then apply.'}</p>}
      {plan && <p className="gain-small">{plan.note}</p>}
      </div>
      <div className="gain-actions">
      <button className="outline" type="submit" disabled={loading}>Apply criteria</button>
      <button className="outline" type="button" disabled={loading} onClick={reset}>Reset to profile defaults</button>
      </div>
    </form>
    <p className="gain-small">These controls apply to this stock screen. Blank limits use your profile defaults, except downside loss which follows your drawdown limit. Applying criteria recalculates the checklist; Research latest news reviews the same values. Changing criteria clears the previous news assessment.</p>
    {error && <p role="alert" className="gain-negative">{error}{data ? ' Existing figures are from their displayed timestamps.' : ''}</p>}
    {loading && <p role="status">{researching ? 'Searching current company news and reviewing the evidence…' : 'Loading prices, annual earnings and historical returns…'}</p>}
    {data && <>
      <p className="gain-small">Saved profile: <strong>{data.preferences.risk} risk · {data.preferences.horizon} years</strong>. {view === 'valuation' ? `Earnings scenarios model ${data.preferences.modeled_years} years.` : 'Current-market indicators describe daily trends; they do not change your investment horizon.'}
        {' '}{data.preferences.screening_mode === 'custom' ? 'Custom screening limits applied.' : 'Profile defaults applied.'} A custom limit changes this screen; it does not change the saved risk label.</p>
      <p className="gain-small" data-testid="applied-criteria"><strong>Applied {view === 'market' ? 'current-market risk limits' : 'criteria'}:</strong> maximum historical drawdown {data.preferences.max_loss_percent}%; annualized volatility {data.preferences.max_volatility_percent}%; quote age {data.preferences.max_quote_age_minutes} minutes.
        {view === 'valuation' && <> Annual goal {data.preferences.annual_return_goal_percent}%; modeled downside loss {data.preferences.max_downside_percent}%; minimum history {data.preferences.min_history_years} years ({data.preferences.required_history_years} required including the holding period); return over benchmark at least {data.preferences.min_excess_return_percentage_points} points/year.</>} These are screening limits, not promised outcomes.</p>
      {view === 'valuation' && <>
      <div className="gain-grid">
        <div className="gain-card"><span>Latest provider price</span><strong>{money(data.quote?.current, stock)}</strong><small>{data.quote_validation.status.replaceAll('_', ' ')} · {data.quote?.timestamp ? new Date(data.quote.timestamp * 1000).toLocaleString() : 'Timestamp unavailable'}</small></div>
        <div className="gain-card"><span>Historical annualized return</span><strong className={tone(history?.cagr_percent)}>{pct(history?.cagr_percent)}</strong><small>{history?.start} to {history?.as_of}; {history?.years_available ?? 0} years</small></div>
        <div className="gain-card"><span>Historical maximum drawdown</span><strong className="gain-negative">{pct(history?.max_drawdown_percent)}</strong><small>Largest peak-to-trough fall; future losses can be larger</small></div>
        <div className="gain-card"><span>Your unrealized gain / loss</span><strong className={tone(data.unrealized_gain?.gain)}>{money(data.unrealized_gain?.gain, stock)}</strong><small>{data.unrealized_gain ? `${pct(data.unrealized_gain.return_percent)} on your entered shares, before costs/tax/FX` : 'Enter your average buy price and shares above'}</small></div>
      </div>
      <p className="gain-small">{data.quote_validation.reason} Prices refresh every 60 seconds while this tab is visible. News research runs when requested.</p>
      {assessment && <div className={`buy-assessment ${assessment.verdict === 'BUY CANDIDATE' ? 'candidate' : ''}`}>
        <div className="gain-row"><div><span className="gain-small">LONG-TERM EARNINGS SCREEN</span><h3>{assessment.verdict}</h3></div>
          <button className="outline" type="button" disabled={loading} onClick={() => apply(true)}><Search size={16} />{researching ? 'Researching…' : 'Research latest news'}</button></div>
        <p>{assessment.reason}</p>
        {assessment.quantitative_candidate && assessment.research_required && <p>The quantitative screen passes. Current cited news still needs review before a buy-candidate signal is available.</p>}
        {expired && <p role="status">The saved news assessment is over 15 minutes old. Its buy signal has expired; refresh the research.</p>}
        <p className="gain-small">A buy candidate is a research signal. Full portfolio suitability and executable pricing still need review.</p>
        <details><summary>See exactly what passed or failed</summary><ul>{data.buy_assessment.checks.map(check => <li key={check.label}><strong>{check.passed ? 'Pass' : 'Review'} · {check.label}:</strong> {check.detail}</li>)}</ul></details>
      </div>}
      <h3 className="gain-section-title">What could your investment gain or lose?</h3>
      <p>Modeling {money(data.budget.amount, base)} over {data.preferences.modeled_years} years. {data.budget.hypothetical_fractional_shares !== null ? `Equivalent to approximately ${data.budget.hypothetical_fractional_shares.toFixed(3)} fractional shares at the displayed price.` : 'Currency conversion or current pricing is unavailable; cash gains are withheld.'}</p>
      {data.valuation.scenarios.length ? <div className="gain-grid three">{data.valuation.scenarios.map(scenario => <div className="gain-card" key={scenario.name}>
        <span>{scenario.name} earnings sensitivity</span><strong className={tone(scenario.gain_in_base_currency)}>{money(scenario.gain_in_base_currency, base)}</strong>
        <p>{pct(scenario.total_return_percent)} total · {pct(scenario.annualized_return_percent)} annualized</p>
        <small>Ending value: {money(scenario.ending_value_in_base_currency, base)}<br />Conditional stock price: {money(scenario.future_price, stock)}<br />EPS growth: {scenario.eps_growth_percent}%/year · Exit P/E: {scenario.exit_pe}×</small>
      </div>)}</div> : <p>{data.valuation.reason}</p>}
      {data.valuation.goal_entry_price !== undefined && <p><strong>Conditional entry threshold for your goal:</strong> {money(data.valuation.goal_entry_price, stock)}. This is the entry price needed to reach your return hurdle under the base earnings assumptions; it is not a verified fair value or buy instruction.</p>}
      <details className="gain-details"><summary>Valuation assumptions and currency conversion</summary><p>{data.valuation.definition}</p><p>{data.valuation.limitations}</p><p>{data.preferences.screening_note}</p><p>{data.budget.fx_note}</p>{data.budget.fx && <p>1 {base} = {data.budget.fx.rate.toFixed(6)} {stock} · {data.budget.fx.as_of || 'same currency'} · {data.budget.fx.provider}</p>}</details>
      <h3 className="gain-section-title">What the historical data actually shows</h3>
      {history?.status !== 'available' ? <p>{history?.reason}</p> : <>
        <HistoryChart points={history.chart} />
        <div className="gain-table-wrap"><table className="gain-table"><thead><tr><th>Holding period</th><th>Historical return</th><th>Actual start date</th></tr></thead><tbody>{history.returns.map(row => <tr key={row.period}><td>{row.period}</td><td className={tone(row.return_percent)}>{pct(row.return_percent)}</td><td>{row.start || 'Not enough history'}</td></tr>)}</tbody></table></div>
        <p className="gain-small">{history.definition}. Returns are in {history.currency || stock}; they exclude your personal FX effects and costs.</p>
        {history.benchmark && <p><strong>Market comparison ({history.benchmark.symbol}):</strong> stock {pct(history.benchmark.stock_cagr_percent)} versus benchmark {pct(history.benchmark.benchmark_cagr_percent)} annualized, from {history.benchmark.start} to {history.benchmark.end}. Difference: {history.benchmark.excess_cagr_percentage_points.toFixed(1)} percentage points per year.</p>}
        {data.historical_budget_cases.length > 0 && <>
          <h4>If past holding-period outcomes repeated</h4><div className="gain-grid three">{data.historical_budget_cases.map(item => <div className="gain-card" key={item.name}><span>{item.name}</span><strong className={tone(item.gain_in_base_currency)}>{money(item.gain_in_base_currency, base)}</strong><small>{pct(item.return_percent)} over {data.preferences.modeled_years} years</small></div>)}</div>
          <p className="gain-small">{history.rolling_history?.sample_count} overlapping monthly-start windows; approximately {history.rolling_history?.independent_periods_approx} independent holding periods. {history.rolling_history?.positive_windows_percent}% of those historical windows were positive. This is not a future probability. {history.rolling_history?.warning}</p>
        </>}
      </>}
      </>}
      <h3 className="gain-section-title">Current company research</h3>
      {web && <div className="gain-details">
        <p className="gain-small">{web.note}{web.retrieved_at ? ` Retrieved ${new Date(web.retrieved_at).toLocaleString()}.` : ''}</p>
        {web.status === 'available' && <p style={{ whiteSpace: 'pre-wrap' }}>{web.segments.map((segment, index) => segment.url ? <a key={index} href={segment.url} target="_blank" rel="noopener noreferrer">{segment.text}</a> : <span key={index}>{segment.text}</span>)}</p>}
      </div>}
      {matchingReview && !expired && review?.buy_assessment.narrative && <>
        <p className="gain-small">News review under the long-term screening criteria: <strong>{review.buy_assessment.verdict}</strong>. This review is separate from the observed price trend.</p>
        <div className="gain-grid two"><div className="gain-card"><TrendingUp size={22} /><h4>Bull case</h4><p>{review.buy_assessment.narrative.bull_case}</p></div><div className="gain-card"><ShieldAlert size={22} /><h4>Bear case</h4><p>{review.buy_assessment.narrative.bear_case}</p></div></div>
        <p><strong>Next step:</strong> {review.buy_assessment.narrative.next_step}</p>
        <ul>{review.buy_assessment.narrative.events.map((event, index) => <li key={index}>{event.event_date} · {event.description} <a href={event.source_url} target="_blank" rel="noopener noreferrer">Source</a></li>)}</ul>
      </>}
      <ul className="gain-news">{data.sources.slice(0, 5).map(item => <li key={item.url}><a href={item.url} target="_blank" rel="noopener noreferrer">{item.title}</a><small>{item.source} · {new Date(item.published_at * 1000).toLocaleDateString()} · Provider-associated news; check company relevance</small></li>)}</ul>
      {!data.sources.length && !web && <p>No recent provider news is available. Use “Research latest news” to search the web for this stock.</p>}
      <details className="gain-details"><summary>Data limitations and profile warnings</summary><ul>{data.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul></details>
      <p className="disclaimer">{data.disclaimer}</p>
    </>}
  </section>;
}
