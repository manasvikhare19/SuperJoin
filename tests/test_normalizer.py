import pytest
from app.comparison.normalizer import (
    normalize_time_period,
    extract_numeric_value,
    normalize_to_inr_crore,
    are_numerically_equivalent
)

def test_normalize_time_period():
    assert normalize_time_period("FY24") == "FY2024"
    assert normalize_time_period("2023-24") == "FY2024"
    assert normalize_time_period("FY 2024-25") == "FY2025"
    assert normalize_time_period("Q4 FY24") == "Q4-FY2024"
    assert normalize_time_period("Fourth Quarter 2024") == "Q4-FY2024"
    assert normalize_time_period("Q4") == "Q4"
    assert normalize_time_period("current") == "current"
    # Arbitrary years (past and future beyond 2021-2026)
    assert normalize_time_period("2018-19") == "FY2019"
    assert normalize_time_period("FY 2035") == "FY2035"
    assert normalize_time_period("2031-2032") == "FY2032"
    assert normalize_time_period("Q1 FY32") == "Q1-FY2032"

def test_extract_numeric_value():
    assert extract_numeric_value("₹8,142.50 Cr") == 8142.50
    assert extract_numeric_value("(452)") == 452.0
    assert extract_numeric_value("6.4%") == 6.4

def test_normalize_to_inr_crore():
    # 10 Million INR = 1 Crore INR -> 81415.38 Million INR = 8141.538 Crore
    cr_val = normalize_to_inr_crore("81415.38", "million inr")
    assert pytest.approx(cr_val, 0.1) == 8141.54

    # 1 Billion INR = 100 Crore INR
    cr_bn = normalize_to_inr_crore("10", "billion inr")
    assert cr_bn == 1000.0

def test_are_numerically_equivalent():
    # Annual Report ₹81,415.38 Million vs Presentation ₹8,142 Crore
    is_equiv, reason = are_numerically_equivalent(
        val_a="81,415.38",
        unit_a="Million INR",
        val_b="8,142",
        unit_b="INR Crore"
    )
    assert is_equiv is True
    assert "Unit-normalized match" in reason

def test_unit_dimensional_compatibility():
    from app.comparison.normalizer import classify_unit_dimension, are_units_dimensionally_compatible
    assert classify_unit_dimension("percent") == "PERCENTAGE"
    assert classify_unit_dimension("INR crore") == "CURRENCY"
    assert classify_unit_dimension("million INR") == "CURRENCY"
    assert classify_unit_dimension("tons") == "VOLUME_COUNT"

    # Percentage and currency can NEVER be compatible or contradictory
    assert are_units_dimensionally_compatible("percent", "million INR") is False
    assert are_units_dimensionally_compatible("INR crore", "million INR") is True
    assert are_units_dimensionally_compatible("percent", "%") is True
