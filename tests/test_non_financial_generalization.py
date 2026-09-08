import pytest
from pathlib import Path
from app.ingestion.pdf_loader import extract_pdf_pages
from app.ingestion.chunker import chunk_pdf_pages
from app.extraction.fact_extractor import FactExtractor
from app.comparison.normalizer import classify_unit_dimension, are_units_dimensionally_compatible
from app.comparison.decision_pipeline import evaluate_fact_relationship, check_predicate_compatibility
from app.database.models import FactRecord

CLIMATE_DIR = Path("starter-datasets/generalization")

@pytest.fixture(scope="module")
def climate_facts():
    doc1_path = CLIMATE_DIR / "01-climate-change-indicators-summary.pdf"
    doc2_path = CLIMATE_DIR / "02-wmo-global-climate-report.pdf"

    p1 = extract_pdf_pages(doc1_path)
    c1 = chunk_pdf_pages(p1["pages"], document_id=101)
    extractor = FactExtractor()
    facts1 = extractor.fallback_heuristic_extraction(c1[0], {1: p1["pages"][0]["text"]})

    p2 = extract_pdf_pages(doc2_path)
    c2 = chunk_pdf_pages(p2["pages"], document_id=102)
    facts2 = extractor.fallback_heuristic_extraction(c2[0], {1: p2["pages"][0]["text"]})

    return {"doc1": facts1, "doc2": facts2}

def test_scientific_unit_dimensions():
    """Verify that scientific units are categorized into correct physical dimensions."""
    assert classify_unit_dimension("ppm") == "CONCENTRATION"
    assert classify_unit_dimension("ppb") == "CONCENTRATION"
    assert classify_unit_dimension("°C") == "TEMPERATURE"
    assert classify_unit_dimension("celsius") == "TEMPERATURE"
    assert classify_unit_dimension("GW") == "ENERGY_POWER"
    assert classify_unit_dimension("million sq km") == "AREA"

    # Incompatible dimensions
    assert are_units_dimensionally_compatible("ppm", "°C") is False
    assert are_units_dimensionally_compatible("ppm", "GW") is False
    assert are_units_dimensionally_compatible("°C", "million sq km") is False

    # Compatible dimensions
    assert are_units_dimensionally_compatible("ppm", "ppb") is True
    assert are_units_dimensionally_compatible("°C", "celsius") is True

def test_climate_fact_extraction(climate_facts):
    """Verify that facts from non-financial scientific reports are accurately extracted and grounded."""
    facts1 = climate_facts["doc1"]
    facts2 = climate_facts["doc2"]

    assert len(facts1) >= 4
    assert len(facts2) >= 4

    # Check for CO2 concentration
    co2_f1 = [f for f in facts1 if "421.5" in f.value and "ppm" in f.unit.lower()]
    assert len(co2_f1) >= 1
    assert co2_f1[0].evidence_status in ("EXACT_MATCH", "NORMALIZED_MATCH")
    assert "421.5 ppm" in co2_f1[0].evidence

    # Check for temperature anomaly
    temp_f1 = [f for f in facts1 if "1.45" in f.value]
    assert len(temp_f1) >= 1
    assert temp_f1[0].evidence_status in ("EXACT_MATCH", "NORMALIZED_MATCH")

    # Check for renewable power capacity
    gw_f1 = [f for f in facts1 if "510" in f.value and "gw" in f.unit.lower()]
    assert len(gw_f1) >= 1
    assert gw_f1[0].evidence_status in ("EXACT_MATCH", "NORMALIZED_MATCH")

def test_cross_document_climate_corroboration(climate_facts):
    """Verify that identical physical measurements across distinct institutions corroborate."""
    facts1 = climate_facts["doc1"]
    facts2 = climate_facts["doc2"]

    co2_1 = next(f for f in facts1 if "421.5" in f.value and f.time_period == "2023")
    co2_2 = next(f for f in facts2 if "421.5" in f.value and f.time_period == "2023")

    result = evaluate_fact_relationship(co2_1, co2_2, similarity=0.88)
    assert result.relationship == "CORROBORATES"
    assert result.confidence >= 0.75
    assert "concordant" in result.why_explanation.lower() or "matches" in result.why_explanation.lower()

def test_climate_temporal_distinction(climate_facts):
    """Verify that consecutive yearly measurements (2022 vs 2023) are classified as TEMPORALLY_DISTINCT."""
    facts1 = climate_facts["doc1"]
    facts2 = climate_facts["doc2"]

    co2_2023 = next(f for f in facts1 if "421.5" in f.value and f.time_period == "2023")
    co2_2022 = next(f for f in facts2 if "418.7" in f.value and f.time_period == "2022")

    result = evaluate_fact_relationship(co2_2023, co2_2022, similarity=0.85)
    assert result.relationship == "TEMPORALLY_DISTINCT"
    assert "distinct time periods" in result.reasoning.lower() or "sequential" in result.reasoning.lower()

def test_physical_unit_guardrail_rejection(climate_facts):
    """Verify that comparing facts with incompatible physical dimensions is rejected as UNRELATED."""
    facts1 = climate_facts["doc1"]

    co2_fact = next(f for f in facts1 if "421.5" in f.value and "ppm" in f.unit.lower())
    gw_fact = next(f for f in facts1 if "510" in f.value and "gw" in f.unit.lower())

    result = evaluate_fact_relationship(co2_fact, gw_fact, similarity=0.80)
    assert result.relationship == "UNRELATED"
    assert "incompatible physical" in result.reasoning.lower()
