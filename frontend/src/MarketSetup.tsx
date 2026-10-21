export type MarketSetupData = {
  status: string; label: string; trend: string | null; reason: string; as_of: string | null;
  timeframe: string; quote_fresh: boolean; is_realtime: boolean; quote_age_limit_minutes: number;
  metrics: { sma20?: number; sma50?: number; distance_from_sma50_percent?: number;
    momentum20_percent?: number; momentum60_percent?: number; rsi14?: number;
    relative_strength?: { symbol: string; start: string; end: string; excess_return_points: number } | null };
  signals: { label: string; state: string; detail: string }[];
  risk_conflicts: string[]; profile_fit: boolean; definition: string; limitations: string;
};
export type PositionPlanData = { status: string; reason: string; note: string; shares?: number; risk_conflicts?: string[];
  position_value?: number; budget_risk_amount?: number; planned_loss?: number; planned_loss_percent?: number;
  price_to_stop_percent?: number; target_gain?: number | null; reward_to_risk?: number | null; unallocated_budget?: number };

const percent = (value: number | undefined) => value === undefined ? 'Unavailable' : `${value > 0 ? '+' : ''}${value.toFixed(1)}%`;

export default function MarketSetup({ setup, quote, currency, now, onResearch, disabled }: {
  setup?: MarketSetupData; quote: { current: number; timestamp: number | null } | null;
  currency: string; now: number; onResearch: () => void; disabled: boolean;
}) {
  const metrics = setup?.metrics;
  const aged = !!setup?.quote_fresh && (!quote?.timestamp || now - quote.timestamp * 1000 > setup.quote_age_limit_minutes * 60_000);
  const fresh = setup?.quote_fresh && !aged;
  const usablePrice = quote && Number.isFinite(quote.current) && quote.current > 0;
  return <div className="market-setup" data-testid="market-setup">
    <div className="gain-row"><div><span className="gain-small">CURRENT MARKET · DAYS TO WEEKS</span><h3>{aged ? 'FRESH TRADE QUOTE NEEDED' : setup?.label || 'Current-market data unavailable'}</h3></div>
      <button className="outline" type="button" onClick={onResearch} disabled={disabled}>Research latest news</button></div>
    <p>{aged ? 'The displayed quote has passed your age limit. Refresh before using the current-price comparison.' : setup?.reason || 'Refresh to retrieve completed daily prices and a current provider quote.'}</p>
    <p className="gain-small">{fresh && setup?.is_realtime && !!quote?.timestamp && now - quote.timestamp * 1000 <= 120_000 ? 'Configured real-time entitlement and recent provider timestamp.' : fresh ? 'Recent provider trade quote; real-time freshness or entitlement is unverified.' : 'Historical context only until a fresh provider trade quote is available.'}
      {' '}Daily indicators through {setup?.as_of || 'unavailable'}. Quotes refresh every 60 seconds while visible.</p>
    <div className="gain-grid">
      <div className="gain-card"><span>Latest provider price</span><strong>{usablePrice ? new Intl.NumberFormat('en-CA', { style: 'currency', currency }).format(quote.current) : 'Unavailable'}</strong><small>{quote?.timestamp ? new Date(quote.timestamp * 1000).toLocaleString() : 'Trade timestamp unavailable'}</small></div>
      <div className="gain-card"><span>{aged ? 'Last calculated price' : fresh ? 'Current price' : 'Completed close'} versus 50-session average</span><strong>{percent(metrics?.distance_from_sma50_percent)}</strong><small>Observed trend: {setup?.trend?.toLowerCase() || 'unavailable'}</small></div>
      <div className="gain-card"><span>20-session price change</span><strong>{percent(metrics?.momentum20_percent)}</strong><small>Historical price momentum, before dividends and costs</small></div>
      <div className="gain-card"><span>Daily momentum · RSI 14</span><strong>{metrics?.rsi14?.toFixed(1) ?? 'Unavailable'}</strong><small>0–100 indicator; not a win probability</small></div>
    </div>
    {setup?.signals.map(signal => <p className="market-signal" key={signal.label}><strong>{signal.label} · {signal.state.replaceAll('_', ' ')}</strong><span>{signal.detail}</span></p>)}
    {!!setup?.risk_conflicts.length && <div className="gain-negative"><strong>Your historical risk limits still need review:</strong><ul>{setup.risk_conflicts.map(conflict => <li key={conflict}>{conflict}</li>)}</ul></div>}
    {setup && !setup.profile_fit && <p className="gain-negative">This stock does not match your saved markets or asset types.</p>}
    <details className="gain-details"><summary>How to interpret this view</summary><p>{setup?.definition}</p><p>{setup?.limitations}</p><p>The separate long-term valuation view compares earnings scenarios with your return and downside limits. A strict scenario failure does not erase an observed price trend, and a supportive price trend does not establish suitability.</p></details>
  </div>;
}
