import pytest
import numpy as np
from app.database.models import FactRecord
from app.embeddings.embedder import FactEmbedder
from app.embeddings.matcher import CandidateMatcher

def test_embedder_format_fact_text():
    fact = FactRecord(
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
    text = FactEmbedder.format_fact_text(fact)
    assert "Delhivery" in text
    assert "revenue from services" in text
    assert "8142 INR crore" in text
    assert "FY2024" in text
    assert "consolidated" in text

def test_candidate_matcher_cross_document():
    embedder = FactEmbedder()
    matcher = CandidateMatcher(embedder=embedder, threshold=0.60)

    fact_a = FactRecord(
        id=1,
        document_id=1,
        page=22,
        subject="Delhivery",
        predicate="revenue from operations",
        value="81415.38",
        unit="million",
        time_period="FY2024",
        scope="consolidated",
        evidence="Revenue from Operations ... 81,415.38",
        fact_json="{}"
    )

    fact_b = FactRecord(
        id=2,
        document_id=2,  # Different document!
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

    fact_c = FactRecord(
        id=3,
        document_id=1,  # Same document as fact_a
        page=10,
        subject="Delhivery",
        predicate="headcount",
        value="57000",
        unit="employees",
        time_period="FY2024",
        scope="consolidated",
        evidence="Total active employees stood at 57,000",
        fact_json="{}"
    )

    matcher.build_index([fact_a, fact_b, fact_c])
    candidates = matcher.find_cross_document_candidates()

    assert len(candidates) >= 1
    # Candidate should match fact_a and fact_b across different documents
    matched_ids = {(c[0].id, c[1].id) for c in candidates}
    assert (1, 2) in matched_ids
    # Same document pairs (1, 3) must never be matched
    assert (1, 3) not in matched_ids
