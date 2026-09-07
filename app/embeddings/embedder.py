import logging
from typing import List, Union
import numpy as np
from sentence_transformers import SentenceTransformer
from app.config import EMBEDDING_MODEL_NAME
from app.database.models import FactRecord

logger = logging.getLogger(__name__)

class FactEmbedder:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(FactEmbedder, cls).__new__(cls)
            cls._instance.model = None
        return cls._instance

    def __init__(self, model_name: str = EMBEDDING_MODEL_NAME):
        if self.model is None:
            logger.info(f"Loading sentence-transformer embedding model: {model_name}...")
            self.model = SentenceTransformer(model_name)
            if hasattr(self.model, "get_embedding_dimension"):
                self.dimension = self.model.get_embedding_dimension()
            else:
                self.dimension = self.model.get_sentence_embedding_dimension()
            logger.info(f"Embedding model loaded. Vector dimension: {self.dimension}")

    @staticmethod
    def format_fact_text(fact: Union[FactRecord, dict]) -> str:
        if isinstance(fact, FactRecord):
            subject = fact.subject
            predicate = fact.predicate
            val = f"{fact.value} {fact.unit}".strip()
            period = fact.time_period
            scope = fact.scope
        else:
            subject = fact.get("subject", "")
            predicate = fact.get("predicate", "")
            val = f"{fact.get('value', '')} {fact.get('unit', '')}".strip()
            period = fact.get("time_period", "")
            scope = fact.get("scope", "")

        parts = [p for p in [subject, predicate, val, period, scope] if p]
        return " | ".join(parts)

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)
        embeddings = self.model.encode(
            texts,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True
        )
        return embeddings.astype(np.float32)

    def embed_facts(self, facts: List[FactRecord]) -> np.ndarray:
        texts = [self.format_fact_text(f) for f in facts]
        return self.embed_texts(texts)

    @staticmethod
    def vector_to_blob(vector: np.ndarray) -> bytes:
        return vector.astype(np.float32).tobytes()

    @staticmethod
    def blob_to_vector(blob: bytes) -> np.ndarray:
        return np.frombuffer(blob, dtype=np.float32)
