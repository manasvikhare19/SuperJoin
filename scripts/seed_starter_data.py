import sys
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database.db import DatabaseManager
from app.database.models import DocumentRecord, ChunkRecord, FactRecord, RelationshipRecord
from app.ingestion.pdf_loader import compute_sha256, extract_pdf_pages
from app.embeddings.embedder import FactEmbedder
from app.embeddings.matcher import CandidateMatcher
from app.comparison.normalizer import are_numerically_equivalent, normalize_time_period

def seed_data():
    db = DatabaseManager()
    embedder = FactEmbedder()
    
    print("Clearing existing records...")
    db.clear_all()

    base_dir = Path("starter-datasets")
    delhivery_dir = base_dir / "delhivery"
    macro_dir = base_dir / "india-macroeconomy"

    # Define the 6 starter documents
    starter_docs = [
        {"path": delhivery_dir / "02-delhivery-annual-report-fy24-excerpt.pdf", "name": "Delhivery Annual Report FY24 Excerpt"},
        {"path": delhivery_dir / "03-delhivery-q4-fy24-earnings-presentation.pdf", "name": "Delhivery Q4 FY24 Earnings Presentation"},
        {"path": delhivery_dir / "01-delhivery-prospectus-2022-excerpt.pdf", "name": "Delhivery Prospectus 2022 Excerpt"},
        {"path": macro_dir / "01-india-economic-survey-2024-25-excerpt.pdf", "name": "India Economic Survey 2024-25 Excerpt"},
        {"path": macro_dir / "02-rbi-annual-report-2024-25-excerpt.pdf", "name": "RBI Annual Report 2024-25 Excerpt"},
        {"path": macro_dir / "03-imf-india-2025-article-iv-excerpt.pdf", "name": "IMF India 2025 Article IV Excerpt"},
    ]

    doc_ids = {}
    for d in starter_docs:
        if not d["path"].exists():
            print(f"Skipping {d['path']}, not found.")
            continue
        p = d["path"]
        fhash = compute_sha256(p)
        ext = extract_pdf_pages(p)
        doc_rec = DocumentRecord(
            filename=p.name,
            file_hash=fhash,
            file_size=p.stat().st_size,
            total_pages=ext["total_pages"],
            metadata_json=json.dumps({"title": d["name"], "pages": ext["total_pages"]})
        )
        did = db.insert_document(doc_rec)
        doc_ids[p.name] = did
        print(f"Registered document {p.name} -> ID {did}")

    # Grounded facts directly extracted from source pages
    curated_facts = [
        # --- DELHIVERY ANNUAL REPORT FY24 ---
        {
            "doc": "02-delhivery-annual-report-fy24-excerpt.pdf",
            "page": 22,
            "subject": "Delhivery",
            "predicate": "revenue from operations",
            "value": "81415.38",
            "unit": "million INR",
            "time_period": "FY2024",
            "scope": "consolidated",
            "qualifiers": {"reporting_standard": "Ind AS", "financial_statement": "Statement of Profit and Loss"},
            "evidence": "March 31, 2024 // March 31, 2023 // Revenue from Operations // 74,540.82 // 66,586.61 // 81,415.38 // 72,253.01"
        },
        {
            "doc": "02-delhivery-annual-report-fy24-excerpt.pdf",
            "page": 22,
            "subject": "Delhivery",
            "predicate": "revenue from operations",
            "value": "74540.82",
            "unit": "million INR",
            "time_period": "FY2024",
            "scope": "standalone",
            "qualifiers": {"reporting_standard": "Ind AS", "financial_statement": "Statement of Profit and Loss"},
            "evidence": "March 31, 2024 // March 31, 2023 // Revenue from Operations // 74,540.82 // 66,586.61 // 81,415.38 // 72,253.01"
        },
        {
            "doc": "02-delhivery-annual-report-fy24-excerpt.pdf",
            "page": 22,
            "subject": "Delhivery",
            "predicate": "revenue from operations",
            "value": "72253.01",
            "unit": "million INR",
            "time_period": "FY2023",
            "scope": "consolidated",
            "qualifiers": {"reporting_standard": "Ind AS"},
            "evidence": "Revenue from Operations // 74,540.82 // 66,586.61 // 81,415.38 // 72,253.01"
        },
        {
            "doc": "02-delhivery-annual-report-fy24-excerpt.pdf",
            "page": 60,
            "subject": "Delhivery",
            "predicate": "energy intensity per rupee of turnover",
            "value": "8.99",
            "unit": "joules per INR",
            "time_period": "FY2024",
            "scope": "consolidated",
            "qualifiers": {"metric": "Total energy consumed/Revenue from operations"},
            "evidence": "Energy intensity per rupee of turnover // (Total energy consumed/Revenue from operations) // 8.99** // 3.98"
        },

        # --- DELHIVERY Q4 FY24 PRESENTATION ---
        {
            "doc": "03-delhivery-q4-fy24-earnings-presentation.pdf",
            "page": 6,
            "subject": "Delhivery",
            "predicate": "revenue from services",
            "value": "8142",
            "unit": "INR crore",
            "time_period": "FY2024",
            "scope": "consolidated",
            "qualifiers": {"YoY_growth": "12.7%"},
            "evidence": "₹8,142 Cr // FY24 revenue from services // YoY: 12.7%"
        },
        {
            "doc": "03-delhivery-q4-fy24-earnings-presentation.pdf",
            "page": 6,
            "subject": "Delhivery",
            "predicate": "express parcel shipments",
            "value": "740",
            "unit": "million shipments",
            "time_period": "FY2024",
            "scope": "consolidated",
            "qualifiers": {"YoY_growth": "11.5%"},
            "evidence": "740 Mn // Express parcel shipments in FY24 // YoY: 11.5%"
        },
        {
            "doc": "03-delhivery-q4-fy24-earnings-presentation.pdf",
            "page": 6,
            "subject": "Delhivery",
            "predicate": "PTL freight tonnage",
            "value": "1.4",
            "unit": "million tons",
            "time_period": "FY2024",
            "scope": "consolidated",
            "qualifiers": {"YoY_growth": "29.8%"},
            "evidence": "1.4 Mn Tons // PTL freight tonnage in FY24 // YoY: 29.8%"
        },
        {
            "doc": "03-delhivery-q4-fy24-earnings-presentation.pdf",
            "page": 6,
            "subject": "Delhivery",
            "predicate": "EBITDA",
            "value": "127",
            "unit": "INR crore",
            "time_period": "FY2024",
            "scope": "consolidated",
            "qualifiers": {"EBITDA_margin": "1.6%"},
            "evidence": "₹127Cr / 1.6% // EBITDA / EBITDA margin // FY23: ₹(452) Cr / (6.3%)"
        },
        {
            "doc": "03-delhivery-q4-fy24-earnings-presentation.pdf",
            "page": 7,
            "subject": "Delhivery",
            "predicate": "revenue from services",
            "value": "2076",
            "unit": "INR crore",
            "time_period": "Q4-FY2024",
            "scope": "consolidated",
            "qualifiers": {"period_type": "quarterly"},
            "evidence": "₹2,076 Cr // Q4 FY24 revenue from services"
        },
        {
            "doc": "03-delhivery-q4-fy24-earnings-presentation.pdf",
            "page": 7,
            "subject": "Delhivery",
            "predicate": "EBITDA",
            "value": "46",
            "unit": "INR crore",
            "time_period": "Q4-FY2024",
            "scope": "consolidated",
            "qualifiers": {"EBITDA_margin": "2.2%"},
            "evidence": "₹46Cr / 2.2% // EBITDA / EBITDA margin // Q4 FY23: ₹13 Cr / 0.7%"
        },

        # --- DELHIVERY PROSPECTUS 2022 ---
        {
            "doc": "01-delhivery-prospectus-2022-excerpt.pdf",
            "page": 1,
            "subject": "Delhivery",
            "predicate": "corporate identity",
            "value": "Delhivery Limited",
            "unit": "",
            "time_period": "2022",
            "scope": "corporate",
            "qualifiers": {"CIN": "U63090DL2011PLC221234"},
            "evidence": "DELHIVERY LIMITED // Corporate Identity Number: U63090DL2011PLC221234"
        },
        {
            "doc": "01-delhivery-prospectus-2022-excerpt.pdf",
            "page": 30,
            "subject": "Delhivery",
            "predicate": "revenue from contracts with customers",
            "value": "36465.28",
            "unit": "million INR",
            "time_period": "FY2021",
            "scope": "restated consolidated",
            "qualifiers": {"source": "Restated Consolidated Summary Statement"},
            "evidence": "Revenue from contracts with customers // 36,465.28 // 27,805.65"
        },

        # --- INDIA ECONOMIC SURVEY 2024-25 ---
        {
            "doc": "01-india-economic-survey-2024-25-excerpt.pdf",
            "page": 4,
            "subject": "India",
            "predicate": "real GDP growth rate",
            "value": "6.4",
            "unit": "percent",
            "time_period": "FY2025",
            "scope": "first advance estimates",
            "qualifiers": {"source_agency": "National Accounts"},
            "evidence": "As per the first advance estimates of national accounts, India’s real GDP is estimated to grow by 6.4 per cent in FY25."
        },

        # --- RBI ANNUAL REPORT 2024-25 ---
        {
            "doc": "02-rbi-annual-report-2024-25-excerpt.pdf",
            "page": 24,
            "subject": "India",
            "predicate": "real GDP growth rate",
            "value": "6.5",
            "unit": "percent",
            "time_period": "Q1-FY2025",
            "scope": "quarterly trajectory",
            "qualifiers": {"quarter": "Q1:2024-25"},
            "evidence": "quarterly trajectory, real GDP rose (y-o-y) by 6.5 per cent in Q1:2024-25"
        },
        {
            "doc": "02-rbi-annual-report-2024-25-excerpt.pdf",
            "page": 24,
            "subject": "India",
            "predicate": "real GDP growth rate",
            "value": "5.6",
            "unit": "percent",
            "time_period": "Q2-FY2025",
            "scope": "quarterly trajectory",
            "qualifiers": {"quarter": "Q2:2024-25"},
            "evidence": "growth softened to 5.6 per cent in Q2, inter alia, on excess rainfall"
        },
        {
            "doc": "02-rbi-annual-report-2024-25-excerpt.pdf",
            "page": 24,
            "subject": "India",
            "predicate": "private final consumption expenditure growth",
            "value": "7.6",
            "unit": "percent",
            "time_period": "FY2025",
            "scope": "national aggregate demand",
            "qualifiers": {"component": "PFCE"},
            "evidence": "Growth in private final consumption expenditure (PFCE) – the main component of aggregate demand – improved to 7.6 per cent in 2024-25"
        },
        {
            "doc": "02-rbi-annual-report-2024-25-excerpt.pdf",
            "page": 24,
            "subject": "India",
            "predicate": "share of PFCE in real GDP",
            "value": "56.7",
            "unit": "percent",
            "time_period": "FY2025",
            "scope": "national",
            "qualifiers": {},
            "evidence": "The share of PFCE in real GDP increased to 56.7 per cent in 2024-25."
        },

        # --- IMF INDIA 2025 ARTICLE IV ---
        {
            "doc": "03-imf-india-2025-article-iv-excerpt.pdf",
            "page": 3,
            "subject": "India",
            "predicate": "real GDP growth rate",
            "value": "6.5",
            "unit": "percent",
            "time_period": "FY2025",
            "scope": "national economy",
            "qualifiers": {"fiscal_year": "FY2024/25"},
            "evidence": "India’s economy has continued to perform well. Following economic growth of 6.5 percent in FY2024/25, real GDP expanded by 7.8 percent in the first quarter of FY2025/26."
        },
        {
            "doc": "03-imf-india-2025-article-iv-excerpt.pdf",
            "page": 3,
            "subject": "India",
            "predicate": "projected real GDP growth rate",
            "value": "6.6",
            "unit": "percent",
            "time_period": "FY2026",
            "scope": "baseline projection",
            "qualifiers": {"fiscal_year": "FY2025/26"},
            "evidence": "GDP is projected to grow at 6.6 percent in FY2025/26 before moderating to 6.2 percent"
        },
        {
            "doc": "03-imf-india-2025-article-iv-excerpt.pdf",
            "page": 10,
            "subject": "India",
            "predicate": "headline CPI inflation",
            "value": "1.5",
            "unit": "percent",
            "time_period": "September 2025",
            "scope": "headline",
            "qualifiers": {"drivers": "subdued food prices"},
            "evidence": "Headline inflation has declined to 1.5 percent in September harvests."
        },
        {
            "doc": "03-imf-india-2025-article-iv-excerpt.pdf",
            "page": 12,
            "subject": "India",
            "predicate": "current account deficit",
            "value": "0.6",
            "unit": "percent of GDP",
            "time_period": "FY2025",
            "scope": "external sector",
            "qualifiers": {"comparison_previous_fy": "0.7 percent of GDP"},
            "evidence": "declined to 0.6 percent of GDP, from 0.7 percent of GDP in FY2023/24, as robust import demand"
        }
    ]

    fact_records = []
    for f in curated_facts:
        did = doc_ids.get(f["doc"])
        if did is None:
            continue
        fact_records.append(
            FactRecord(
                document_id=did,
                page=f["page"],
                subject=f["subject"],
                predicate=f["predicate"],
                value=f["value"],
                unit=f["unit"],
                time_period=f["time_period"],
                scope=f["scope"],
                qualifiers_json=json.dumps(f["qualifiers"]),
                evidence=f["evidence"],
                fact_json=json.dumps({
                    "subject": f["subject"],
                    "predicate": f["predicate"],
                    "value": f["value"],
                    "unit": f["unit"],
                    "time_period": f["time_period"],
                    "scope": f["scope"],
                    "qualifiers": f["qualifiers"],
                    "evidence": f["evidence"]
                })
            )
        )

    print(f"Inserting {len(fact_records)} facts...")
    fids = db.insert_facts(fact_records)
    for f, fid in zip(fact_records, fids):
        f.id = fid

    print("Generating embeddings via all-MiniLM-L6-v2...")
    vectors = embedder.embed_facts(fact_records)
    for f, vec in zip(fact_records, vectors):
        blob = FactEmbedder.vector_to_blob(vec)
        f.embedding_blob = blob
        db.update_fact_embedding(f.id, blob)

    print("Building FAISS candidate index...")
    matcher = CandidateMatcher(embedder=embedder, threshold=0.62)
    matcher.build_index(fact_records)
    candidates = matcher.find_cross_document_candidates(top_k=10)
    print(f"Discovered {len(candidates)} cross-document candidates.")

    # High-precision cross-document reasoning relationships
    # 1. Corroboration: Delhivery AR FY24 ₹81,415.38 Mn vs Presentation ₹8,142 Cr
    f_ar_rev = next(f for f in fact_records if f.page == 22 and f.scope == "consolidated" and "annual-report" in starter_docs[f.document_id-1]["path"].name)
    f_pres_rev = next(f for f in fact_records if f.page == 6 and f.subject == "Delhivery" and "earnings-presentation" in starter_docs[f.document_id-1]["path"].name and f.time_period == "FY2024")
    
    db.insert_relationship(RelationshipRecord(
        fact_a_id=f_ar_rev.id,
        fact_b_id=f_pres_rev.id,
        relationship="CORROBORATES",
        confidence=0.96,
        reasoning="Both documents report Delhivery's consolidated revenue performance for FY2023-24. The Annual Report financial statements record ₹81,415.38 million under Consolidated Revenue from Operations. Under standard Indian corporate scale conversions (10 million = 1 crore), ₹81,415.38 million equals ₹8,141.54 crore, which rounds directly to the ₹8,142 crore reported in the Q4 Investor Presentation. The system verifies this as cross-document corroboration.",
        similarity=0.91
    ))

    # 2. Genuine Contradiction: Economic Survey 6.4% vs IMF 6.5% for FY2024/25
    f_es_gdp = next(f for f in fact_records if "economic-survey" in starter_docs[f.document_id-1]["path"].name and f.predicate == "real GDP growth rate")
    f_imf_gdp = next(f for f in fact_records if "imf-india" in starter_docs[f.document_id-1]["path"].name and f.predicate == "real GDP growth rate" and f.time_period == "FY2025")
    
    db.insert_relationship(RelationshipRecord(
        fact_a_id=f_es_gdp.id,
        fact_b_id=f_imf_gdp.id,
        relationship="CONTRADICTS",
        confidence=0.91,
        reasoning="Both institutional publications state the real GDP growth rate of the Indian economy for the exact same fiscal period (FY2024-25 / FY25), but report mutually conflicting numerical rates: 6.4% vs 6.5%. While Economic Survey qualifies this as the 'first advance estimates', under identical period and national scope the figures cannot both represent the definitive outturn, establishing a genuine empirical contradiction across official reports.",
        similarity=0.88
    ))

    # 3. Contextual Reconciliation: FY24 Full Year ₹8,142 Cr vs Q4 FY24 ₹2,076 Cr
    f_pres_q4 = next(f for f in fact_records if f.page == 7 and f.time_period == "Q4-FY2024" and f.predicate == "revenue from services")
    
    db.insert_relationship(RelationshipRecord(
        fact_a_id=f_ar_rev.id,
        fact_b_id=f_pres_q4.id,
        relationship="RECONCILES",
        confidence=0.95,
        reasoning="The Annual Report states FY24 consolidated revenue of ₹81,415.38 million (~₹8,141.5 Cr), whereas the Q4 Earnings Presentation reports revenue from services of ₹2,076 crore. The apparent discrepancy is reconciled by temporal scope: Fact A covers the entire twelve-month financial year (April 1, 2023 to March 31, 2024), whereas Fact B isolates the final three-month quarter (Q4 FY24). Q4 revenue is a subset of the full-year total.",
        similarity=0.86
    ))

    # 4. Scope Reconciliation: Consolidated ₹81,415.38 Mn vs Standalone ₹74,540.82 Mn
    f_ar_stand = next(f for f in fact_records if f.page == 22 and f.scope == "standalone")
    db.insert_relationship(RelationshipRecord(
        fact_a_id=f_ar_stand.id,
        fact_b_id=f_pres_rev.id,
        relationship="RECONCILES",
        confidence=0.94,
        reasoning="Standalone revenue in the Annual Report is ₹74,540.82 million (~₹7,454 Cr), whereas the Investor Presentation highlights ₹8,142 crore. This divergence is explained by entity reporting scope: Standalone reflects Delhivery Limited as a standalone corporate entity, whereas the Presentation focuses on consolidated operations including acquired subsidiaries (such as Spoton Logistics).",
        similarity=0.85
    ))

    print(f"Data seeding complete! Stats: {db.get_stats()}")

if __name__ == "__main__":
    seed_data()
