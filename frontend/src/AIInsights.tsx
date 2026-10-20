import { useState } from 'react';
import {
  ArrowRight, BrainCircuit, CheckCircle2, Clock3,
  RefreshCw, ShieldAlert, TrendingUp,
} from 'lucide-react';

type Decision = {
  decision: 'BUY' | 'HOLD' | 'WAIT' | 'AVOID' | 'INSUFFICIENT DATA';
  headline: string;
  reason: string;
  upside: string;
  risk: string;
  entry_price: number | null;
  target_price: number | null;
  time_horizon: string;
  next_action: string;
  data_as_of: string | null;
};

type AIResult = {
  ai_summary: Decision;
  sources: { title: string; url: string }[];
  disclaimer: string;
};

export default function AIInsights({
  market,
  symbol,
}: {
  market: string;
  symbol: string;
}) {
  const [result, setResult] = useState<AIResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function analyze() {
    setLoading(true);
    setError('');
    setResult(null);

    try {
      const response = await fetch(
        `/api/ai-analysis/${encodeURIComponent(market)}/${encodeURIComponent(symbol)}`
      );

      if (!response.ok) {
        throw new Error(`AI analysis unavailable (${response.status})`);
      }

      setResult((await response.json()) as AIResult);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analysis failed');
    } finally {
      setLoading(false);
    }
  }

  const decision = result?.ai_summary ?? null;
  const verdict = decision?.decision || '';
  const positive = verdict === 'BUY';
  const negative = verdict === 'AVOID';
  const accent = positive ? '#16a34a' : negative ? '#dc2626' : '#d97706';
  const accentBg = positive ? '#f0fdf4' : negative ? '#fef2f2' : '#fffbeb';

  const tile: React.CSSProperties = {
    padding: 18,
    borderRadius: 16,
    border: '1px solid rgba(148,163,184,.22)',
    background: 'rgba(148,163,184,.045)',
    flex: '1 1 220px',
    minWidth: 0,
  };

  return (
    <section style={{
      marginTop: 16,
      padding: 22,
      borderRadius: 20,
      border: '1px solid rgba(148,163,184,.22)',
    }}>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: 16,
      }}>
        <div>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 7,
            fontSize: 12,
            fontWeight: 700,
            letterSpacing: 1,
            opacity: .65,
          }}>
            <BrainCircuit size={16} />
            INVESTIQ AI ANALYSIS
          </div>
          <h2 style={{ margin: '8px 0 4px' }}>{symbol}</h2>
          <div style={{ fontSize: 13, opacity: .65 }}>
            {market === 'IN' ? 'India' : market === 'CA' ? 'Canada' : 'United States'} market
          </div>
        </div>

        <button
          type="button"
          onClick={analyze}
          disabled={loading}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 8,
            padding: '11px 16px',
            borderRadius: 12,
            cursor: loading ? 'wait' : 'pointer',
          }}
        >
          <RefreshCw size={16} />
          {loading ? 'Analyzing…' : result ? 'Refresh analysis' : 'Analyze stock'}
        </button>
      </div>

      {error && <p role="alert" style={{ color: '#dc2626' }}>{error}</p>}

      {!result && !loading && !error && (
        <p style={{ marginTop: 22, opacity: .7 }}>
          Get a simple investment assessment based on available company data.
        </p>
      )}

      {loading && (
        <p style={{ marginTop: 22, opacity: .7 }}>
          Reviewing financial data and investment risks…
        </p>
      )}

      {decision && (
        <div style={{ marginTop: 22 }}>
          <div style={{
            padding: 22,
            borderRadius: 18,
            background: accentBg,
            border: `1px solid ${accent}33`,
            color: '#172033',
          }}>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              flexWrap: 'wrap',
              marginBottom: 12,
            }}>
              {positive
                ? <CheckCircle2 size={26} color={accent} />
                : <Clock3 size={26} color={accent} />}
              <span style={{
                fontSize: 28,
                fontWeight: 800,
                letterSpacing: 1,
                color: accent,
              }}>
                {verdict}
              </span>
              <span style={{ fontSize: 12, opacity: .65 }}>
                AI investment outlook
              </span>
            </div>

            <p style={{
              margin: 0,
              fontSize: 16,
              lineHeight: 1.6,
              fontWeight: 500,
            }}>
              {decision.headline}{decision.reason ? ` ${decision.reason}` : ''}
            </p>
          </div>

          <div style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: 14,
            marginTop: 16,
          }}>
            <div style={tile}>
              <TrendingUp size={22} color="#16a34a" />
              <h3 style={{ margin: '10px 0 8px', fontSize: 15 }}>
                Growth potential
              </h3>
              <p style={{ margin: 0, fontSize: 14, lineHeight: 1.6 }}>
                {decision.upside}
              </p>
            </div>

            <div style={tile}>
              <ShieldAlert size={22} color="#dc2626" />
              <h3 style={{ margin: '10px 0 8px', fontSize: 15 }}>
                Main risk
              </h3>
              <p style={{ margin: 0, fontSize: 14, lineHeight: 1.6 }}>
                {decision.risk}
              </p>
            </div>
          </div>

          <div style={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: 12,
            marginTop: 16,
            padding: 18,
            borderRadius: 16,
            background: 'rgba(59,130,246,.07)',
          }}>
            <ArrowRight size={22} color="#2563eb" style={{ flexShrink: 0 }} />
            <div>
              <strong>Suggested next move</strong>
              <p style={{ margin: '6px 0 0', lineHeight: 1.6, fontSize: 14 }}>
                {decision.next_action}
              </p>
            </div>
          </div>

          {result && result.sources.length > 0 && (
            <details style={{ marginTop: 18 }}>
              <summary style={{ cursor: 'pointer' }}>Research sources</summary>
              <ul>
                {result.sources.map((source, index) => (
                  <li key={`${source.url}-${index}`}>
                    <a href={source.url} target="_blank" rel="noopener noreferrer">
                      {source.title}
                    </a>
                  </li>
                ))}
              </ul>
            </details>
          )}

          <p style={{
            marginTop: 20,
            fontSize: 11,
            lineHeight: 1.5,
            opacity: .6,
          }}>
            {result?.disclaimer}
          </p>
        </div>
      )}
    </section>
  );
}
