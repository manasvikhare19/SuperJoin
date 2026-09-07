import re
from typing import Optional, Tuple

def normalize_time_period(period_str: str) -> str:
    """
    Normalizes diverse financial year notations to standard canonical strings.
    e.g. 'FY24', 'FY 2023-24', '2023-24', 'FY2024' -> 'FY2024'
    'Q4 FY24', 'Q4 2023-24' -> 'Q4-FY2024'
    """
    if not period_str:
        return ""
    text = period_str.strip().lower()

    # Quarter detection
    quarter = None
    fy = None
    q_match = re.search(r'\b(q[1-4]|first quarter|second quarter|third quarter|fourth quarter)\b', text)
    if q_match:
        q_raw = q_match.group(1)
        if "first" in q_raw or "q1" in q_raw:
            quarter = "Q1"
        elif "second" in q_raw or "q2" in q_raw:
            quarter = "Q2"
        elif "third" in q_raw or "q3" in q_raw:
            quarter = "Q3"
        elif "fourth" in q_raw or "q4" in q_raw:
            quarter = "Q4"

    # Generic fiscal year and range detection for arbitrary years (e.g. 1990-2099)
    # 1. Hyphenated/slashed year range (e.g., 2023-24, 2023-2024, FY 2024-25) -> ending year FY
    range_match = re.search(r'\b(?:fy\s*)?(\d{4})\s*[-/]\s*(\d{2,4})\b', text)
    if range_match:
        y1_str, y2_str = range_match.group(1), range_match.group(2)
        if len(y2_str) == 2:
            fy = f"FY{y1_str[:2]}{y2_str}"
        else:
            fy = f"FY{y2_str}"

    # 2. 2-digit range (e.g., 23-24, FY 23-24)
    if not fy:
        range_2d = re.search(r'\b(?:fy\s*)?(\d{2})\s*[-/]\s*(\d{2})\b', text)
        if range_2d:
            y2_val = int(range_2d.group(2))
            century = 2000 if y2_val < 50 else 1900
            fy = f"FY{century + y2_val}"

    # 3. Explicit FY prefix with 2 or 4 digits (e.g., FY24, FY 2025, FY30)
    if not fy:
        fy_match = re.search(r'\bfy\s*(\d{2,4})\b', text)
        if fy_match:
            digits = fy_match.group(1)
            if len(digits) == 2:
                y_val = int(digits)
                century = 2000 if y_val < 50 else 1900
                fy = f"FY{century + y_val}"
            elif len(digits) == 4:
                fy = f"FY{digits}"

    # 4. Standalone 4-digit calendar/fiscal year (e.g., 2024, 2018, 2030)
    if not fy:
        year_match = re.search(r'\b(19\d{2}|20\d{2})\b', text)
        if year_match:
            fy = f"FY{year_match.group(1)}"

    if quarter and fy:
        return f"{quarter}-{fy}"
    if fy:
        return fy
    if quarter:
        return quarter
    return period_str.strip()

def extract_numeric_value(val_str: str) -> Optional[float]:
    """Extracts floating point number from string, removing commas and symbols."""
    if not val_str:
        return None
    cleaned = val_str.replace(',', '').replace('₹', '').replace('$', '').replace('%', '').strip()
    match = re.search(r'[-+]?\d*\.?\d+', cleaned)
    if match:
        try:
            return float(match.group())
        except ValueError:
            return None
    return None

def normalize_to_inr_crore(val_str: str, unit_str: str) -> Optional[float]:
    """
    Normalizes Indian and global financial amounts to INR Crore.
    1 Crore = 10 Million = 100 Lakh = 0.01 Billion
    1 Billion = 100 Crore = 1,000 Million
    1 Million INR = 0.1 Crore
    1 Lakh INR = 0.01 Crore
    """
    num = extract_numeric_value(val_str)
    if num is None:
        return None

    unit = (unit_str or "").lower() + " " + val_str.lower()

    if "crore" in unit or "cr" in unit:
        return num
    elif "billion" in unit or "bn" in unit:
        # 1 Billion INR = 100 Crore
        return num * 100.0
    elif "million" in unit or "mn" in unit:
        # 1 Million INR = 0.1 Crore (10 Million = 1 Crore)
        return num * 0.1
    elif "lakh" in unit or "lac" in unit:
        # 1 Lakh INR = 0.01 Crore
        return num * 0.01

    return None

def are_numerically_equivalent(
    val_a: str,
    unit_a: str,
    val_b: str,
    unit_b: str,
    tolerance_pct: float = 0.015
) -> Tuple[bool, Optional[str]]:
    """
    Checks if two values are numerically equivalent under standard scale conversions
    (e.g., ₹81,415.38 million vs ₹8,142 crore).
    Tolerance defaults to 1.5% to account for corporate rounding.
    """
    # Direct numeric check
    num_a = extract_numeric_value(val_a)
    num_b = extract_numeric_value(val_b)
    if num_a is not None and num_b is not None:
        if abs(num_a - num_b) < 1e-5:
            return True, "Exact numerical match"

    # Normalized INR Crore check
    cr_a = normalize_to_inr_crore(val_a, unit_a)
    cr_b = normalize_to_inr_crore(val_b, unit_b)

    if cr_a is not None and cr_b is not None and cr_a > 0 and cr_b > 0:
        diff_pct = abs(cr_a - cr_b) / max(cr_a, cr_b)
        if diff_pct <= tolerance_pct:
            return True, f"Unit-normalized match: {val_a} {unit_a} (~{cr_a:.2f} Cr) is equivalent to {val_b} {unit_b} (~{cr_b:.2f} Cr)"

    return False, None
