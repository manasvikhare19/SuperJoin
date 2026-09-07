import os
import shutil
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import UPLOADS_DIR
from app.database.db import DatabaseManager
from app.services.pipeline import KnowledgeLayerPipeline
from app.extraction.llm import UnifiedLLM

app = FastAPI(
    title="Fact Knowledge Layer API",
    description="REST API for ingesting PDFs, extracting grounded facts, and identifying cross-document relationships.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = DatabaseManager()
pipeline = KnowledgeLayerPipeline(db=db)

class FactCompareRequest(BaseModel):
    fact_a_id: int
    fact_b_id: int

@app.get("/")
def read_root():
    stats = db.get_stats()
    return {
        "name": "Fact Knowledge Layer API",
        "status": "online",
        "stats": stats,
        "active_llm": pipeline.llm.get_active_provider_name()
    }

@app.get("/api/stats")
def get_stats():
    return db.get_stats()

@app.get("/api/documents")
def list_documents():
    docs = db.list_documents()
    return {"documents": [d.model_dump() for d in docs]}

@app.post("/api/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    max_chunks: Optional[int] = Form(None)
):
    """
    Accepts any arbitrary PDF file, computes SHA-256, extracts facts,
    and runs cross-document matching against all existing facts.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # Save to uploads dir
    save_path = UPLOADS_DIR / file.filename
    with open(save_path, "wb") as f:
        f.write(file_bytes)

    result = pipeline.process_pdf(
        file_input=file_bytes,
        filename=file.filename,
        max_chunks=max_chunks
    )
    return result

@app.get("/api/facts")
def list_facts(
    document_id: Optional[int] = Query(None, description="Filter facts by document ID"),
    limit: int = Query(100, ge=1, le=1000)
):
    if document_id:
        facts = db.get_facts_by_document(document_id)
    else:
        facts = db.get_all_facts()
    return {"total": len(facts), "facts": [f.model_dump() for f in facts[:limit]]}

@app.get("/api/relationships")
def list_relationships(
    relationship_type: Optional[str] = Query(None, description="Filter: CORROBORATES, CONTRADICTS, RECONCILES, UNRELATED")
):
    rels = db.list_relationships(relationship_filter=relationship_type)
    return {"total": len(rels), "relationships": rels}

@app.post("/api/compare")
def compare_facts(request: FactCompareRequest):
    fact_a = db.get_fact_by_id(request.fact_a_id)
    fact_b = db.get_fact_by_id(request.fact_b_id)

    if not fact_a or not fact_b:
        raise HTTPException(status_code=404, detail="One or both fact IDs not found.")

    doc_a = db.get_document_by_id(fact_a.document_id)
    doc_b = db.get_document_by_id(fact_b.document_id)

    res = pipeline.classifier.compare_facts(
        fact_a=fact_a,
        fact_b=fact_b,
        doc_a_name=doc_a.filename if doc_a else "Doc A",
        doc_b_name=doc_b.filename if doc_b else "Doc B"
    )
    return {
        "fact_a_id": fact_a.id,
        "fact_b_id": fact_b.id,
        "relationship": res.relationship,
        "confidence": res.confidence,
        "reasoning": res.reasoning
    }
