"""Long-only, whole-share position arithmetic from explicit user inputs; no order execution."""
import math


def build_position_plan(quote, amount, fx_rate, *, risk_budget=None, planned_stop=None,
                        planned_target=None, max_quote_age_minutes=15):
    result = {'status': 'not_requested', 'reason': 'Enter a budget-risk percentage and planned exit price to calculate a position.',
              'risk_budget_percent': risk_budget, 'planned_stop': planned_stop, 'planned_target': planned_target,
              'note': 'Hypothetical whole-share calculation using the modeled budget, not verified client portfolio equity. A planned exit is not a guaranteed fill or maximum loss. Gaps, slippage, fees, FX changes and taxes can increase losses. No order is placed.'}
    if risk_budget is None or planned_stop is None:
        return result
    fresh = (quote.get('valid') and quote.get('status') != 'daily_bar'
             and quote.get('age_seconds', 1e9) <= max_quote_age_minutes * 60)
    if not fresh or fx_rate is None or fx_rate <= 0:
        return {**result, 'status': 'unavailable', 'reason': 'A fresh trade quote and currency conversion are required for position sizing.'}
    price = quote['price']
    if planned_stop >= price or (planned_target is not None and planned_target <= price):
        return {**result, 'status': 'invalid_levels',
                'reason': 'For a long position, planned exit must be below the current quote and any target must be above it. Recheck levels after price changes.'}
    per_share_loss = price - planned_stop
    cash = amount * fx_rate
    risk_cash = cash * risk_budget / 100
    units = math.floor(min(cash / price, risk_cash / per_share_loss))
    # Keep raw arithmetic for limits; round only displayed cash values.
    planned_loss = units * per_share_loss / fx_rate
    target_gain = units * (planned_target - price) / fx_rate if planned_target is not None else None
    return {**result, 'status': 'calculated', 'reason': 'Sized to the smaller of the available budget and your planned budget risk.',
            'shares': units, 'entry_reference': price, 'position_value': round(units * price / fx_rate, 2),
            'unallocated_budget': round(amount - units * price / fx_rate, 2),
            'budget_risk_amount': round(amount * risk_budget / 100, 2), 'planned_loss': round(planned_loss, 2),
            'planned_loss_percent': round(planned_loss / amount * 100, 4),
            'price_to_stop_percent': round(per_share_loss / price * 100, 2),
            'target_gain': round(target_gain, 2) if target_gain is not None else None,
            'reward_to_risk': round((planned_target - price) / per_share_loss, 2) if planned_target is not None else None}
