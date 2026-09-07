import sqlite3
import json
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from app.config import DB_PATH
from app.database.models import DocumentRecord, ChunkRecord, FactRecord, RelationshipRecord
from app.ingestion.table_parser import get_demo_failure_case

def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn

def init_db(db_path: Path = DB_PATH):
    """Initializes SQLite database schema and handles incremental migrations."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                file_hash TEXT UNIQUE NOT NULL,
                file_size INTEGER DEFAULT 0,
                total_pages INTEGER DEFAULT 0,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata_json TEXT DEFAULT '{}'
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                chunk_index INTEGER NOT NULL,
                page_start INTEGER NOT NULL,
                page_end INTEGER NOT NULL,
                text TEXT NOT NULL,
                chunk_hash TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                chunk_id INTEGER REFERENCES chunks(id) ON DELETE SET NULL,
                page INTEGER NOT NULL,
                subject TEXT NOT NULL,
                predicate TEXT NOT NULL,
                value TEXT NOT NULL,
                unit TEXT DEFAULT '',
                time_period TEXT DEFAULT '',
                scope TEXT DEFAULT '',
                qualifiers_json TEXT DEFAULT '{}',
                evidence TEXT NOT NULL,
                evidence_status TEXT DEFAULT 'EXACT_MATCH',
                extraction_method TEXT DEFAULT 'LLM',
                confidence REAL DEFAULT 0.95,
                fact_json TEXT NOT NULL,
                embedding_blob BLOB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fact_a_id INTEGER NOT NULL REFERENCES facts(id) ON DELETE CASCADE,
                fact_b_id INTEGER NOT NULL REFERENCES facts(id) ON DELETE CASCADE,
                relationship TEXT NOT NULL,
                confidence REAL NOT NULL,
                reasoning TEXT NOT NULL,
                why_explanation TEXT DEFAULT '',
                why_not_explanation TEXT DEFAULT '',
                confidence_breakdown_json TEXT DEFAULT '{}',
                similarity REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(fact_a_id, fact_b_id)
            )
        """)

        # Migrations for existing databases
        fact_cols = [c[1] for c in cursor.execute("PRAGMA table_info(facts)").fetchall()]
        if "evidence_status" not in fact_cols:
            cursor.execute("ALTER TABLE facts ADD COLUMN evidence_status TEXT DEFAULT 'EXACT_MATCH'")
        if "extraction_method" not in fact_cols:
            cursor.execute("ALTER TABLE facts ADD COLUMN extraction_method TEXT DEFAULT 'LLM'")
        if "confidence" not in fact_cols:
            cursor.execute("ALTER TABLE facts ADD COLUMN confidence REAL DEFAULT 0.95")

        rel_cols = [c[1] for c in cursor.execute("PRAGMA table_info(relationships)").fetchall()]
        if "why_explanation" not in rel_cols:
            cursor.execute("ALTER TABLE relationships ADD COLUMN why_explanation TEXT DEFAULT ''")
        if "why_not_explanation" not in rel_cols:
            cursor.execute("ALTER TABLE relationships ADD COLUMN why_not_explanation TEXT DEFAULT ''")
        if "confidence_breakdown_json" not in rel_cols:
            cursor.execute("ALTER TABLE relationships ADD COLUMN confidence_breakdown_json TEXT DEFAULT '{}'")

        # Indexes for fast lookup
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_docs_hash ON documents(file_hash)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_facts_doc ON facts(document_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_facts_subject ON facts(subject)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_facts_pred ON facts(predicate)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_rel_facts ON relationships(fact_a_id, fact_b_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_rel_type ON relationships(relationship)")
        
        conn.commit()

class DatabaseManager:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        init_db(self.db_path)

    def get_document_by_hash(self, file_hash: str) -> Optional[DocumentRecord]:
        with get_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE file_hash = ?", (file_hash,)
            ).fetchone()
            if row:
                return DocumentRecord(**dict(row))
            return None

    def get_document_by_id(self, doc_id: int) -> Optional[DocumentRecord]:
        with get_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE id = ?", (doc_id,)
            ).fetchone()
            if row:
                return DocumentRecord(**dict(row))
            return None

    def insert_document(self, doc: DocumentRecord) -> int:
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO documents (filename, file_hash, file_size, total_pages, metadata_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (doc.filename, doc.file_hash, doc.file_size, doc.total_pages, doc.metadata_json)
            )
            conn.commit()
            return cursor.lastrowid

    def list_documents(self) -> List[DocumentRecord]:
        with get_connection(self.db_path) as conn:
            rows = conn.execute("SELECT * FROM documents ORDER BY id ASC").fetchall()
            return [DocumentRecord(**dict(r)) for r in rows]

    def insert_chunks(self, chunks: List[ChunkRecord]) -> List[int]:
        ids = []
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            for ch in chunks:
                cursor.execute(
                    """
                    INSERT INTO chunks (document_id, chunk_index, page_start, page_end, text, chunk_hash)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (ch.document_id, ch.chunk_index, ch.page_start, ch.page_end, ch.text, ch.chunk_hash)
                )
                ids.append(cursor.lastrowid)
            conn.commit()
        return ids

    def insert_facts(self, facts: List[FactRecord]) -> List[int]:
        ids = []
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            for f in facts:
                cursor.execute(
                    """
                    INSERT INTO facts (
                        document_id, chunk_id, page, subject, predicate, value,
                        unit, time_period, scope, qualifiers_json, evidence,
                        evidence_status, extraction_method, confidence,
                        fact_json, embedding_blob
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f.document_id, f.chunk_id, f.page, f.subject, f.predicate,
                        f.value, f.unit, f.time_period, f.scope, f.qualifiers_json,
                        f.evidence, getattr(f, "evidence_status", "EXACT_MATCH"),
                        getattr(f, "extraction_method", "LLM"), getattr(f, "confidence", 0.95),
                        f.fact_json, f.embedding_blob
                    )
                )
                ids.append(cursor.lastrowid)
            conn.commit()
        return ids

    def update_fact_embedding(self, fact_id: int, embedding_blob: bytes):
        with get_connection(self.db_path) as conn:
            conn.execute(
                "UPDATE facts SET embedding_blob = ? WHERE id = ?",
                (embedding_blob, fact_id)
            )
            conn.commit()

    def get_facts_by_document(self, document_id: int) -> List[FactRecord]:
        with get_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM facts WHERE document_id = ? ORDER BY page ASC, id ASC",
                (document_id,)
            ).fetchall()
            return [FactRecord(**dict(r)) for r in rows]

    def get_all_facts(self) -> List[FactRecord]:
        with get_connection(self.db_path) as conn:
            rows = conn.execute("SELECT * FROM facts ORDER BY id ASC").fetchall()
            return [FactRecord(**dict(r)) for r in rows]

    def get_fact_by_id(self, fact_id: int) -> Optional[FactRecord]:
        with get_connection(self.db_path) as conn:
            row = conn.execute("SELECT * FROM facts WHERE id = ?", (fact_id,)).fetchone()
            if row:
                return FactRecord(**dict(row))
            return None

    def insert_relationship(self, rel: RelationshipRecord) -> int:
        with get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO relationships (
                    fact_a_id, fact_b_id, relationship, confidence, reasoning,
                    why_explanation, why_not_explanation, confidence_breakdown_json, similarity
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rel.fact_a_id, rel.fact_b_id, rel.relationship, rel.confidence, rel.reasoning,
                    getattr(rel, "why_explanation", ""), getattr(rel, "why_not_explanation", ""),
                    getattr(rel, "confidence_breakdown_json", "{}"), rel.similarity
                )
            )
            conn.commit()
            return cursor.lastrowid

    def list_relationships(self, relationship_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns relationships joined with fact and document information for easy presentation."""
        query = """
            SELECT 
                r.id as relationship_id,
                r.relationship,
                r.confidence,
                r.reasoning,
                r.why_explanation,
                r.why_not_explanation,
                r.confidence_breakdown_json,
                r.similarity,
                r.created_at,
                fa.id as fact_a_id,
                fa.subject as fact_a_subject,
                fa.predicate as fact_a_predicate,
                fa.value as fact_a_value,
                fa.unit as fact_a_unit,
                fa.time_period as fact_a_period,
                fa.scope as fact_a_scope,
                fa.evidence as fact_a_evidence,
                fa.evidence_status as fact_a_evidence_status,
                fa.extraction_method as fact_a_extraction_method,
                fa.page as fact_a_page,
                da.id as doc_a_id,
                da.filename as doc_a_filename,
                fb.id as fact_b_id,
                fb.subject as fact_b_subject,
                fb.predicate as fact_b_predicate,
                fb.value as fact_b_value,
                fb.unit as fact_b_unit,
                fb.time_period as fact_b_period,
                fb.scope as fact_b_scope,
                fb.evidence as fact_b_evidence,
                fb.evidence_status as fact_b_evidence_status,
                fb.extraction_method as fact_b_extraction_method,
                fb.page as fact_b_page,
                db.id as doc_b_id,
                db.filename as doc_b_filename
            FROM relationships r
            JOIN facts fa ON r.fact_a_id = fa.id
            JOIN documents da ON fa.document_id = da.id
            JOIN facts fb ON r.fact_b_id = fb.id
            JOIN documents db ON fb.document_id = db.id
        """
        params = []
        if relationship_filter:
            query += " WHERE r.relationship = ?"
            params.append(relationship_filter.upper())
        query += " ORDER BY r.confidence DESC, r.similarity DESC"

        with get_connection(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def get_four_cases(self) -> Dict[str, Any]:
        """
        Dynamically queries the database for the 4 core cases required by the assignment:
        1. Corroboration: Two documents affirming the same fact.
        2. Contradiction: Two documents with incompatible values.
        3. Context-based Reconciliation: Divergent figures reconciled by time/scope.
        4. Real Extraction Failure Case Study: Demonstrating raw table flattening vs layout-aware recovery.
        """
        all_rels = self.list_relationships()

        corrob_rel = next((r for r in all_rels if r["relationship"] == "CORROBORATES"), None)
        contradict_rel = next((r for r in all_rels if r["relationship"] in ("CONTRADICTS", "LIKELY_CONTRADICTION")), None)
        reconcile_rel = next((r for r in all_rels if r["relationship"] == "RECONCILES"), None)

        return {
            "corroboration": corrob_rel,
            "contradiction": contradict_rel,
            "reconciliation": reconcile_rel,
            "extraction_failure": get_demo_failure_case()
        }

    def get_stats(self) -> Dict[str, int]:
        with get_connection(self.db_path) as conn:
            doc_count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            chunk_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            fact_count = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
            rel_count = conn.execute("SELECT COUNT(*) FROM relationships").fetchone()[0]
            return {
                "documents": doc_count,
                "chunks": chunk_count,
                "facts": fact_count,
                "relationships": rel_count
            }

    def clear_all(self):
        """Reset all tables."""
        with get_connection(self.db_path) as conn:
            conn.execute("DELETE FROM relationships")
            conn.execute("DELETE FROM facts")
            conn.execute("DELETE FROM chunks")
            conn.execute("DELETE FROM documents")
            conn.commit()
