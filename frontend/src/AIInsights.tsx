import { useEffect, useRef, useState } from 'react';
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
  analysis_mode: 'ai' | 'rules';
  analysis_note: string;
};

type AIResult = {
  ai_summary: Decision;
  sources: { title: string; url: string }[];
  disclaimer: string;
  analysis_id: number;
  generated_at: string;
  assessment: {
    financial_period_end: string | null;
    missing_data: string[];
    warnings: string[];
    risk_flags: string[];
    required_before_buy: string[];
    quote: { status: string; timestamp: string | null };
    investor_fit: { risk: string; horizon: string; warnings: string[] };
    metrics: { trailing_pe_at_quote: number | null; revenue_growth_trend: string; cash_flow_trend: string };
    evidence: { id: string; period: string; source: string; revenue: number; currency: string | null; filed: string | null; accession: string | null }[];
  };
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
  const [ownsPosition, setOwnsPosition] = useState(false);
  const pending = useRef<AbortController | null>(null);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 30_000);
    return () => { pending.current?.abort(); clearInterval(timer); };
  }, []);

  async function analyze() {
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    setLoading(true);
    setError('');
    setResult(null);

    try {
      const response = await fetch(
        `/api/ai-analysis/${encodeURIComponent(market)}/${encodeURIComponent(symbol)}?owns_position=${ownsPosition}`,
        { signal: controller.signal, cache: 'no-store' }
      );

      if (!response.ok) {
        throw new Error(`AI analysis unavailable (${response.status})`);
      }

      const data = (await response.json()) as AIResult;
      if (!controller.signal.aborted) setResult(data);
    } catch (err) {
      if (!controller.signal.aborted) setError(err instanceof Error ? err.message : 'Analysis failed');
    } finally {
      if (!controller.signal.aborted) setLoading(false);
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

      <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 16 }}>
        <input type="checkbox" checked={ownsPosition} disabled={loading}
          onChange={event => { setOwnsPosition(event.target.checked); setResult(null); }} />
        I already own shares in {symbol}
      </label>
      <p style={{ fontSize: 12 }}>Uses your saved risk tolerance and investment horizon. Save profile changes before analyzing.</p>

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
          <p style={{ fontSize: 12 }}>
            {decision.analysis_mode === 'ai' ? 'AI-assisted research' : 'Rules-based research'} · Analysis #{result?.analysis_id}
            <br />{decision.analysis_note}
            <br />Quote as of: {decision.data_as_of ? new Date(decision.data_as_of).toLocaleString() : 'Unavailable'}
            {' · '}Financial year ended: {result?.assessment.financial_period_end || 'Unavailable'}
          </p>
          {result && now - new Date(result.generated_at).getTime() > 120_000 && (
            <p role="status">This is a saved research snapshot. Refresh analysis to check for updated evidence.</p>
          )}
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
                Research assessment
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

          {result && <div style={{ marginTop: 18 }}>
            <p><strong>Profile:</strong> {result.assessment.investor_fit.risk} risk · {decision.time_horizon}</p>
            <p><strong>Revenue growth:</strong> {result.assessment.metrics.revenue_growth_trend}
              {' · '}<strong>Cash generation:</strong> {result.assessment.metrics.cash_flow_trend}
              {' · '}<strong>P/E at quote:</strong> {result.assessment.metrics.trailing_pe_at_quote ?? 'Unavailable'}</p>
            {[...result.assessment.missing_data, ...result.assessment.risk_flags,
              ...result.assessment.investor_fit.warnings].length > 0 && <ul>
              {[...result.assessment.missing_data, ...result.assessment.risk_flags,
                ...result.assessment.investor_fit.warnings].map(item => <li key={item}>{item}</li>)}
            </ul>}
            <details>
              <summary>Evidence and requirements before buying</summary>
              <ul>{result.assessment.required_before_buy.map(item => <li key={item}>{item}</li>)}</ul>
              <ul>{result.assessment.warnings.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul>
              {result.assessment.evidence.map(item => <p key={item.id}>
                {item.period} · {item.source} · Revenue: {item.revenue.toLocaleString()} {item.currency || '(currency unverified)'}
                {item.filed ? ` · Filed ${item.filed}` : ''}
                {item.accession ? ` · Accession ${item.accession}` : ''}
              </p>)}
            </details>
          </div>}

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
