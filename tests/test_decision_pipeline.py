import pytest
from app.database.models import FactRecord
from app.comparison.decision_pipeline import (
    check_entity_compatibility,
    check_predicate_compatibility,
    analyze_time_relationship,
    analyze_scope_relationship,
    evaluate_fact_relationship
)
from app.ingestion.evidence_verifier import verify_evidence
from app.ingestion.table_parser import detect_table_ambiguity

def test_entity_compatibility():
    # Compatible entities
    ok, score, _ = check_entity_compatibility("Delhivery", "Delhivery Limited")
    assert ok is True
    assert score >= 0.85

    ok, score, _ = check_entity_compatibility("RBI", "Reserve Bank of India")
    assert ok is True
    assert score >= 0.85

    # Completely distinct entities
    ok, score, _ = check_entity_compatibility("Delhivery", "India")
    assert ok is False
    assert score <= 0.2

def test_predicate_compatibility():
    ok, score, _ = check_predicate_compatibility("revenue from operations", "revenue from services")
    assert ok is True
    assert score >= 0.85

    ok, score, _ = check_predicate_compatibility("revenue from operations", "PTL freight tonnage")
    assert ok is False
    assert score <= 0.3

def test_time_subset_relationship():
    rel, score, _ = analyze_time_relationship("FY2024", "Q4-FY2024")
    assert rel == "SUBSET"
    assert score >= 0.9

def test_scope_divergence():
    rel, score, _ = analyze_scope_relationship("consolidated", "standalone")
    assert rel == "SCOPE_DIVERGENCE"
    assert score >= 0.9

def test_decision_pipeline_prevents_false_reconciliation():
    """
    CRITICAL TEST: Ensures unrelated entities with different periods
    are classified as UNRELATED, not falsely RECONCILED.
    """
    fact_delhivery = FactRecord(
        id=1,
        document_id=1,
        page=22,
        subject="Delhivery",
        predicate="revenue from operations",
        value="81415.38",
        unit="million INR",
        time_period="FY2024",
        scope="consolidated",
        evidence="Revenue from Operations 81,415.38",
        fact_json="{}"
    )

    fact_india = FactRecord(
        id=2,
        document_id=2,
        page=4,
        subject="India",
        predicate="real GDP growth",
        value="6.4",
        unit="percent",
        time_period="FY2025",
        scope="national",
        evidence="India real GDP estimated to grow by 6.4 per cent in FY25",
        fact_json="{}"
    )

    res = evaluate_fact_relationship(fact_delhivery, fact_india, similarity=0.30)
    assert res.relationship == "UNRELATED"
    assert "distinct" in res.reasoning.lower() or "different" in res.reasoning.lower()
    assert "Rejected CORROBORATES" in res.why_not_explanation

def test_decision_pipeline_corroboration():
    fact_ar = FactRecord(
        id=1,
        document_id=1,
        page=22,
        subject="Delhivery",
        predicate="revenue from operations",
        value="81415.38",
        unit="million INR",
        time_period="FY2024",
        scope="consolidated",
        evidence="Revenue from Operations 81,415.38",
        fact_json="{}"
    )

    fact_pres = FactRecord(
        id=2,
        document_id=2,
        page=6,
        subject="Delhivery",
        predicate="revenue from services",
        value="8142",
        unit="INR crore",
        time_period="FY2024",
        scope="consolidated",
        evidence="₹8,142 Cr FY24 revenue from services",
        fact_json="{}"
    )

    res = evaluate_fact_relationship(fact_ar, fact_pres, similarity=0.90)
    assert res.relationship == "CORROBORATES"
    assert res.confidence >= 0.85
    assert len(res.why_explanation) > 10
    assert len(res.why_not_explanation) > 10

def test_decision_pipeline_temporal_reconciliation():
    fact_full_year = FactRecord(
        id=1,
        document_id=1,
        page=6,
        subject="Delhivery",
        predicate="revenue from services",
        value="8142",
        unit="INR crore",
        time_period="FY2024",
        scope="consolidated",
        evidence="₹8,142 Cr FY24 revenue from services",
        fact_json="{}"
    )

    fact_quarter = FactRecord(
        id=2,
        document_id=1,
        page=7,
        subject="Delhivery",
        predicate="revenue from services",
        value="2076",
        unit="INR crore",
        time_period="Q4-FY2024",
        scope="consolidated",
        evidence="₹2,076 Cr Q4 FY24 revenue from services",
        fact_json="{}"
    )

    res = evaluate_fact_relationship(fact_full_year, fact_quarter, similarity=0.85)
    assert res.relationship == "RECONCILES"
    assert "temporal" in res.why_explanation.lower() or "subset" in res.why_explanation.lower()
    assert "Rejected CONTRADICTS" in res.why_not_explanation

def test_evidence_verifier():
    source_page = "Revenue from operations on consolidated basis for FY24 stood at ₹81,415.38 million."
    
    # Exact match
    status, score = verify_evidence("₹81,415.38 million", source_page)
    assert status == "EXACT_MATCH"
    assert score == 1.0

    # Normalized whitespace and dash match
    status, score = verify_evidence("Revenue  from   operations   on  consolidated basis", source_page)
    assert status == "NORMALIZED_MATCH"
    assert score >= 0.90

    # Non-existent quote
    status, score = verify_evidence("Unrelated random claims about something else", source_page)
    assert status == "UNVERIFIED"

def test_table_ambiguity_detector():
    flattened_text = (
        "Revenue from operations 74,540.82 66,586.61 81,415.38 72,253.01\n"
        "Total income 78,286.02 69,415.75 85,423.69 75,424.19"
    )
    res = detect_table_ambiguity(flattened_text)
    assert res["is_ambiguous"] is True
    assert res["ambiguity_type"] == "AMBIGUOUS_TABLE_FLATTENING"

def test_generic_acronym_matching():
    ok1, score1, _ = check_entity_compatibility("SEBI", "Securities and Exchange Board of India")
    assert ok1 is True
    assert score1 >= 0.90

    ok2, score2, _ = check_entity_compatibility("IMF", "International Monetary Fund")
    assert ok2 is True
    assert score2 >= 0.90

def test_llm_primacy_adopted():
    fact_a = FactRecord(
        id=1, document_id=1, page=1, subject="Tesla Inc", predicate="total revenue",
        value="96.77", unit="billion USD", time_period="FY2023", scope="consolidated",
        evidence="Tesla total revenue reached 96.77 billion USD in FY2023.", fact_json="{}"
    )
    fact_b = FactRecord(
        id=2, document_id=2, page=3, subject="Tesla", predicate="revenue",
        value="96.77", unit="billion USD", time_period="FY2023", scope="consolidated",
        evidence="Full year 2023 revenue recorded at 96.77 billion USD.", fact_json="{}"
    )

    res = evaluate_fact_relationship(
        fact_a=fact_a,
        fact_b=fact_b,
        similarity=0.92,
        llm_relationship="CORROBORATES",
        llm_confidence=0.96,
        llm_reasoning="Both filings confirm identical consolidated revenue of 96.77B USD for Tesla in FY23."
    )
    assert res.relationship == "CORROBORATES"
    assert res.confidence >= 0.90
    assert "Both filings confirm" in res.reasoning

def test_llm_guardrail_catches_false_contradiction():
    fact_year = FactRecord(
        id=1, document_id=1, page=10, subject="Alphabet", predicate="revenues",
        value="307.4", unit="billion USD", time_period="FY2023", scope="consolidated",
        evidence="Annual revenue reached 307.4 billion.", fact_json="{}"
    )
    fact_q4 = FactRecord(
        id=2, document_id=1, page=15, subject="Alphabet", predicate="revenues",
        value="86.3", unit="billion USD", time_period="Q4-FY2023", scope="consolidated",
        evidence="Fourth quarter revenue was 86.3 billion.", fact_json="{}"
    )

    # LLM mistakenly flagged CONTRADICTS due to differing figures
    res = evaluate_fact_relationship(
        fact_a=fact_year,
        fact_b=fact_q4,
        similarity=0.88,
        llm_relationship="CONTRADICTS",
        llm_confidence=0.90,
        llm_reasoning="Figures 307.4 and 86.3 do not match."
    )
    # Structural guardrail intervenes and changes to RECONCILES
    assert res.relationship == "RECONCILES"
    assert "Structural guardrail reconciliation" in res.why_explanation

def test_unit_dimensional_guardrail_prevents_false_contradiction():
    fact_revenue = FactRecord(
        id=1, document_id=1, page=22, subject="Delhivery", predicate="revenue from operations",
        value="81415.38", unit="million INR", time_period="FY2024", scope="consolidated",
        evidence="Consolidated revenue from operations for FY24 was 81,415.38 million INR.", fact_json="{}"
    )
    fact_concentration = FactRecord(
        id=2, document_id=1, page=138, subject="Delhivery", predicate="revenue from operations", # mislabeled by heuristic
        value="10.82", unit="percent", time_period="FY2024", scope="consolidated",
        evidence="Revenue from one customer exceeded 10% of total revenue amounting to 10.82%.", fact_json="{}"
    )

    res = evaluate_fact_relationship(
        fact_a=fact_revenue,
        fact_b=fact_concentration,
        similarity=0.75
    )
    assert res.relationship == "UNRELATED"
    assert "incompatible physical/economic dimensions" in res.reasoning
    assert "Rejected CONTRADICTS" in res.why_not_explanation

def test_evidence_guardrail_prevents_false_contradiction():
    # Both are percentages for Delhivery FY2024, but evidence proves distinct disclosures
    fact_customer = FactRecord(
        id=1, document_id=1, page=138, subject="Delhivery", predicate="percentage share",
        value="10.82", unit="percent", time_period="FY2024", scope="consolidated",
        evidence="During the year ended March 31, 2024, revenue from one customer exceeded 10% of total revenue amounting to 10.82%.", fact_json="{}"
    )
    fact_fair_value = FactRecord(
        id=2, document_id=1, page=218, subject="Delhivery", predicate="percentage share",
        value="89.53", unit="percent", time_period="FY2024", scope="consolidated",
        evidence="The group has recognized a net fair value loss on financial instruments at fair value through profit or loss amounting to 89.53%.", fact_json="{}"
    )

    res = evaluate_fact_relationship(
        fact_a=fact_customer,
        fact_b=fact_fair_value,
        similarity=0.70
    )
    assert res.relationship == "UNRELATED"
    assert "Semantic evidence guardrail overrule" in res.reasoning
    assert "below contradiction threshold" in res.reasoning

def test_evidence_guardrail_allows_true_contradiction():
    # Both discuss PTL freight services share for Delhivery FY24 with conflicting numbers
    fact_a = FactRecord(
        id=1, document_id=1, page=6, subject="Delhivery", predicate="PTL freight revenue contribution",
        value="29.82", unit="percent", time_period="FY2024", scope="consolidated",
        evidence="PTL freight services revenue contributed 29.82% of total express logistics revenue in FY24.", fact_json="{}"
    )
    fact_b = FactRecord(
        id=2, document_id=2, page=12, subject="Delhivery", predicate="PTL freight revenue contribution",
        value="35.50", unit="percent", time_period="FY2024", scope="consolidated",
        evidence="PTL freight services revenue contributed 35.50% of total express logistics revenue in FY24.", fact_json="{}"
    )

    res = evaluate_fact_relationship(
        fact_a=fact_a,
        fact_b=fact_b,
        similarity=0.92
    )
    assert res.relationship == "CONTRADICTS"
    assert "Direct empirical contradiction" in res.reasoning

def test_adversarial_high_lexical_overlap_distinct_dimensions():
    """
    Adversarial test: High lexical overlap (Delhivery, operations, numbers)
    with incompatible physical dimensions (Currency vs Count) must NEVER
    falsely contradict or corroborate.
    """
    fact_rev = FactRecord(
        id=1, document_id=1, page=22, subject="Delhivery", predicate="revenue from operations",
        value="81415.38", unit="million INR", time_period="FY2024", scope="consolidated",
        evidence="Consolidated revenue from operations for FY24 reached 81,415.38 million INR.", fact_json="{}"
    )
    fact_count = FactRecord(
        id=2, document_id=1, page=45, subject="Delhivery", predicate="operational team count",
        value="57000", unit="employees", time_period="FY2024", scope="consolidated",
        evidence="Delhivery deployed an operational team count of 57,000 employees nationwide.", fact_json="{}"
    )

    res = evaluate_fact_relationship(
        fact_a=fact_rev,
        fact_b=fact_count,
        similarity=0.72
    )
    assert res.relationship == "UNRELATED"
    assert "incompatible physical/economic dimensions" in res.reasoning
    assert "Rejected CONTRADICTS" in res.why_not_explanation

def test_adversarial_ratio_vs_absolute_total():
    """
    Adversarial test: Percentage metric vs Absolute currency metric
    must be recognized as dimensionally distinct, even if subject and predicate overlap.
    """
    fact_ebitda_margin = FactRecord(
        id=1, document_id=1, page=5, subject="Delhivery", predicate="adjusted EBITDA margin",
        value="12.5", unit="percent", time_period="FY2024", scope="consolidated",
        evidence="Adjusted EBITDA margin expanded by 120 bps to 12.5% for the full year.", fact_json="{}"
    )
    fact_ebitda_abs = FactRecord(
        id=2, document_id=1, page=5, subject="Delhivery", predicate="adjusted EBITDA",
        value="1250", unit="crore INR", time_period="FY2024", scope="consolidated",
        evidence="Adjusted EBITDA stood at 1,250 crore INR across consolidated network operations.", fact_json="{}"
    )

    res = evaluate_fact_relationship(
        fact_a=fact_ebitda_margin,
        fact_b=fact_ebitda_abs,
        similarity=0.78
    )
    assert res.relationship == "UNRELATED"
    assert "incompatible physical/economic dimensions" in res.reasoning
    assert "Rejected CONTRADICTS" in res.why_not_explanation

def test_temporally_distinct_sequential_periods():
    """
    Ensures multi-year sequential periods (FY23 vs FY24) are classified as
    TEMPORALLY_DISTINCT, rather than falsely calling them RECONCILES.
    """
    fact_fy23 = FactRecord(
        id=1, document_id=1, page=4, subject="Delhivery", predicate="revenue from services",
        value="7225", unit="crore INR", time_period="FY2023", scope="consolidated",
        evidence="Revenue from services in FY23 was 7,225 crore INR.", fact_json="{}"
    )
    fact_fy24 = FactRecord(
        id=2, document_id=2, page=4, subject="Delhivery", predicate="revenue from services",
        value="8142", unit="crore INR", time_period="FY2024", scope="consolidated",
        evidence="Revenue from services in FY24 expanded to 8,142 crore INR.", fact_json="{}"
    )

    res = evaluate_fact_relationship(
        fact_a=fact_fy23,
        fact_b=fact_fy24,
        similarity=0.88
    )
    assert res.relationship == "TEMPORALLY_DISTINCT"
    assert "distinct time periods" in res.why_explanation.lower() or "sequential" in res.why_explanation.lower()
    assert "Rejected CONTRADICTS" in res.why_not_explanation
    assert "Rejected RECONCILES" in res.why_not_explanation



