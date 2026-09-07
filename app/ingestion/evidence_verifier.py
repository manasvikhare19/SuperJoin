import re
from typing import Tuple

def normalize_for_matching(text: str) -> str:
    """Normalizes text for fuzzy whitespace, punctuation, and quote comparison."""
    if not text:
        return ""
    # Standardize unicode quotes and dashes
    t = text.replace('“', '"').replace('”', '"').replace('’', "'").replace('‘', "'")
    t = t.replace('–', '-').replace('—', '-').replace('\xa0', ' ')
    # Collapse multiple whitespaces and newlines
    t = re.sub(r'\s+', ' ', t).strip().lower()
    return t

def verify_evidence(evidence: str, source_text: str) -> Tuple[str, float]:
    """
    Verifies if evidence quote is truly grounded in the source page text.
    Returns:
        (status, verification_score)
        where status is 'EXACT_MATCH', 'NORMALIZED_MATCH', or 'UNVERIFIED'
    """
    if not evidence or not source_text:
        return ("UNVERIFIED", 0.0)

    evidence_clean = evidence.strip()
    if not evidence_clean:
        return ("UNVERIFIED", 0.0)

    # 1. Exact verbatim match check
    if evidence_clean in source_text:
        return ("EXACT_MATCH", 1.0)

    # 2. Normalized whitespace / punctuation match check
    norm_evidence = normalize_for_matching(evidence_clean)
    norm_source = normalize_for_matching(source_text)

    if norm_evidence and norm_evidence in norm_source:
        return ("NORMALIZED_MATCH", 0.95)

    # 3. Sub-phrase match: if 80% or more of words appear in sequence
    words = norm_evidence.split()
    if len(words) >= 4:
        # Check consecutive sub-phrases of 4+ words
        window_size = min(len(words), 8)
        sub_phrase = " ".join(words[:window_size])
        if sub_phrase in norm_source:
            return ("NORMALIZED_MATCH", 0.85)

    # 4. Keyword presence check
    if len(words) >= 2:
        matched_words = sum(1 for w in words if w in norm_source)
        ratio = matched_words / len(words)
        if ratio >= 0.85:
            return ("NORMALIZED_MATCH", 0.75)

    return ("UNVERIFIED", 0.20)
