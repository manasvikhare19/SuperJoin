import re
from typing import Dict, Any, List, Optional
import pymupdf

def detect_table_ambiguity(text: str) -> Dict[str, Any]:
    """
    Detects if raw extracted text exhibits table column collapse / flattening.
    For example: '74,540.82 66,586.61 81,415.38 72,253.01' in a single line or adjacent lines
    without clear column association.
    """
    lines = text.splitlines()
    ambiguous_rows = []

    # Regex matching consecutive financial / decimal numbers
    num_pattern = re.compile(r'(\(?-?₹?\d{1,3}(?:,\d{3})*(?:\.\d+)?%?\)?|\(?-?\d+\.\d+%?\)?|-)')

    for idx, line in enumerate(lines):
        matches = num_pattern.findall(line)
        # If a single line contains 3 or more multi-digit numbers or percentages
        numbers = [m for m in matches if any(c.isdigit() for c in m)]
        if len(numbers) >= 3 and len(line.strip().split()) <= 15:
            ambiguous_rows.append({
                "line_number": idx + 1,
                "raw_text": line.strip(),
                "extracted_numbers": numbers,
                "reason": "Collapsed multi-column financial row lacking explicit column headers"
            })

    is_ambiguous = len(ambiguous_rows) >= 2

    return {
        "is_ambiguous": is_ambiguous,
        "ambiguity_type": "AMBIGUOUS_TABLE_FLATTENING" if is_ambiguous else "NONE",
        "ambiguous_rows_count": len(ambiguous_rows),
        "sample_ambiguous_rows": ambiguous_rows[:3],
        "explanation": (
            "Naive text extraction flattened multi-period financial tables into unaligned number sequences. "
            "Without layout reconstruction, values cannot be deterministically mapped to FY23 vs FY24 or Standalone vs Consolidated."
            if is_ambiguous else "Text appears sequentially structured without obvious column collapse."
        )
    }

def extract_tables_from_page(pymupdf_page) -> List[Dict[str, Any]]:
    """
    Uses PyMuPDF layout-aware table finder to extract structured grids from PDF pages.
    """
    tables = []
    try:
        tabs = pymupdf_page.find_tables()
        for i, tab in enumerate(tabs):
            df_rows = tab.extract()
            if df_rows and len(df_rows) > 1:
                header = [str(c or "").strip() for c in df_rows[0]]
                rows = [[str(c or "").strip() for c in r] for r in df_rows[1:]]
                tables.append({
                    "table_index": i,
                    "bbox": tab.bbox,
                    "header": header,
                    "rows": rows,
                    "row_count": len(rows),
                    "col_count": len(header)
                })
    except Exception:
        pass
    return tables
