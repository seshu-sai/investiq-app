# Valuation and potential gains

Select a stock in Overview, then open **Valuation**. This view supports US, Canadian and Indian stocks when the required data is available.

- Your saved amount, base currency, risk level and horizon provide the starting inputs. Override the modeled amount, annual return hurdle or maximum loss on this screen and press **Apply goals**. Overrides do not overwrite your saved profile.
- Enter both your average buy price and shares owned to see unrealized gain/loss in the stock's currency. This is calculated from the latest available provider price, not your brokerage's executable bid/ask. Figures refresh every 60 seconds while the tab is visible.
- Inspect adjusted historical returns, maximum peak-to-trough drawdown, annualized volatility, a growth-of-100 chart and an ETF comparison over matching dates. Yahoo's adjusted daily closes approximate dividends and splits; prices and currency metadata remain unofficial. Historical returns are expressed in the stock currency.
- Review downside/base/upside earnings sensitivities and hypothetical gains/losses on the modeled budget. A dated daily FX rate converts the budget; base-currency gains hold FX constant. Actual currency movement, fees, tax, bid/ask spreads and dividend payments are excluded from the earnings sensitivities. The full-budget example is a calculator, not a position-size recommendation.
- Press **Research latest news** for a live, cited web search and a separate structured assessment. This makes OpenAI requests and can use API/tool credits. Price polling never calls OpenAI. The returned web sources appear as clickable inline citations; date extraction still requires source review. Each manual review is saved to the research audit history.

## Calculations and assumptions

Default modeled years are 1 for a 0–1 year preference, 2 for 1–3, 4 for 3–5, and 5 for 5+. The model never silently substitutes a long horizon for a short one.

Starting screening limits are policy defaults, not forecasts or measured risk tolerance:

| Saved risk | Annual return hurdle | Maximum loss | Annualized volatility limit |
| --- | --- | --- | --- |
| Low | 6% | 15% | 20% |
| Medium | 10% | 30% | 40% |
| High | 14% | 50% | 70% |

Valuation exposes the annual return hurdle, maximum historical drawdown, maximum annualized volatility and maximum modeled terminal downside loss. **More screening criteria** exposes minimum history, maximum trade quote age and minimum annual excess return over the market ETF. Click **Apply criteria** to recalculate the checklist, then **Research latest news** to review the same applied limits with cited web evidence. The research button also applies the current form values. Each checklist item and the applied-criteria summary show the actual values used.

Limits apply to the current stock screen; they do not update the saved profile. Blank fields use the profile defaults above. A blank downside limit follows the selected historical drawdown limit; enter a separate downside limit to screen terminal sensitivity independently. **Reset to profile defaults** clears all overrides and optional position inputs. Increasing tolerance does not make a stock safe or change its saved risk label.

Additional defaults are three years of history, a 15-minute trade quote age and at least zero percentage points of annual excess return. Required history is the larger of the chosen minimum and the modeled holding period. Quote age accepts 1–60 whole minutes, history 1–10 whole years, volatility 0–300%, downside 0–100%, and benchmark excess return −100 to +100 percentage points/year. Return and historical drawdown limits must be greater than zero and no more than 100%. These input bounds are validation limits, not recommended settings. Daily bars, missing financial evidence and invalid quotes remain disqualifying regardless of the chosen limits.

The earnings model requires three consecutive positive annual diluted-EPS records and positive trailing EPS in matching provider quote currency. Base growth is half the median observed annual EPS growth, bounded to -10% to +10%. Downside growth is at most zero, with an exit multiple of 80% of the lower of current P/E and 15. Base exit P/E is the lower of current P/E and 20; upside is the lower of current P/E and 25, with growth capped at 15%. These caps and shrinkage are explicit conservative assumptions. They are not peer-derived valuations, calibrated forecasts or analyst consensus. EPS revisions, ADR ratios and stock splits can complicate comparisons.

Future price sensitivity = trailing EPS × (1 + assumed growth)^years × assumed exit P/E.

Conditional entry threshold = base-case future price / (1 + annual return hurdle)^years. This is a required entry under those assumptions, not an independently verified intrinsic value. The existing SEC cash-flow model remains available separately at `/api/cash-flow-valuation/{market}/{symbol}` and retains its illustrative-only restrictions.

Historical holding-period replays start once per month and use actual calendar dates matching the modeled duration. Displayed 10th/50th/90th percentiles describe those past outcomes only. Windows overlap heavily: the page shows both the raw window count and an approximate independent-period count. Their positive frequency is not a probability of future profit. A positive historical 10th percentile does not establish downside protection. Missing/stale data withholds these estimates rather than substituting generic returns.

## Buy assessment

The page can show **INSUFFICIENT DATA**, **NOT SUITABLE**, **WAIT**, **AVOID**, or **BUY CANDIDATE**. A buy candidate is a research screening result, not a broker instruction or a guarantee.

Every quantitative check must pass before BUY CANDIDATE is allowed: a usable provider trade price within the applied quote-age limit, three recent consecutive annual periods, adequate history, drawdown/volatility within the selected limits, saved-market/asset/horizon fit, an available earnings sensitivity that clears the return hurdle and separate downside limit, historical excess return at least the chosen minimum versus the matching-market ETF, and available currency conversion. Daily bars cannot produce a buy candidate. CA/IN gains and history remain available, but a licensed intraday feed is needed for their candidate gate.

A manual web review must also support the candidate with dated events, at least one in the last 30 days, and citations from at least two distinct domains present in the actual web-search annotations. Event dates older than 120 days, future dates, fabricated citations, unsupported verdicts, incomplete/refused model responses and missing evidence retain the quantitative verdict. AVOID requires dated negative evidence. The model receives the explicit applied limits and computed checks; a custom volatility limit overrides the numeric risk preset. A news narrative cannot override a failed check. A displayed buy-candidate review expires after 15 minutes, and loses that signal earlier if refreshed quantitative checks fail. Editing inputs withholds the old buy-candidate signal; applying criteria clears the previous news review. Reviews can be reused on price refresh only for the same stock, profile context, budget and all seven resolved screening limits. Applied criteria are persisted in each manual research audit record.

These gates are intentionally transparent. They have not been validated as a profitable trading strategy. Holdings, taxes, concentration, liquidity needs and personal loss capacity still require review. The previous AI Research page retains its stricter BUY restriction; it does not use the new conditional screening verdict.

## API

- `GET /api/valuation/{market}/{symbol}`: current calculations, no model call. Optional query inputs: `amount`, `annual_goal`, `max_loss` (historical drawdown), `max_volatility`, `max_downside` (terminal scenario loss), `min_history_years`, `max_quote_age_minutes`, `min_excess_return` (percentage points/year), `cost_basis`, `shares`. Responses include `preferences.applied_screening`, `screening_defaults` and a resolved `screening_key` for review compatibility.
- `POST /api/valuation/{market}/{symbol}/research`: the same optional inputs in a JSON body, plus cited web research and audit persistence.
- `GET /api/cash-flow-valuation/{market}/{symbol}`: the original SEC cash-flow sensitivity endpoint (US only).

Price history and FX cache for 15 minutes. Fundamentals and filings cache for 5 minutes. Finnhub trade quotes cache for 15 seconds. A page refresh does not make annual statements or daily bars real-time.

Sources: [yfinance history API](https://ranaroussi.github.io/yfinance/reference/yfinance.price_history.html), [OpenAI web-search API and citation requirements](https://developers.openai.com/api/docs/guides/tools-web-search), [FINRA on return and historical performance](https://syndication.finra.org/content/key-concepts-return-and-rate-return).
