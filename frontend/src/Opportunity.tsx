export type OpportunityData = {
  key: string; verdict: string; reason: string; eligible: boolean;
  inputs: { holding_weeks: number; loss_amount: number; min_reward_risk: number; round_trip_cost_percent: number };
  plan: { entry_price: number; buy_up_to: number; exit_price: number; target_price: number;
    target_basis: string; exit_basis: string; levels_as_of: string; shares: number; money_used: number; money_unallocated: number;
    planned_loss: number; potential_gain: number; gain_on_position_percent: number; reward_risk: number;
    estimated_round_trip_cost: number } | null;
  checks: { label: string; passed: boolean; detail: string }[]; context: string[]; limitations: string;
  news_review: { status: string; reason: string; stance?: string; reviewed_at?: string;
    events?: { event_date: string; description: string; impact: string; source_url: string }[] };
};

const labels: Record<string, string> = {
  'BUY SETUP': 'Buy setup — check company news', 'BUY CANDIDATE': 'Buy candidate',
  'WAIT FOR BETTER PRICE': 'Wait for a better price', 'WAIT FOR TREND': 'Wait for the price trend to improve',
  'INSUFFICIENT DATA': 'More information needed', 'WAIT': 'Wait for now', 'AVOID': 'Avoid for now',
};
const money = (value: number | undefined, currency: string) => value === undefined ? 'Unavailable'
  : new Intl.NumberFormat('en-CA', { style: 'currency', currency, maximumFractionDigits: 2 }).format(value);

export default function Opportunity({ data, currency, stockCurrency, fresh, dirty, onResearch, busy, quoteTimestamp, isRealtime }: {
  data?: OpportunityData; currency: string; stockCurrency: string; fresh: boolean; dirty: boolean;
  onResearch: () => void; busy: boolean; quoteTimestamp?: number | null; isRealtime?: boolean;
}) {
  const plan = data?.plan;
  const ready = fresh && !dirty;
  const positive = ready && (data?.verdict === 'BUY SETUP' || data?.verdict === 'BUY CANDIDATE');
  const setupLabel = data?.verdict === 'BUY SETUP' && data.news_review.status === 'validated' && data.news_review.stance === 'mixed'
    ? 'Buy setup — company news is mixed' : data?.verdict === 'BUY SETUP' && data.news_review.status === 'unavailable'
      ? 'Buy setup — news review unavailable' : undefined;
  return <section className={`opportunity-card ${positive ? 'opportunity-positive' : ''}`} data-testid="investment-decision">
    <span className="gain-small">YOUR {data?.inputs.holding_weeks || 12}-WEEK INVESTING PLAN</span>
    <div className="gain-row"><h3>{dirty ? 'Update your analysis' : !data ? 'Preparing your analysis…' : !fresh ? 'A fresh trade price is needed' : setupLabel || labels[data.verdict] || data.verdict}</h3>
      <button type="button" className="outline" onClick={onResearch} disabled={busy || !data}>{busy ? 'Reviewing…' : 'Check company news'}</button></div>
    <p>{dirty ? 'Your answers changed. Analyse the stock again to update the plan below.' : !fresh && data ? 'The displayed trade price is missing or older than your limit. Refresh before using an entry or position size.' : data?.reason}</p>
    {quoteTimestamp && <p className="gain-small">Price recorded {new Date(quoteTimestamp * 1000).toLocaleString()}. {isRealtime ? 'Configured real-time entitlement and recent timestamp.' : 'Real-time freshness or entitlement is unverified.'} Prices refresh every 60 seconds while visible.</p>}
    {plan && ready && <>
      <div className="gain-grid three">
        <div className="gain-card"><span>Potential profit if the target is reached</span><strong className={plan.potential_gain < 0 ? 'gain-negative' : 'gain-positive'}>{money(plan.potential_gain, currency)}</strong><small>{plan.gain_on_position_percent}% on the planned position, after estimated costs; not a forecast</small></div>
        <div className="gain-card"><span>Planned loss if the exit fills there</span><strong className="gain-negative">{money(plan.planned_loss, currency)}</strong><small>Your chosen money-at-risk limit: {money(data?.inputs.loss_amount, currency)}. Actual losses can be larger.</small></div>
        <div className="gain-card"><span>Money used for this position</span><strong>{money(plan.money_used, currency)}</strong><small>{plan.shares} whole shares, including estimated entry costs. {money(plan.money_unallocated, currency)} stays uninvested.</small></div>
      </div>
      <div className="opportunity-levels">
        <p><span>Price used for this plan</span><strong>{money(plan.entry_price, stockCurrency)}</strong></p>
        <p><span>Highest entry price that meets your profit/loss rule</span><strong>{money(plan.buy_up_to, stockCurrency)}</strong></p>
        <p><span>Planned exit if the price falls</span><strong>{money(plan.exit_price, stockCurrency)}</strong></p>
        <p><span>Take-profit reference</span><strong>{money(plan.target_price, stockCurrency)}</strong></p>
      </div>
      <p className="gain-small">For each 1 {currency} of planned loss, the target offers about {plan.reward_risk} {currency} of potential profit. A lower entry price must still have a supportive trend.</p>
    </>}
    {data && <>
      <p className="gain-small"><strong>Company news:</strong> {data.news_review.reason}</p>
      {data.news_review.events && <ul className="gain-news">{data.news_review.events.map((event, index) => <li key={index}>{event.event_date} · {event.description} <a href={event.source_url} target="_blank" rel="noopener noreferrer">Read source</a></li>)}</ul>}
      <details className="gain-details"><summary>Why this result, and what could change it?</summary><ul>{data.checks.map(check => <li key={check.label}><strong>{check.passed ? 'Pass' : 'Review'} · {check.label}:</strong> {check.detail}</li>)}</ul>
        {plan && <p>Exit reference: {plan.exit_basis}. Target reference: {plan.target_basis}. Daily prices through {plan.levels_as_of}. Estimated total trading cost: {money(plan.estimated_round_trip_cost, currency)}.</p>}
        {!!data.context.length && <><p>Long-term stock risks remain relevant. The short-term position is sized using your money-at-risk answer; this does not make the stock low risk.</p><ul>{data.context.map(item => <li key={item}>{item}</li>)}</ul></>}
      </details>
      <p className="gain-small">{data.limitations}</p>
    </>}
  </section>;
}
