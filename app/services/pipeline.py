import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable, Union
from app.database.db import DatabaseManager
from app.database.models import DocumentRecord, FactRecord, RelationshipRecord
from app.ingestion.pdf_loader import extract_pdf_pages, compute_sha256
from app.ingestion.chunker import chunk_pdf_pages
from app.extraction.llm import UnifiedLLM
from app.extraction.fact_extractor import FactExtractor
from app.embeddings.embedder import FactEmbedder
from app.embeddings.matcher import CandidateMatcher
from app.comparison.relationship import RelationshipClassifier

logger = logging.getLogger(__name__)

class KnowledgeLayerPipeline:
    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        llm: Optional[UnifiedLLM] = None
    ):
        self.db = db or DatabaseManager()
        self.llm = llm or UnifiedLLM()
        self.fact_extractor = FactExtractor(llm=self.llm)
        self.embedder = FactEmbedder()
        self.matcher = CandidateMatcher(embedder=self.embedder)
        self.classifier = RelationshipClassifier(llm=self.llm)

    def process_pdf(
        self,
        file_input: Union[str, Path, bytes],
        filename: str,
        progress_callback: Optional[Callable[[str, float], None]] = None,
        max_chunks: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        End-to-end ingestion and cross-document reasoning for a single PDF.
        Supports incremental processing: skips already processed PDFs by SHA-256,
        and only compares new facts against existing facts in the database.
        """
        def update_progress(msg: str, pct: float):
            if progress_callback:
                progress_callback(msg, pct)
            logger.info(f"[{pct*100:.0f}%] {msg}")

        update_progress("Computing SHA-256 checksum...", 0.05)
        file_hash = compute_sha256(file_input)

        # Check if already processed
        existing_doc = self.db.get_document_by_hash(file_hash)
        if existing_doc:
            update_progress("Document already processed. Loaded from cache.", 1.0)
            existing_facts = self.db.get_facts_by_document(existing_doc.id)
            return {
                "status": "cached",
                "document_id": existing_doc.id,
                "filename": existing_doc.filename,
                "facts_count": len(existing_facts),
                "new_relationships": 0,
                "message": f"Document '{filename}' was already processed with {len(existing_facts)} facts."
            }

        update_progress("Extracting pages via PyMuPDF...", 0.15)
        extraction_result = extract_pdf_pages(file_input)
        total_pages = extraction_result["total_pages"]
        pages = extraction_result["pages"]

        # Calculate file size
        if isinstance(file_input, bytes):
            file_size = len(file_input)
        else:
            file_size = Path(file_input).stat().st_size

        # Record document
        doc_record = DocumentRecord(
            filename=filename,
            file_hash=file_hash,
            file_size=file_size,
            total_pages=total_pages,
            metadata_json=json.dumps({"pages_extracted": total_pages})
        )
        doc_id = self.db.insert_document(doc_record)
        update_progress(f"Registered document (ID: {doc_id}). Creating semantic chunks...", 0.25)

        # Create semantic chunks
        chunks = chunk_pdf_pages(pages, document_id=doc_id)
        if max_chunks and len(chunks) > max_chunks:
            chunks = chunks[:max_chunks]

        chunk_ids = self.db.insert_chunks(chunks)
        for ch, cid in zip(chunks, chunk_ids):
            ch.id = cid

        update_progress(f"Chunked into {len(chunks)} sections. Extracting grounded facts...", 0.35)

        # Page text lookup for exact grounding
        page_texts = {p["page_number"]: p["text"] for p in pages}

        all_extracted_facts: List[FactRecord] = []
        for idx, chunk in enumerate(chunks):
            sub_pct = 0.35 + (0.35 * (idx / max(1, len(chunks))))
            update_progress(f"Extracting facts from chunk {idx+1}/{len(chunks)} (p. {chunk.page_start}-{chunk.page_end})...", sub_pct)
            
            chunk_facts = self.fact_extractor.extract_facts_from_chunk(
                chunk=chunk,
                page_texts=page_texts
            )
            all_extracted_facts.extend(chunk_facts)

        if all_extracted_facts:
            update_progress(f"Inserting {len(all_extracted_facts)} facts and generating embeddings...", 0.70)
            fact_ids = self.db.insert_facts(all_extracted_facts)
            for f, fid in zip(all_extracted_facts, fact_ids):
                f.id = fid

            # Embed facts and store vector blobs
            vectors = self.embedder.embed_facts(all_extracted_facts)
            for f, vec in zip(all_extracted_facts, vectors):
                blob = FactEmbedder.vector_to_blob(vec)
                f.embedding_blob = blob
                self.db.update_fact_embedding(f.id, blob)
        else:
            update_progress("No checkable facts found in text chunks.", 0.70)

        # Cross-Document Relationship Matching
        update_progress("Finding cross-document candidates with FAISS...", 0.80)
        all_db_facts = self.db.get_all_facts()
        self.matcher.build_index(all_db_facts)

        # Only compare new facts against existing facts
        candidates = self.matcher.find_cross_document_candidates(
            new_facts=all_extracted_facts,
            top_k=10
        )

        update_progress(f"Discovered {len(candidates)} cross-document candidate pairs. Classifying relationships...", 0.85)

        # Pre-fetch document filenames for clean prompts
        doc_names = {d.id: d.filename for d in self.db.list_documents()}

        new_relationships_count = 0
        for c_idx, (fa, fb, sim) in enumerate(candidates):
            rel_pct = 0.85 + (0.13 * (c_idx / max(1, len(candidates))))
            update_progress(f"Reasoning pair {c_idx+1}/{len(candidates)}: [{fa.subject}] vs [{fb.subject}]...", rel_pct)

            doc_a_name = doc_names.get(fa.document_id, f"Doc {fa.document_id}")
            doc_b_name = doc_names.get(fb.document_id, f"Doc {fb.document_id}")

            res = self.classifier.compare_facts(
                fact_a=fa,
                fact_b=fb,
                doc_a_name=doc_a_name,
                doc_b_name=doc_b_name,
                similarity=sim
            )

            # Insert relationship if meaningful (or even UNRELATED with low confidence if needed)
            rel_record = RelationshipRecord(
                fact_a_id=fa.id,
                fact_b_id=fb.id,
                relationship=res.relationship,
                confidence=res.confidence,
                reasoning=res.reasoning,
                similarity=sim
            )
            self.db.insert_relationship(rel_record)
            if res.relationship in ["CORROBORATES", "CONTRADICTS", "RECONCILES"]:
                new_relationships_count += 1

        update_progress("Pipeline processing complete!", 1.0)

        return {
            "status": "success",
            "document_id": doc_id,
            "filename": filename,
            "facts_count": len(all_extracted_facts),
            "candidates_found": len(candidates),
            "new_relationships": new_relationships_count,
            "message": f"Successfully extracted {len(all_extracted_facts)} facts and identified relationships across documents."
        }
