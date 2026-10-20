import { useEffect, useState } from 'react';

type Scenario = {
  name: string;
  illustrative_value_per_share_usd: number;
  illustrative_25pct_buffer_usd: number;
  terminal_value_share_approx: number | null;
  assumptions: {
    growth_rate: number;
    discount_rate: number;
    terminal_growth_rate: number;
    years: number;
  };
};

type ValuationResponse = {
  status: string;
  currency: string;
  sec_inputs: {
    cash_flow_proxy_usd: number;
    cash_flow_fiscal_year_end: string;
    cash_flow_filed: string;
    shares_outstanding: number;
    shares_as_of: string;
  };
  scenarios: Scenario[];
  limitations: string;
};

export default function Valuation({
  market,
  symbol,
}: {
  market: string;
  symbol: string;
}) {
  const [data, setData] = useState<ValuationResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    setData(null);
    setError('');

    if (market !== 'US') return;

    const controller = new AbortController();
    setLoading(true);

    fetch(
      `/api/valuation/${encodeURIComponent(market)}/${encodeURIComponent(symbol)}`,
      { signal: controller.signal }
    )
      .then(async response => {
        if (!response.ok) {
          throw new Error(`Valuation unavailable (${response.status})`);
        }
        return response.json() as Promise<ValuationResponse>;
      })
      .then(setData)
      .catch(err => {
        if (err.name !== 'AbortError') setError(err.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
  }, [market, symbol]);

  const usd = (value: number) =>
    new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
    }).format(value);

  const percent = (value: number) =>
    `${(value * 100).toFixed(1)}%`;

  return (
    <section className="valuation-section">
      <h3>Cash-flow valuation scenarios</h3>
      <p>
        Illustrative sensitivity analysis using SEC historical financial
        data and hypothetical assumptions. Not a price target.
      </p>

      {market !== 'US' ? (
        <p>SEC-based valuation currently supports US stocks only.</p>
      ) : loading ? (
        <p>Loading valuation scenarios…</p>
      ) : error ? (
        <p role="alert">{error}</p>
      ) : data ? (
        <>
          <div className="valuation-scenarios">
            {data.scenarios.map(scenario => (
              <div className="valuation-scenario" key={scenario.name}>
                <h4>{scenario.name}</h4>
                <strong>
                  {usd(scenario.illustrative_value_per_share_usd)}
                </strong>
                <p>
                  Illustrative value per share — not a buy price
                </p>
                <p>
                  25% buffer: {usd(scenario.illustrative_25pct_buffer_usd)}
                </p>
                <small>
                  Growth: {percent(scenario.assumptions.growth_rate)}
                  {' · '}Discount: {percent(scenario.assumptions.discount_rate)}
                  {' · '}Terminal growth: {percent(scenario.assumptions.terminal_growth_rate)}
                  {' · '}Projection: {scenario.assumptions.years} years
                </small>
                <p>
                  Terminal-value contribution:{' '}
                  {scenario.terminal_value_share_approx === null
                    ? 'Unavailable'
                    : percent(scenario.terminal_value_share_approx)}
                </p>
              </div>
            ))}
          </div>

          <p>
            <strong>SEC historical input:</strong>{' '}
            Cash-flow proxy {usd(data.sec_inputs.cash_flow_proxy_usd)}
            {' · '}Fiscal year ended {data.sec_inputs.cash_flow_fiscal_year_end}
            {' · '}Filed {data.sec_inputs.cash_flow_filed}
          </p>

          <p>
            <strong>Share count:</strong>{' '}
            {data.sec_inputs.shares_outstanding.toLocaleString('en-US')}
            {' · '}As of {data.sec_inputs.shares_as_of}
          </p>

          <p className="disclaimer">
            <strong>Model limitations:</strong> {data.limitations}
          </p>
        </>
      ) : null}
    </section>
  );
}
