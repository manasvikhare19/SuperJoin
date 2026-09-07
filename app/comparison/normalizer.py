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

    # Fiscal year detection - Check specific hyphenated ranges and FY prefixes before bare years
    if re.search(r'\b(2024-25|2024-2025|fy\s*25|fy\s*2025)\b', text):
        fy = "FY2025"
    elif re.search(r'\b(2023-24|2023-2024|fy\s*24|fy\s*2024)\b', text):
        fy = "FY2024"
    elif re.search(r'\b(2025-26|2025-2026|fy\s*26|fy\s*2026)\b', text):
        fy = "FY2026"
    elif re.search(r'\b(2022-23|2022-2023|fy\s*23|fy\s*2023)\b', text):
        fy = "FY2023"
    elif re.search(r'\b(2021-22|2021-2022|fy\s*22|fy\s*2022)\b', text):
        fy = "FY2022"
    elif re.search(r'\b(2025)\b', text):
        fy = "FY2025"
    elif re.search(r'\b(2024)\b', text):
        fy = "FY2024"
    elif re.search(r'\b(2023)\b', text):
        fy = "FY2023"

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
