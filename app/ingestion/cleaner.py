import re

def clean_extracted_text(text: str) -> str:
    """
    Cleans raw PDF text while strictly preserving:
    - Currency symbols (₹, $, €, £)
    - Financial figures, commas, decimals, percentages
    - Negative accounting representations (e.g. ₹(452) Cr)
    - Metric qualifiers and dates (FY24, 2023-24, Q4, etc.)
    """
    if not text:
        return ""

    # Normalize unicode spaces and non-breaking spaces
    cleaned = text.replace('\xa0', ' ').replace('\u200b', '')

    # Fix soft hyphens and hyphenated word breaks at end of line (e.g. "opera- \n tions" -> "operations")
    cleaned = re.sub(r'(\b[A-Za-z]+)-\s*\n\s*([A-Za-z]+\b)', r'\1\2', cleaned)

    # Clean multiple spaces and tabs within a line
    cleaned = re.sub(r'[ \t]+', ' ', cleaned)

    # Clean excessive blank lines (more than 2 consecutive newlines)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)

    # Strip whitespace on each line
    lines = [line.strip() for line in cleaned.splitlines()]
    
    # Filter out standalone header/footer page artifacts like "Page 1 of 100" or single isolated numbers if clearly page indicators
    filtered_lines = []
    for line in lines:
        if not line:
            filtered_lines.append("")
            continue
        # Skip purely page numbers like "143" or "Page 22" if short and isolated
        if re.match(r'^(page\s*\d+(\s*of\s*\d+)?|\d{1,3})$', line, re.IGNORECASE) and len(line) < 15:
            continue
        filtered_lines.append(line)

    result = '\n'.join(filtered_lines).strip()
    return result
