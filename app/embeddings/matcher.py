import logging
from typing import List, Tuple, Dict, Any, Optional
import faiss
import numpy as np
from app.config import SIMILARITY_THRESHOLD
from app.database.models import FactRecord
from app.embeddings.embedder import FactEmbedder

logger = logging.getLogger(__name__)

class CandidateMatcher:
    def __init__(self, embedder: Optional[FactEmbedder] = None, threshold: float = SIMILARITY_THRESHOLD):
        self.embedder = embedder or FactEmbedder()
        self.threshold = threshold
        self.dimension = self.embedder.dimension
        self.index: Optional[faiss.IndexFlatIP] = None
        self.fact_records: List[FactRecord] = []
        self.fact_id_map: Dict[int, FactRecord] = {}

    def build_index(self, all_facts: List[FactRecord]):
        """Builds a FAISS IndexFlatIP index over all existing facts."""
        self.fact_records = list(all_facts)
        self.fact_id_map = {f.id: f for f in all_facts if f.id is not None}
        
        if not all_facts:
            self.index = faiss.IndexFlatIP(self.dimension)
            return

        # Identify any facts missing embeddings and batch compute them upfront
        missing_indices = [i for i, f in enumerate(all_facts) if not f.embedding_blob]
        if missing_indices:
            missing_facts = [all_facts[i] for i in missing_indices]
            computed_vectors = self.embedder.embed_facts(missing_facts)
            from app.database.db import DatabaseManager
            db = DatabaseManager()
            for idx, vec in zip(missing_indices, computed_vectors):
                blob = FactEmbedder.vector_to_blob(vec)
                all_facts[idx].embedding_blob = blob
                if all_facts[idx].id:
                    db.update_fact_embedding(all_facts[idx].id, blob)

        # Build vectors in exact 1:1 positional order matching self.fact_records
        vectors = [FactEmbedder.blob_to_vector(f.embedding_blob) for f in all_facts]
        matrix = np.vstack(vectors).astype(np.float32)
        # Normalize vectors for cosine similarity via inner product
        faiss.normalize_L2(matrix)

        self.index = faiss.IndexFlatIP(self.dimension)
        self.index.add(matrix)
        logger.info(f"FAISS index built with {self.index.ntotal} facts.")

    def add_facts(self, new_facts: List[FactRecord]) -> int:
        """
        Incrementally adds new facts to the existing FAISS index in O(ΔN) time.
        Avoids full index recomputation over existing facts.
        """
        if not new_facts:
            return 0

        if self.index is None:
            self.build_index(new_facts)
            return len(new_facts)

        # Identify any new facts missing embeddings and batch compute them upfront
        missing_indices = [i for i, f in enumerate(new_facts) if not f.embedding_blob]
        if missing_indices:
            missing_facts = [new_facts[i] for i in missing_indices]
            computed_vectors = self.embedder.embed_facts(missing_facts)
            for idx, vec in zip(missing_indices, computed_vectors):
                new_facts[idx].embedding_blob = FactEmbedder.vector_to_blob(vec)

        # Build vectors in exact 1:1 positional order matching new_facts
        vectors = [FactEmbedder.blob_to_vector(f.embedding_blob) for f in new_facts]
        matrix = np.vstack(vectors).astype(np.float32)
        faiss.normalize_L2(matrix)

        self.index.add(matrix)
        self.fact_records.extend(new_facts)
        for f in new_facts:
            if f.id is not None:
                self.fact_id_map[f.id] = f

        logger.info(f"Incrementally added {len(new_facts)} facts to FAISS. Total in index: {self.index.ntotal}")
        return len(new_facts)

    def clear(self):
        """Resets the FAISS index and associated fact records."""
        self.index = None
        self.fact_records = []
        self.fact_id_map = {}

    def find_cross_document_candidates(
        self,
        new_facts: Optional[List[FactRecord]] = None,
        top_k: int = 10
    ) -> List[Tuple[FactRecord, FactRecord, float]]:
        """
        Finds candidate pairs of facts across different documents.
        If new_facts is provided, only searches candidates between new_facts and existing facts.
        Otherwise compares all facts in the index.
        Returns: [(fact_a, fact_b, cosine_similarity), ...]
        """
        if self.index is None or self.index.ntotal == 0:
            return []

        query_facts = new_facts if new_facts is not None else self.fact_records
        if not query_facts:
            return []

        # Ensure query facts have embeddings
        query_vectors = []
        for qf in query_facts:
            if qf.embedding_blob:
                vec = FactEmbedder.blob_to_vector(qf.embedding_blob)
            else:
                vec = self.embedder.embed_facts([qf])[0]
                qf.embedding_blob = FactEmbedder.vector_to_blob(vec)
            query_vectors.append(vec)

        query_matrix = np.vstack(query_vectors).astype(np.float32)
        faiss.normalize_L2(query_matrix)

        k = min(top_k, self.index.ntotal)
        distances, indices = self.index.search(query_matrix, k)

        candidates: List[Tuple[FactRecord, FactRecord, float]] = []
        seen_pairs = set()

        for q_idx, qf in enumerate(query_facts):
            for match_rank in range(k):
                matched_idx = indices[q_idx][match_rank]
                sim = float(distances[q_idx][match_rank])

                if matched_idx < 0 or sim < self.threshold:
                    continue

                matched_fact = self.fact_records[matched_idx]

                # STRICT RULE: Must be from DIFFERENT documents
                if qf.document_id == matched_fact.document_id:
                    continue

                # Ensure canonical pair ordering by fact ID to avoid (A, B) and (B, A)
                id_a = qf.id or 0
                id_b = matched_fact.id or 0
                pair_key = (min(id_a, id_b), max(id_a, id_b))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                if id_a <= id_b:
                    candidates.append((qf, matched_fact, sim))
                else:
                    candidates.append((matched_fact, qf, sim))

        # Sort by similarity descending
        candidates.sort(key=lambda x: x[2], reverse=True)
        return candidates
