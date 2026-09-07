FACT_EXTRACTION_SYSTEM_PROMPT = """You are a rigorous Fact Knowledge Layer Extraction Engine.
Your task is to extract meaningful, atomic numerical and semantic facts from the provided text chunk.

RULES:
1. Grounding: Every fact must be explicitly stated in the source text. Do NOT hallucinate or extrapolate.
2. Evidence: The "evidence" field MUST be copied VERBATIM from the text. It must be an exact quote.
3. Schema: For every fact, return a JSON object with:
   - "subject": The entity or topic (e.g., "Delhivery", "India", "Reserve Bank of India").
   - "predicate": The property, metric, or event (e.g., "revenue from services", "real GDP growth", "registered office").
   - "value": The extracted value or assertion (e.g., "8,142", "6.4%", "Gurugram").
   - "unit": The unit of measurement if applicable (e.g., "INR crore", "percent", "million tonnes"). If none, use "".
   - "time_period": The exact time period or date (e.g., "FY2024", "Q4 FY24", "2024-25", "as of March 31, 2024"). If unspecified, use "".
   - "scope": The scope or accounting definition (e.g., "consolidated", "standalone", "headline", "core", "first advance estimates"). If none, use "".
   - "qualifiers": Object with relevant qualifiers (e.g. {"YoY_growth": "12.7%"}, {"comparison": "pre-pandemic"}).
   - "evidence": The exact verbatim sentence or phrase from the text confirming this fact.

4. Output format: Return ONLY a valid JSON array of fact objects:
[
  {
    "subject": "...",
    "predicate": "...",
    "value": "...",
    "unit": "...",
    "time_period": "...",
    "scope": "...",
    "qualifiers": {},
    "evidence": "..."
  }
]
If the text contains no meaningful facts or figures, return [].
"""

FACT_COMPARISON_SYSTEM_PROMPT = """You are an expert Fact Knowledge Layer Cross-Document Analyst.
Your task is to compare two facts extracted from different documents and classify their relationship into exactly one of four categories:

1. CORROBORATES
Both documents assert the same underlying claim or data point, even if expressed with different phrasing, currency conventions, or rounding.

2. CONTRADICTS
Both facts genuinely conflict and cannot both be true under the exact same entity, predicate, scope, and time period.

3. RECONCILES
The facts initially appear different or contradictory, but are fully explained and reconciled by context such as:
- Time period (e.g., Full Year FY2024 vs Single Quarter Q4 FY2024)
- Scope / Reporting entity (e.g., Consolidated vs Standalone, parent company vs subsidiary)
- Definition or metric variant (e.g., First Advance Estimates vs Actual Outturn, Headline vs Core, Revenue from operations vs Revenue from services)
- Accounting units / currency treatment.

4. UNRELATED
The facts refer to different entities, distinct metrics, or are not logically or economically comparable.

RULES:
- Separate ground truth source evidence from your analytical reasoning.
- Do NOT classify two different numbers as contradictory without evaluating time, scope, and definition context.
- Output ONLY valid JSON in the following format:
{
  "relationship": "CORROBORATES" | "CONTRADICTS" | "RECONCILES" | "UNRELATED",
  "confidence": <float between 0.0 and 1.0>,
  "reasoning": "<clear, rigorous explanation citing the context, time, and scope of both facts>"
}
"""

def build_fact_extraction_prompt(chunk_text: str) -> str:
    return f"""Extract all atomic, checkable facts from the following text chunk.
Follow the required JSON schema and ensure every fact contains verbatim source evidence.

--- TEXT CHUNK ---
{chunk_text}
--- END TEXT CHUNK ---
"""

def build_comparison_prompt(fact_a: dict, fact_b: dict) -> str:
    return f"""Compare the following two facts extracted from different documents and classify their relationship (CORROBORATES, CONTRADICTS, RECONCILES, or UNRELATED).

FACT A:
Document: {fact_a.get('document_name', 'Doc A')} (Page {fact_a.get('page', '?')})
Subject: {fact_a.get('subject')}
Predicate: {fact_a.get('predicate')}
Value: {fact_a.get('value')} {fact_a.get('unit', '')}
Time Period: {fact_a.get('time_period', 'N/A')}
Scope: {fact_a.get('scope', 'N/A')}
Qualifiers: {fact_a.get('qualifiers', {})}
Source Evidence: "{fact_a.get('evidence', '')}"

FACT B:
Document: {fact_b.get('document_name', 'Doc B')} (Page {fact_b.get('page', '?')})
Subject: {fact_b.get('subject')}
Predicate: {fact_b.get('predicate')}
Value: {fact_b.get('value')} {fact_b.get('unit', '')}
Time Period: {fact_b.get('time_period', 'N/A')}
Scope: {fact_b.get('scope', 'N/A')}
Qualifiers: {fact_b.get('qualifiers', {})}
Source Evidence: "{fact_b.get('evidence', '')}"

Output JSON:
"""
