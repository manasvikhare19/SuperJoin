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

def test_candidate_matcher_incremental_add_facts():
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

    # Initial build with 1 fact
    matcher.build_index([fact_a])
    assert matcher.index.ntotal == 1

    # Incrementally add a second fact from another document
    fact_b = FactRecord(
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
    added_count = matcher.add_facts([fact_b])
    assert added_count == 1
    assert matcher.index.ntotal == 2
    assert len(matcher.fact_records) == 2

    # Query cross-document candidates between fact_b and existing index
    candidates = matcher.find_cross_document_candidates(new_facts=[fact_b])
    assert len(candidates) >= 1
    matched_ids = {(c[0].id, c[1].id) for c in candidates}
    assert (1, 2) in matched_ids

def test_candidate_matcher_vector_positional_alignment_mixed_state():
    """Validates that facts with precomputed blobs and missing blobs maintain exact 1:1 index alignment."""
    embedder = FactEmbedder()
    matcher = CandidateMatcher(embedder=embedder, threshold=0.50)

    facts = [
        FactRecord(id=10, document_id=1, page=1, subject="Alpha", predicate="metric_a", value="10", unit="x", evidence="Alpha metric_a 10", fact_json="{}"),
        FactRecord(id=20, document_id=1, page=2, subject="Beta", predicate="metric_b", value="20", unit="y", evidence="Beta metric_b 20", fact_json="{}"),
        FactRecord(id=30, document_id=1, page=3, subject="Gamma", predicate="metric_c", value="30", unit="z", evidence="Gamma metric_c 30", fact_json="{}"),
        FactRecord(id=40, document_id=1, page=4, subject="Delta", predicate="metric_d", value="40", unit="w", evidence="Delta metric_d 40", fact_json="{}"),
    ]

    # Pre-embed only even-index facts (0 and 2), leaving odd-index facts (1 and 3) missing
    vec_0 = embedder.embed_facts([facts[0]])[0]
    vec_2 = embedder.embed_facts([facts[2]])[0]
    facts[0].embedding_blob = FactEmbedder.vector_to_blob(vec_0)
    facts[2].embedding_blob = FactEmbedder.vector_to_blob(vec_2)
    assert facts[1].embedding_blob is None
    assert facts[3].embedding_blob is None

    matcher.build_index(facts)
    assert matcher.index.ntotal == 4
    assert len(matcher.fact_records) == 4

    # Verify that index i in FAISS corresponds exactly to facts[i]
    for i, fact in enumerate(facts):
        assert fact.embedding_blob is not None
        vec = FactEmbedder.blob_to_vector(fact.embedding_blob).reshape(1, -1).astype(np.float32)
        import faiss
        faiss.normalize_L2(vec)
        dists, idxs = matcher.index.search(vec, 1)
        # The top-1 nearest neighbor must be position i with cosine similarity ~ 1.0
        assert idxs[0][0] == i, f"Expected FAISS index {i} for fact ID {fact.id}, got {idxs[0][0]}"
        assert dists[0][0] > 0.99

