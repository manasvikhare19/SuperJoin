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
