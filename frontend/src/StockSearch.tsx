import { useEffect, useState } from 'react';
import { Search } from 'lucide-react';

type Suggestion = {
  symbol: string;
  name: string;
  market: string;
};

export default function StockSearch({
  market,
  value,
  onChange,
}: {
  market: string;
  value: string;
  onChange: (symbol: string) => void;
}) {
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const query = value.trim();

    if (query.length < 2 || !open) {
      setSuggestions([]);
      setLoading(false);
      return;
    }

    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setLoading(true);

      try {
        const response = await fetch(
          `/api/stocks/search?q=${encodeURIComponent(query)}&market=${market}`,
          { signal: controller.signal }
        );

        if (!response.ok) throw new Error('Search failed');

        const data = (await response.json()) as Suggestion[];
        setSuggestions(data);
      } catch {
        if (!controller.signal.aborted) setSuggestions([]);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, 350);

    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [value, market, open]);

  return (
    <div style={{ position: 'relative', flex: 1, minWidth: 180 }}>
      <div style={{ position: 'relative' }}>
        <Search
          size={16}
          style={{
            position: 'absolute',
            left: 12,
            top: '50%',
            transform: 'translateY(-50%)',
            opacity: 0.5,
            pointerEvents: 'none',
          }}
        />

        <input
          aria-label="Search stocks"
          placeholder="Search company or ticker..."
          value={value}
          onChange={event => {
            onChange(event.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          style={{ width: '100%', paddingLeft: 36, boxSizing: 'border-box' }}
        />
      </div>

      {open && (suggestions.length > 0 || loading) && (
        <div style={{
          position: 'absolute',
          zIndex: 30,
          top: 'calc(100% + 6px)',
          left: 0,
          right: 0,
          background: '#fff',
          color: '#172033',
          border: '1px solid #e2e8f0',
          borderRadius: 14,
          boxShadow: '0 14px 36px rgba(15,23,42,.14)',
          maxHeight: 280,
          overflowY: 'auto',
        }}>
          {loading && (
            <div style={{ padding: 12, fontSize: 13, opacity: .65 }}>
              Searching stocks...
            </div>
          )}

          {!loading && suggestions.map(item => (
            <button
              key={item.symbol}
              type="button"
              onMouseDown={event => event.preventDefault()}
              onClick={() => {
                onChange(item.symbol);
                setOpen(false);
              }}
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: 3,
                width: '100%',
                textAlign: 'left',
                padding: '12px 14px',
                background: 'transparent',
                color: '#172033',
                border: 0,
                borderBottom: '1px solid #f1f5f9',
                cursor: 'pointer',
              }}
            >
              <strong style={{ fontSize: 13 }}>
                {item.symbol} — {item.name}
              </strong>
              <span style={{ fontSize: 11, opacity: .6 }}>
                {item.market === 'IN' ? 'India' : item.market === 'CA' ? 'Canada' : 'United States'}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
