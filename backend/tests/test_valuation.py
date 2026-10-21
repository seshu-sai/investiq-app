from copy import deepcopy

import pytest

from app.financial_validation import validate_financial_evidence
from app.growth_analysis import analyze_cash_flow_growth
from app.trajectory import calculate_trajectory
from app.valuation import ValuationError, calculate_cash_flow_valuation


def test_sec_financial_validation_and_arithmetic(sample):
    financials = sample['financials']
    assert validate_financial_evidence(financials)['valid']
    financials['history'][-1]['cash_after_productive_asset_purchases'] += 1
    assert not validate_financial_evidence(financials)['valid']


def test_mismatched_cashflow_filings_rejected(sample):
    sample['financials']['history'][-1]['productive_asset_purchases_accession'] = 'different'
    assert not validate_financial_evidence(sample['financials'])['valid']


def test_growth_rejects_gaps_and_loss_years(sample):
    history = sample['financials']['history']
    assert analyze_cash_flow_growth(history)['valid']
    history[1]['cash_after_productive_asset_purchases'] = -10
    assert not analyze_cash_flow_growth(history)['valid']
    history[1]['cash_after_productive_asset_purchases'] = 25
    history[0]['fiscal_year_end'] = '2010-06-30'
    assert not analyze_cash_flow_growth(history)['valid']


def test_duplicate_years_rejected(sample):
    history = sample['financials']['history']
    history[1]['fiscal_year_end'] = history[0]['fiscal_year_end']
    assert not validate_financial_evidence(sample['financials'])['valid']


def test_zero_growth_discounted_cashflow_has_known_value():
    value = calculate_cash_flow_valuation(100, 10, 0, 0.1, 0, years=5)
    # A perpetuity paying 100 at 10% is worth 1000, divided by 10 shares.
    assert value['fair_value_per_share'] == pytest.approx(100)
    assert value['margin_of_safety_price'] == 75


@pytest.mark.parametrize('years', [0, 1.5, True, 11])
def test_invalid_projection_horizon(years):
    with pytest.raises(ValuationError):
        calculate_cash_flow_valuation(100, 10, 0.05, 0.1, 0.02, years=years)
    assert calculate_trajectory(100, 2, 50, years=years)['status'] == 'insufficient_data'


def test_terminal_growth_cannot_exceed_discount_rate():
    with pytest.raises(ValuationError):
        calculate_cash_flow_valuation(100, 10, 0.05, 0.02, 0.03)


def test_generic_scenarios_never_return_investment_verdict():
    result = calculate_trajectory(100, 2, 50)
    assert result['assessment'] == 'Hypothetical sensitivity analysis'
    assert all(row['target_price'] > 0 for row in result['scenarios'])
