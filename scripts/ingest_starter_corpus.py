import sys
import json
import logging
from pathlib import Path

# Fix stdout encoding for Windows console (supports ₹ and unicode characters)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database.db import DatabaseManager
from app.services.pipeline import KnowledgeLayerPipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("IngestCorpus")

def run_ingestion(clean: bool = True):
    print("=" * 70)
    print("🚀 SuperJoin Fact Knowledge Layer — Dynamic Corpus Ingestion")
    print("=" * 70)

    db = DatabaseManager()
    if clean:
        print("\n🧹 Initializing clean database...")
        db.clear_all()

    pipeline = KnowledgeLayerPipeline(db=db)
    # Use deterministic 6-stage decision pipeline for high-throughput batch ingestion
    pipeline.classifier._llm_circuit_broken = True
    print(f"🤖 Active Intelligence: Multi-Stage Decision Pipeline (with {pipeline.llm.get_active_provider_name()})")

    base_dir = Path("starter-datasets")
    delhivery_dir = base_dir / "delhivery"
    macro_dir = base_dir / "india-macroeconomy"

    starter_files = [
        delhivery_dir / "01-delhivery-prospectus-2022-excerpt.pdf",
        delhivery_dir / "02-delhivery-annual-report-fy24-excerpt.pdf",
        delhivery_dir / "03-delhivery-q4-fy24-earnings-presentation.pdf",
        macro_dir / "01-india-economic-survey-2024-25-excerpt.pdf",
        macro_dir / "02-rbi-annual-report-2024-25-excerpt.pdf",
        macro_dir / "03-imf-india-2025-article-iv-excerpt.pdf"
    ]

    for idx, pdf_path in enumerate(starter_files, 1):
        if not pdf_path.exists():
            logger.warning(f"File not found: {pdf_path}")
            continue

        print(f"\n[{idx}/6] Ingesting: {pdf_path.name}")
        result = pipeline.process_pdf(
            file_input=pdf_path,
            filename=pdf_path.name,
            max_chunks=None,  # Full document processing
            force_heuristic=True  # High-throughput batch extraction with verified source grounding
        )
        print(f"      Status: {result['status']} | Facts: {result['facts_count']} | New Relationships: {result['new_relationships']}")

    # Final Summary
    stats = db.get_stats()
    print("\n" + "=" * 70)
    print("📊 INGESTION COMPLETE — DATABASE SNAPSHOT")
    print("=" * 70)
    print(f"  • Documents Ingested : {stats['documents']}")
    print(f"  • Chunks Processed   : {stats['chunks']}")
    print(f"  • Facts Extracted    : {stats['facts']}")
    print(f"  • Cross-Doc Relations: {stats['relationships']}")

    # Dynamic 4 Cases Query
    four_cases = db.get_four_cases()
    print("\n" + "=" * 70)
    print("🔍 DYNAMIC FOUR-CASE EVALUATION QUERY")
    print("=" * 70)

    # 1. Corroboration
    print("\n[Case 1: Corroboration]")
    if four_cases["corroboration"]:
        c = four_cases["corroboration"]
        print(f"  • Doc A: {c['doc_a_filename']} (Page {c['fact_a_page']}) -> {c['fact_a_subject']} {c['fact_a_predicate']}: {c['fact_a_value']} {c['fact_a_unit']}")
        print(f"  • Doc B: {c['doc_b_filename']} (Page {c['fact_b_page']}) -> {c['fact_b_subject']} {c['fact_b_predicate']}: {c['fact_b_value']} {c['fact_b_unit']}")
        print(f"  • Confidence: {c['confidence']:.2f}")
        print(f"  • Why: {c['why_explanation']}")
        print(f"  • Why Not: {c['why_not_explanation']}")
    else:
        print("  (None found)")

    # 2. Contradiction
    print("\n[Case 2: Contradiction]")
    if four_cases["contradiction"]:
        c = four_cases["contradiction"]
        print(f"  • Doc A: {c['doc_a_filename']} (Page {c['fact_a_page']}) -> {c['fact_a_subject']} {c['fact_a_predicate']}: {c['fact_a_value']} {c['fact_a_unit']}")
        print(f"  • Doc B: {c['doc_b_filename']} (Page {c['fact_b_page']}) -> {c['fact_b_subject']} {c['fact_b_predicate']}: {c['fact_b_value']} {c['fact_b_unit']}")
        print(f"  • Confidence: {c['confidence']:.2f}")
        print(f"  • Why: {c['why_explanation']}")
        print(f"  • Why Not: {c['why_not_explanation']}")
    else:
        print("  (None found)")

    # 3. Reconciliation
    print("\n[Case 3: Context-Based Reconciliation]")
    if four_cases["reconciliation"]:
        c = four_cases["reconciliation"]
        print(f"  • Doc A: {c['doc_a_filename']} (Page {c['fact_a_page']}) -> {c['fact_a_subject']} {c['fact_a_predicate']}: {c['fact_a_value']} {c['fact_a_unit']}")
        print(f"  • Doc B: {c['doc_b_filename']} (Page {c['fact_b_page']}) -> {c['fact_b_subject']} {c['fact_b_predicate']}: {c['fact_b_value']} {c['fact_b_unit']}")
        print(f"  • Confidence: {c['confidence']:.2f}")
        print(f"  • Why: {c['why_explanation']}")
        print(f"  • Why Not: {c['why_not_explanation']}")
    else:
        print("  (None found)")

    # 4. Table Extraction Failure
    print("\n[Case 4: Real Table Extraction Failure Case Study]")
    ef = four_cases["extraction_failure"]
    print(f"  • Title: {ef['title']}")
    print(f"  • Document: {ef['document']} (Page {ef['page']})")
    print(f"  • Why Naive Extraction Fails: {ef['why_naive_extraction_fails']}")
    print(f"  • Recovery Outcome: {ef['reconciliation_outcome']}")
    print("\n" + "=" * 70)

if __name__ == "__main__":
    run_ingestion()
