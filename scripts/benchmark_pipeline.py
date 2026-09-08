import sys
import time
from pathlib import Path
from typing import List, Dict, Any

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

import numpy as np
from app.ingestion.pdf_loader import extract_pdf_pages
from app.ingestion.chunker import chunk_pdf_pages
from app.embeddings.embedder import FactEmbedder
from app.embeddings.matcher import CandidateMatcher
from app.comparison.decision_pipeline import evaluate_fact_relationship
from app.database.models import FactRecord, ChunkRecord

def run_benchmarks():
    print("=" * 75)
    print("⚡ SuperJoin Empirical Pipeline Performance Benchmark")
    print("   Measuring PyMuPDF, Chunker, MiniLM Embedder, FAISS Pruning & Reasoning")
    print("=" * 75)

    base_dir = Path("starter-datasets")
    pdf_paths = list(base_dir.rglob("*.pdf"))

    if not pdf_paths:
        print("❌ No PDFs found in starter-datasets/")
        return

    # -------------------------------------------------------------
    # 1. Benchmark PDF Parsing (PyMuPDF)
    # -------------------------------------------------------------
    print("\n[Stage 1/5] Benchmarking PyMuPDF Document Extraction...")
    total_pages = 0
    total_chars = 0
    doc_results = []

    t_parse_start = time.perf_counter()
    extracted_docs = []

    for p in pdf_paths:
        t0 = time.perf_counter()
        extracted = extract_pdf_pages(str(p))
        t1 = time.perf_counter()

        elapsed = (t1 - t0) * 1000.0  # ms
        p_count = extracted["total_pages"]
        chars = sum(p_info["char_count"] for p_info in extracted["pages"])

        total_pages += p_count
        total_chars += chars
        extracted_docs.append((p.name, extracted["pages"]))

        doc_results.append({
            "filename": p.name,
            "pages": p_count,
            "chars": chars,
            "elapsed_ms": elapsed,
            "ms_per_page": elapsed / p_count if p_count else 0
        })

    t_parse_total = (time.perf_counter() - t_parse_start) * 1000.0

    print(f"  • Ingested {len(pdf_paths)} documents ({total_pages} total pages, {total_chars:,} characters)")
    print(f"  • Total parsing time: {t_parse_total:.2f} ms")
    print(f"  • Average per page  : {t_parse_total / total_pages:.2f} ms/page ({total_pages / (t_parse_total / 1000.0):.1f} pages/sec)")

    # -------------------------------------------------------------
    # 2. Benchmark Semantic Chunking
    # -------------------------------------------------------------
    print("\n[Stage 2/5] Benchmarking Semantic Chunking...")
    t_chunk_start = time.perf_counter()
    all_chunks = []

    for doc_id, (name, pages) in enumerate(extracted_docs, start=1):
        chunks = chunk_pdf_pages(pages, document_id=doc_id)
        all_chunks.extend(chunks)

    t_chunk_total = (time.perf_counter() - t_chunk_start) * 1000.0
    print(f"  • Generated {len(all_chunks)} semantic chunks")
    print(f"  • Total chunking time: {t_chunk_total:.2f} ms ({t_chunk_total / len(all_chunks):.2f} ms/chunk)")

    # -------------------------------------------------------------
    # 3. Benchmark MiniLM Vector Embeddings
    # -------------------------------------------------------------
    print("\n[Stage 3/5] Benchmarking SentenceTransformer Embeddings (all-MiniLM-L6-v2)...")
    embedder = FactEmbedder()
    sample_texts = [
        f"Delhivery | revenue from operations | {80000 + i * 100} million INR | FY2024 | consolidated"
        for i in range(100)
    ]

    # Warmup
    _ = embedder.embed_texts(sample_texts[:5])

    t_embed_start = time.perf_counter()
    embeddings = embedder.embed_texts(sample_texts)
    t_embed_total = (time.perf_counter() - t_embed_start) * 1000.0

    print(f"  • Vector Dimension : {embeddings.shape[1]}-d (L2 normalized)")
    print(f"  • Embedded         : {len(sample_texts)} structured facts")
    print(f"  • Total time       : {t_embed_total:.2f} ms")
    print(f"  • Throughput       : {len(sample_texts) / (t_embed_total / 1000.0):.1f} facts/sec ({t_embed_total / len(sample_texts):.2f} ms/fact)")

    # -------------------------------------------------------------
    # 4. Benchmark FAISS Candidate Pruning Ratio
    # -------------------------------------------------------------
    print("\n[Stage 4/5] Benchmarking FAISS Candidate Pruning Efficiency...")
    topics = ["revenue from services", "real GDP growth rate", "EBITDA margin", "PTL freight tonnage", "CPI inflation"]
    entities = ["Delhivery", "India", "RBI", "Bluedart", "DTDC"]
    simulated_facts = []

    for i in range(250):
        ent = entities[i % len(entities)]
        top = topics[i % len(topics)]
        val = str(round(10 + (i * 1.7), 2))
        simulated_facts.append(
            FactRecord(
                id=i + 1,
                document_id=(i % 6) + 1,
                chunk_id=i + 1,
                page=(i % 30) + 1,
                subject=ent,
                predicate=top,
                value=val,
                unit="INR crore" if "revenue" in top else ("percent" if "growth" in top or "margin" in top or "inflation" in top else "tons"),
                time_period="FY2024",
                scope="consolidated",
                evidence=f"{ent} reported {top} of {val} for FY2024.",
                fact_json="{}"
            )
        )

    # Populate FAISS CandidateMatcher
    matcher = CandidateMatcher(embedder=embedder, threshold=0.35)
    matcher.build_index(simulated_facts)

    n_facts = len(simulated_facts)
    brute_force_pairs = (n_facts * (n_facts - 1)) // 2

    # Measure FAISS candidate retrieval latency across cross-document facts (top-k = 10)
    t_faiss_start = time.perf_counter()
    candidates = matcher.find_cross_document_candidates(top_k=10)
    t_faiss_total = (time.perf_counter() - t_faiss_start) * 1000.0

    retained_pairs = len(candidates)
    pruning_ratio = (1.0 - (retained_pairs / brute_force_pairs)) * 100.0

    print(f"  • Corpus Facts           : {n_facts}")
    print(f"  • Brute-Force All-Pairs  : {brute_force_pairs:,} comparisons")
    print(f"  • FAISS Top-10 Candidates: {retained_pairs:,} candidate pairs")
    print(f"  • Pruning Ratio          : {pruning_ratio:.2f}% candidate reduction")
    print(f"  • Index Search Latency   : {t_faiss_total:.2f} ms ({t_faiss_total / n_facts:.3f} ms/query)")

    # -------------------------------------------------------------
    # 5. Benchmark 6-Stage Reasoning Decision Pipeline
    # -------------------------------------------------------------
    print("\n[Stage 5/5] Benchmarking 6-Stage Analytical Decision Pipeline...")
    t_eval_start = time.perf_counter()
    sample_pairs = candidates[:100]

    eval_results = []
    for fa, fb, sim in sample_pairs:
        res = evaluate_fact_relationship(fa, fb, similarity=sim, embedder=embedder)
        eval_results.append(res)

    t_eval_total = (time.perf_counter() - t_eval_start) * 1000.0

    print(f"  • Evaluated Pairs        : {len(sample_pairs)}")
    print(f"  • Total Pipeline Time    : {t_eval_total:.2f} ms")
    print(f"  • Latency per Decision   : {t_eval_total / len(sample_pairs):.2f} ms/pair")
    print(f"  • Reasoning Throughput   : {len(sample_pairs) / (t_eval_total / 1000.0):.1f} comparisons/sec")

    # -------------------------------------------------------------
    # Print Benchmark Summary Table
    # -------------------------------------------------------------
    print("\n" + "=" * 75)
    print("📋 EMPIRICAL BENCHMARK SUMMARY TABLE (Reproducible via time.perf_counter)")
    print("=" * 75)
    print(f"| {'Pipeline Stage':<32} | {'Metric Measured':<20} | {'Empirical Result':<16} |")
    print(f"|{'-' * 34}|{'-' * 22}|{'-' * 18}|")
    print(f"| {'PyMuPDF Document Extraction':<32} | {'Parsing Throughput':<20} | {total_pages / (t_parse_total / 1000.0):.1f} pages/sec   |")
    print(f"| {'PyMuPDF Page Latency':<32} | {'Average Page Time':<20} | {t_parse_total / total_pages:.2f} ms/page     |")
    print(f"| {'Semantic Chunking Engine':<32} | {'Chunking Latency':<20} | {t_chunk_total / len(all_chunks):.2f} ms/chunk    |")
    print(f"| {'MiniLM Embedding Generation':<32} | {'Vector Throughput':<20} | {len(sample_texts) / (t_embed_total / 1000.0):.1f} facts/sec   |")
    print(f"| {'MiniLM Embedding Latency':<32} | {'Per-Vector Latency':<20} | {t_embed_total / len(sample_texts):.2f} ms/fact     |")
    print(f"| {'FAISS Candidate Pruning Ratio':<32} | {'Search Space Reduction':<20} | {pruning_ratio:.2f}%           |")
    print(f"| {'FAISS Top-10 Query Latency':<32} | {'Vector Search Time':<20} | {t_faiss_total / n_facts:.3f} ms/query   |")
    print(f"| {'6-Stage Analytical Pipeline':<32} | {'Reasoning Throughput':<20} | {len(sample_pairs) / (t_eval_total / 1000.0):.1f} pairs/sec   |")
    print(f"| {'Cross-Document Decision Time':<32} | {'Per-Pair Evaluation':<20} | {t_eval_total / len(sample_pairs):.2f} ms/pair     |")
    print("=" * 75)

if __name__ == "__main__":
    run_benchmarks()
