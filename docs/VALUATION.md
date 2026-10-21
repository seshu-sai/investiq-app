# Investing decisions and valuation

Choose **Analyse stock** beside a watchlist symbol, or open **Investing decisions** / **Valuation** for the selected stock. Both open the same beginner-friendly investing plan. The separate **Long-term estimates** view retains earnings scenarios and historical returns.

## Three ordinary questions

- **Money available for this stock:** the most money the hypothetical position may use, in your saved base currency.
- **How long might you hold it?:** about one, three or six months (4, 12 or 26 weeks). This explicit plan timeframe does not overwrite the saved long-term profile.
- **Money you are prepared to risk:** the planned loss if the chosen exit fills at its price, including estimated round-trip costs. Actual losses can be larger. The visible starting amount is 0.5%, 1% or 2% of the available money for saved low, medium or high risk, respectively. These are editable starting policies, not a measurement of loss capacity or a recommendation.

Press **Analyse stock** for calculations without an AI call. **Check company news** applies the same answers, searches the web and requests a cited review; it uses OpenAI API/tool credits. **Reset my answers** restores the visible starting answers and clears advanced overrides. No form action changes saved preferences or places an order.

## Weeks-to-months decision

The engine in `backend/app/opportunities.py` is independent of the five-year earnings screen. It requires a recent provider trade quote, company identity, saved-market/asset fit, currency conversion and at least 61 completed daily high/low/close sessions. Today's exchange-local bar is excluded. The last completed date must be within four calendar days, and gaps over ten days invalidate the recent levels. Daily bars cannot qualify as fresh trade quotes.

The entry rule requires the current quote and 20-session price average to be above the 50-session average. The automatic exit reference is the 20-session average when price is above it, otherwise the 50-session average, minus one Wilder 14-session average true range. The target reference is the highest traded price over the chosen holding period's trading-session lookback, capped at 126 sessions and actual available history. Neither reference is a future price forecast.

Estimated round-trip costs start at 0.2% of entry value, editable in Advanced options. With entry P, exit S, target T and round-trip cost fraction c:

- Per-share planned loss = P − S + P × c.
- Per-share target profit = T − P − P × c.
- Profit/loss ratio = per-share target profit / per-share planned loss.
- Whole shares = floor(min(available stock-currency money / [P × (1 + c/2)], stock-currency money-at-risk / per-share planned loss)).

The default minimum profit/loss ratio is 1.5, editable. It is an explicit rule, not a probability, optimized threshold or proof of profitability. For minimum ratio R, the highest entry satisfying that arithmetic is (T + R × S) / [(1 + R) × (1 + c)]. A lower price must still have a supportive trend, valid quote and affordable position; it is not an unconditional buy limit.

The main card shows conditional target profit, planned exit loss, money used, money left uninvested, whole shares, current price, maximum qualifying entry price and exit/target references. Money figures use the saved base currency; share prices use the stock currency. FX is dated daily and held unchanged for the calculations. The references are not broker orders, guaranteed fills or maximum losses. Gaps, fees, slippage, taxes and future FX changes can increase losses.

### Decision meanings

- **BUY SETUP:** the explicit entry rule and risk-sized arithmetic pass. Company news may still be unreviewed; the card identifies its status.
- **BUY CANDIDATE:** the numerical entry rule still passes and a validated cited company-news review supports it.
- **WAIT FOR BETTER PRICE:** net target profit is too small versus planned loss. The card shows a conditional entry threshold.
- **WAIT FOR TREND:** price/average trends are not aligned upward.
- **WAIT / INSUFFICIENT DATA:** required evidence, valid levels or an affordable whole-share position is missing.
- **AVOID:** validated dated negative company evidence overrides a price setup.

Saved low/medium/high risk presets determine a visible starting money-at-risk amount. Historical full-stock volatility and drawdown remain context, alongside long-term earnings weaknesses; they do not silently veto this separately sized short-term plan. If the user explicitly enters drawdown or volatility limits in Advanced options, only those selected stock-risk filters become binding. Saved markets/assets remain binding. This separation does not establish full portfolio suitability or make a volatile stock low risk.

A personal target above the observed range cannot manufacture a buy setup. Advanced exit/target inputs are explicit assumptions. Missing information remains missing; there is no weighted confidence percentage or expected-profit probability. This investing rule has not been validated as a profitable strategy or for out-of-sample use.

## Company-news review

The manual review follows the selected view. The weeks-to-months news reviewer receives company identity, the selected timeframe and source-page text; our five-year calculations are excluded from its input. The older long-term view has its own independently constrained review. The long-term screen may remain NOT SUITABLE while an independently risk-sized entry qualifies as a candidate; each is labeled with its timeframe.

The opportunity needs dated company evidence within 120 days, at least one positive event, a supportive review, and either a company/regulatory source or at least two cited source domains. It does not require a new positive announcement every 30 days. A negative stance requires dated negative evidence. All event URLs must resolve to actual web-search citation annotations. Each opportunity event also needs a short verbatim supporting quote from the actual fetched source-page text and a date found on that page. Technical indicators and our own long-term calculations cannot be presented as sourced company events. Dates in the future or over 120 days old, invented URLs, unverified source quotes/dates and incomplete/refused/invalid responses cannot produce a reviewed candidate. An honest mixed review may contain no events and remains explicitly limited.

Citation matching accepts URL tracking/presentation differences (UTM parameters, PDF presentation and fragments), preserving content-changing query parameters and restoring the actual searched URL in the output. Upcoming earnings dates are not treated as past event dates. Source pages are fetched without credentials, with public-address checks on redirects, bounded HTML size, timeout and concurrency. PDF presentation links are read through their equivalent HTML page; unavailable/blocked/non-HTML sources remain unverifiable. A review-validation failure is displayed separately from the numerical setup and is not interpreted as a negative business judgment. AI interpretation and company relevance still require source review.

Reviews expire after 15 minutes. Edits hide earlier buy decisions until reanalysis. New answers, optional risk filters, stock identity, saved profile context, budget and manual levels all affect review compatibility. A price refresh recomputes current sizing/levels; it may reuse only the unexpired matching news conclusion, never old price arithmetic. A failed current entry rule cannot be promoted by earlier good news. Manual reviews are audited with both assessments, assumptions and the primary opportunity verdict.

## Advanced options and long-term estimates

Advanced controls retain optional personal exit/target prices, minimum profit/loss ratio, estimated trading costs, historical drawdown/volatility limits, annual return goal, modeled terminal-loss tolerance, minimum historical coverage, maximum trade quote age, historical benchmark requirement and existing ownership inputs. Ordinary users need only the three visible answers. The older financial-background AI review remains available under a clearly labeled disclosure and does not issue buy instructions.

Long-term modeled years are 1 for a saved 0–1 year preference, 2 for 1–3, 4 for 3–5 and 5 for 5+. Starting long-term defaults are:

| Saved risk | Annual return hurdle | Historical loss limit | Annualized volatility limit |
| --- | --- | --- | --- |
| Low | 6% | 15% | 20% |
| Medium | 10% | 30% | 40% |
| High | 14% | 50% | 70% |

These are policy defaults. Three consecutive recent positive annual EPS records and positive same-currency trailing EPS are required for earnings sensitivities. Base growth is half the median historical annual EPS change, capped between −10% and +10%. Base exit P/E is the lower of current P/E and 20. Downside growth is at most zero, with 80% of the lower of current P/E and 15. Upside growth is capped at 15%, with an exit P/E capped at 25. Future price = trailing EPS × (1 + assumed growth)^years × exit P/E. These are conditional assumptions, not calibrated forecasts or independently verified fair values.

Long-term cash gains assume the full modeled budget is invested. They are separate from the smaller risk-sized opportunity position, exclude dividends/costs/taxes/future FX changes and must not be added to its target-profit figure. The goal entry threshold is the entry required under the base assumptions, not a verified buy price.

Historical returns use dividend/split-adjusted closes, unlike price-only trend indicators. The growth-of-100 chart, matching-date market ETF comparison, maximum drawdown, volatility and monthly-start holding-period percentile replays describe the past. Overlapping windows are not independent and their positive frequency is not a forecast probability. Cash replays hold FX unchanged.

The old long-term BUY CANDIDATE gate still requires all its quantitative checks, adequate history covering the holding period, suitable saved horizon/markets/assets, earnings hurdle/downside passes, benchmark threshold, currency conversion and recent multi-domain web evidence. Its restrictions do not decide the new weeks-to-months opportunity.

## API and freshness

- `GET /api/valuation/{market}/{symbol}` calculates both views without an AI call.
- `POST /api/valuation/{market}/{symbol}/research` takes the same JSON options, adds manual cited review and saves an audit record. `review_scope` selects `opportunity` (default) or `long_term`; it is removed before the calculation and retained in the audit.
- Beginner inputs: `amount`, `holding_weeks` (whole number 4–26), `loss_amount` (positive, no greater than available money).
- Optional entry inputs: `min_reward_risk` (0.5–10), `round_trip_cost_percent` (0–10), `planned_stop`, `planned_target` (positive stock-currency prices). With `loss_amount`, levels may be supplied separately. Legacy `risk_budget` requires a stop and cannot be combined with `loss_amount`.
- Legacy inputs remain `annual_goal`, `max_loss`, `max_volatility`, `max_downside`, `min_history_years`, `max_quote_age_minutes`, `min_excess_return`, `cost_basis` and `shares`.
- Responses add `opportunity` alongside `market_setup`, `position_plan` and the long-term `buy_assessment`. Each opportunity includes resolved answers, checks, levels, monetary calculations and a review-compatibility key.
- The original SEC cash-flow endpoint remains `/api/cash-flow-valuation/{market}/{symbol}`.

Prices refresh every 60 seconds while visible. Finnhub trade quotes cache for 15 seconds; history and FX for 15 minutes; fundamentals/filings for five minutes. Real-time labeling still needs provider entitlement and a timestamp within two minutes. CA/IN data is daily and cannot produce an actionable fresh-trade setup. This is not an intraday streaming or automated execution system.

Sources: [Fidelity ATR](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/atr), [Fidelity moving averages](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/sma), [yfinance history](https://ranaroussi.github.io/yfinance/reference/yfinance.price_history.html), [OpenAI web search](https://developers.openai.com/api/docs/guides/tools-web-search), [FINRA order types and stop risks](https://syndication.finra.org/content/understanding-order-types-can-save-time-and-money).
