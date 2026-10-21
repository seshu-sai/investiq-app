import { useEffect, useState } from 'react';

type Research = {
  market: string;
  symbol: string;
  status: string;
  provider?: string;
  quote_validation?: { status: string; reason: string; timestamp: string | null };
  warnings?: string[];
  quote?: {
    current: number;
    change: number | null;
    percent_change: number | null;
    high: number | null;
    low: number | null;
    previous_close: number | null;
    currency: string;
    timestamp: number | null;
  };
  sources: {
    title: string;
    url: string;
    source: string;
    published_at: number;
    summary?: string;
  }[];
  message: string;
};

export default function LiveResearch({
  market,
  symbol,
}: {
  market: string;
  symbol: string;
}) {
  const [data, setData] = useState<Research | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setData(null);
    setError('');

    let timer: ReturnType<typeof setTimeout>;
    const refresh = () => {
      if (document.hidden) {
        timer = setTimeout(refresh, 60_000);
        return;
      }
      fetch(`/api/research/${encodeURIComponent(market)}/${encodeURIComponent(symbol)}`, {
      signal: controller.signal,
      cache: 'no-store',
    })
      .then(async response => {
        if (!response.ok) throw new Error(`Research unavailable (HTTP ${response.status})`);
        return response.json() as Promise<Research>;
      })
      .then(result => {
        if (!controller.signal.aborted) {
          setData(result);
          setError('');
        }
      })
      .catch(err => {
        if (!controller.signal.aborted) setError(String(err));
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false);
          timer = setTimeout(refresh, 60_000);
        }
      });
    };
    refresh();

    return () => { controller.abort(); clearTimeout(timer); };
  }, [market, symbol]);

  if (loading) return <p>Loading {symbol}…</p>;
  if (error && !data) return <p role="alert">{error}</p>;
  if (!data) return null;
  if (data.status !== 'connected' || !data.quote) return <p>{data.message}</p>;

  const q = data.quote;
  const money = (value: number | null | undefined) =>
    typeof value === 'number'
      ? new Intl.NumberFormat('en-US', {
          style: 'currency',
          currency: q.currency || 'USD',
          maximumFractionDigits: 2,
        }).format(value)
      : 'N/A';

  const change = q.percent_change;
  const changeColor = typeof change === 'number'
    ? change >= 0 ? '#34d399' : '#f87171'
    : 'inherit';

  return (
    <section style={{
      padding: 20,
      border: '1px solid rgba(148,163,184,.22)',
      borderRadius: 18,
    }}>
      {error && <p role="alert">Refresh failed. The displayed quote is from the timestamp below.</p>}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 12,
      }}>
        <div>
          <div style={{ fontSize: 12, opacity: .6 }}>{market} · {symbol}</div>
          <div style={{
            fontSize: 'clamp(28px, 4vw, 38px)',
            fontWeight: 800,
            letterSpacing: '-1px',
            marginTop: 5,
          }}>
            {money(q.current)}
          </div>
          <div style={{ color: changeColor, fontWeight: 650, marginTop: 4 }}>
            {typeof change === 'number'
              ? `${change > 0 ? '+' : ''}${change.toFixed(2)}%`
              : 'Change unavailable'}
            {typeof q.change === 'number' ? ` (${money(q.change)})` : ''}
          </div>
        </div>
        <span style={{
          borderRadius: 30,
          padding: '6px 10px',
          background: 'rgba(148,163,184,.12)',
          fontSize: 12,
        }}>
          {q.currency}
        </span>
      </div>

      <p style={{ fontSize: 12, marginTop: 12 }}>
        <strong>{data.quote_validation?.status.replaceAll('_', ' ') || 'Freshness unverified'}</strong>
        {' · '}{q.timestamp ? new Date(q.timestamp * 1000).toLocaleString() : 'Timestamp unavailable'}
        <br />Refreshes every 60 seconds while this page is visible.
      </p>
      <p style={{ fontSize: 12 }}>{data.quote_validation?.reason}</p>
      {data.warnings?.map(warning => <p key={warning} role="status">{warning}</p>)}

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
        gap: 10,
        marginTop: 18,
      }}>
        {[
          ['Day high', q.high],
          ['Day low', q.low],
        ].map(([label, value]) => (
          <div key={String(label)} style={{
            padding: 12,
            borderRadius: 12,
            background: 'rgba(148,163,184,.08)',
          }}>
            <div style={{ opacity: .65, fontSize: 12 }}>{label}</div>
            <div style={{ fontWeight: 700, marginTop: 5 }}>
              {money(value as number | null)}
            </div>
          </div>
        ))}
      </div>

      <details style={{ marginTop: 18 }}>
        <summary style={{ cursor: 'pointer', fontWeight: 600 }}>
          Latest news ({Math.min(data.sources.length, 3)})
        </summary>
        {data.sources.length ? (
          <ul style={{ paddingLeft: 18, marginTop: 12 }}>
            {data.sources.slice(0, 3).map((item, index) => (
              <li key={`${item.url}-${index}`} style={{ marginBottom: 12 }}>
                <a href={item.url} target="_blank" rel="noopener noreferrer">
                  {item.title || 'Read article'}
                </a>
                <div style={{ opacity: .6, fontSize: 12, marginTop: 3 }}>
                  {item.source}
                </div>
              </li>
            ))}
          </ul>
        ) : <p>No recent news available.</p>}
      </details>

      <details style={{ marginTop: 12 }}>
        <summary style={{ cursor: 'pointer', fontWeight: 600 }}>
          Market details
        </summary>
        <p>Previous close: {money(q.previous_close)}</p>
        <p>Provider: {data.provider || 'Unknown'}</p>
        {q.timestamp ? (
          <p>Quote timestamp: {new Date(q.timestamp * 1000).toLocaleString()}</p>
        ) : null}
        <p style={{ fontSize: 12, opacity: .7 }}>{data.message}</p>
      </details>

      <p style={{ fontSize: 11, opacity: .55, marginTop: 16 }}>
        Prices may be delayed. News may not be company-specific.
      </p>
    </section>
  );
}
