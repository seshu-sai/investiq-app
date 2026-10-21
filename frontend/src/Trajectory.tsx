import { useEffect, useState } from 'react';

type Scenario = {
  scenario: string;
  years: number;
  target_price: number;
  total_return_percent: number;
  annualized_return_percent: number;
  eps_growth_assumption: number;
  future_pe_assumption: number;
};

type Analysis = {
  fundamentals: {
    company: string | null;
    currency: string | null;
    trailing_eps: number | null;
    trailing_pe: number | null;
  };
  trajectory: {
    status: string;
    assessment: string;
    current_price?: number;
    scenarios: Scenario[];
    disclaimer?: string;
    reason?: string;
  };
};

export default function Trajectory({
  market,
  symbol,
}: {
  market: string;
  symbol: string;
}) {
  const [data, setData] = useState<Analysis | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    setData(null);
    setError('');
    setLoading(true);

    fetch(`/api/analysis/${encodeURIComponent(market)}/${encodeURIComponent(symbol)}`, {
      signal: controller.signal,
    })
      .then(async response => {
        if (!response.ok) throw new Error(`Analysis unavailable (${response.status})`);
        return response.json() as Promise<Analysis>;
      })
      .then(result => {
        if (!controller.signal.aborted) setData(result);
      })
      .catch(err => {
        if (!controller.signal.aborted) setError(String(err));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
  }, [market, symbol]);

  if (loading) return <p>Loading outlook…</p>;
  if (error) return <p role="alert">{error}</p>;
  if (!data) return null;

  const { trajectory, fundamentals } = data;
  const currency = fundamentals.currency || 'USD';

  const money = (value: number) =>
    new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency,
      maximumFractionDigits: 0,
    }).format(value);

  return (
    <section style={{
      padding: 20,
      border: '1px solid rgba(148,163,184,.22)',
      borderRadius: 18,
      marginTop: 16,
    }}>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        gap: 12,
        flexWrap: 'wrap',
      }}>
        <div>
          <div style={{ opacity: .65, fontSize: 12 }}>3-YEAR HYPOTHETICAL SCENARIOS</div>
          <h3 style={{ margin: '5px 0' }}>{fundamentals.company || symbol}</h3>
        </div>
        <span style={{
          padding: '6px 12px',
          borderRadius: 20,
          background: 'rgba(148,163,184,.12)',
          fontSize: 12,
        }}>
          {trajectory.assessment}
        </span>
      </div>

      {trajectory.status === 'illustrative' ? (
        <>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
            gap: 10,
            marginTop: 18,
          }}>
            {trajectory.scenarios.map(s => (
              <div key={s.scenario} style={{
                padding: '14px 10px',
                borderRadius: 12,
                background: 'rgba(148,163,184,.08)',
                minWidth: 0,
              }}>
                <div style={{ fontSize: 12, opacity: .7, textTransform: 'capitalize' }}>
                  {s.scenario}
                </div>
                <div style={{
                  fontWeight: 750,
                  fontSize: 'clamp(14px, 2vw, 22px)',
                  marginTop: 8,
                  overflowWrap: 'anywhere',
                }}>
                  {money(s.target_price)}
                </div>
                <div style={{
                  marginTop: 6,
                  fontSize: 13,
                  color: s.total_return_percent < 0 ? '#f87171' : '#34d399',
                }}>
                  {s.total_return_percent > 0 ? '+' : ''}
                  {s.total_return_percent.toFixed(1)}%
                </div>
              </div>
            ))}
          </div>

          <details style={{ marginTop: 16, fontSize: 13 }}>
            <summary style={{ cursor: 'pointer', opacity: .8 }}>
              View valuation assumptions
            </summary>
            <p>Starting provider price: {money(trajectory.current_price || 0)}</p>
            <p>Trailing EPS: {fundamentals.trailing_eps ?? 'N/A'} · P/E: {fundamentals.trailing_pe ?? 'N/A'}</p>
            {trajectory.scenarios.map(s => (
              <p key={s.scenario}>
                {s.scenario}: EPS growth {s.eps_growth_assumption}%/year,
                future P/E {s.future_pe_assumption},
                annualized return {s.annualized_return_percent}%
              </p>
            ))}
            <p>{trajectory.disclaimer}</p>
          </details>
        </>
      ) : (
        <p>{trajectory.reason || 'Insufficient data for scenarios.'}</p>
      )}
      <p style={{ fontSize: 11, opacity: .55, marginTop: 12 }}>
        Hypothetical scenarios, not investment recommendations.
      </p>
    </section>
  );
}
