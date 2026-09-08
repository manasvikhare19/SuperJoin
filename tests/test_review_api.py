import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from app.database.db import DatabaseManager
from app.database.models import DocumentRecord, FactRecord, RelationshipRecord
from app.main import app

def test_human_review_persistence_and_api(tmp_path: Path):
    test_db_path = tmp_path / "test_review.db"
    db = DatabaseManager(db_path=test_db_path)

    # 1. Setup sample document and facts
    doc_id_a = db.insert_document(DocumentRecord(filename="doc_a.pdf", file_hash="hash_a"))
    doc_id_b = db.insert_document(DocumentRecord(filename="doc_b.pdf", file_hash="hash_b"))

    fact_ids = db.insert_facts([
        FactRecord(
            document_id=doc_id_a,
            page=1,
            subject="Acme Corp",
            predicate="revenue",
            value="100",
            unit="crore",
            evidence="Revenue was 100 crore",
            fact_json="{}"
        ),
        FactRecord(
            document_id=doc_id_b,
            page=1,
            subject="Acme Corp",
            predicate="revenue",
            value="100",
            unit="crore",
            evidence="Revenue was 100 crore",
            fact_json="{}"
        )
    ])

    rel_id = db.insert_relationship(RelationshipRecord(
        fact_a_id=fact_ids[0],
        fact_b_id=fact_ids[1],
        relationship="CORROBORATES",
        confidence=0.98,
        reasoning="Both report 100 crore revenue",
        why_explanation="Corroborated across documents",
        why_not_explanation="No discrepancy",
        similarity=0.95
    ))

    # 2. Test initial state
    rels = db.list_relationships()
    assert len(rels) == 1
    assert rels[0]["relationship_id"] == rel_id
    assert rels[0]["human_review_status"] is None

    # 3. Test db.update_relationship_review directly
    updated = db.update_relationship_review(rel_id=rel_id, status="ACCEPTED", notes="Audited by QA")
    assert updated is not None
    assert updated["human_review_status"] == "ACCEPTED"
    assert updated["reviewer_notes"] == "Audited by QA"
    assert updated["reviewed_at"] is not None

    # 4. Test list_relationships reflects updated review
    rels_after = db.list_relationships()
    assert rels_after[0]["human_review_status"] == "ACCEPTED"
    assert rels_after[0]["reviewer_notes"] == "Audited by QA"

    # 5. Test API endpoint with app
    from app import main
    original_db = main.db
    main.db = db
    try:
        client = TestClient(app)

        # Test REJECTED via API
        res = client.post(f"/api/relationships/{rel_id}/review", json={
            "status": "REJECTED",
            "notes": "Flagged as false positive"
        })
        assert res.status_code == 200
        data = res.json()
        assert data["human_review_status"] == "REJECTED"
        assert data["reviewer_notes"] == "Flagged as false positive"

        # Verify DB updated
        check_db = db.list_relationships()
        assert check_db[0]["human_review_status"] == "REJECTED"

        # Test RESET via API
        res_reset = client.post(f"/api/relationships/{rel_id}/review", json={
            "status": "RESET"
        })
        assert res_reset.status_code == 200
        assert res_reset.json()["human_review_status"] is None
        check_reset = db.list_relationships()
        assert check_reset[0]["human_review_status"] is None

        # Test Invalid Status
        res_invalid = client.post(f"/api/relationships/{rel_id}/review", json={
            "status": "INVALID_STATUS"
        })
        assert res_invalid.status_code == 400

        # Test 404 for non-existent relationship
        res_404 = client.post("/api/relationships/99999/review", json={
            "status": "ACCEPTED"
        })
        assert res_404.status_code == 404
    finally:
        main.db = original_db

def test_four_cases_clean_and_guardrail_discovery(tmp_path: Path):
    test_db_path = tmp_path / "test_four_cases.db"
    db = DatabaseManager(db_path=test_db_path)

    # Clean DB: returns NO_GUARDRAIL_INTERCEPTION_DETECTED without hardcoded fallback
    four_cases_clean = db.get_four_cases()
    failure_case = four_cases_clean["extraction_failure"]
    assert failure_case["status"] == "NO_GUARDRAIL_INTERCEPTION_DETECTED"
    assert failure_case["is_dynamically_discovered"] is False
    assert "No extraction failure or guardrail interception detected" in failure_case["message"]
    # Ensure no fabricated Delhivery p.138 data is returned
    assert "01-delhivery" not in str(failure_case)

    # Insert a real guardrail interception relationship
    doc_a = db.insert_document(DocumentRecord(filename="esg_report.pdf", file_hash="esg_1"))
    doc_b = db.insert_document(DocumentRecord(filename="presentation.pdf", file_hash="pres_1"))
    fact_ids = db.insert_facts([
        FactRecord(
            document_id=doc_a,
            page=42,
            subject="GreenEnergy",
            predicate="emissions",
            value="1500",
            unit="tCO2e",
            evidence="Scope 1 emissions were 1500 tCO2e",
            fact_json="{}"
        ),
        FactRecord(
            document_id=doc_b,
            page=5,
            subject="GreenEnergy",
            predicate="emissions",
            value="25",
            unit="%",
            evidence="Emissions reduction was 25%",
            fact_json="{}"
        )
    ])

    db.insert_relationship(RelationshipRecord(
        fact_a_id=fact_ids[0],
        fact_b_id=fact_ids[1],
        relationship="UNRELATED",
        confidence=0.92,
        reasoning="Dimensional unit check intercepted mismatch",
        why_explanation="Dimensional Guardrail Interception: Incompatible physical dimensions (mass vs percentage) prevent false contradiction.",
        why_not_explanation="Cannot reconcile incompatible units",
        similarity=0.88
    ))

    # Test dynamic discovery of guardrail case
    four_cases_guarded = db.get_four_cases()
    failure_guarded = four_cases_guarded["extraction_failure"]
    assert failure_guarded["status"] == "GUARDRAIL_INTERCEPTION_DETECTED"
    assert failure_guarded["is_dynamically_discovered"] is True
    assert failure_guarded["document"] == "esg_report.pdf"
    assert failure_guarded["page"] == 42
    assert "guardrail_recovery" in failure_guarded
    assert failure_guarded["guardrail_recovery"]["status"] == "RESOLVED_VIA_GUARDRAIL_PIPELINE"
