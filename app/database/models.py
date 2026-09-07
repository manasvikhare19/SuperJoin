from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

class DocumentRecord(BaseModel):
    id: Optional[int] = None
    filename: str
    file_hash: str
    file_size: int = 0
    total_pages: int = 0
    uploaded_at: Optional[str] = None
    metadata_json: Optional[str] = "{}"

class ChunkRecord(BaseModel):
    id: Optional[int] = None
    document_id: int
    chunk_index: int
    page_start: int
    page_end: int
    text: str
    chunk_hash: str

class FactModel(BaseModel):
    subject: str = Field(description="Entity or topic the fact refers to, e.g. Delhivery, India, Reserve Bank")
    predicate: str = Field(description="Property or metric, e.g. revenue from operations, real GDP growth, EBITDA")
    value: str = Field(description="Extracted value, number, or categorical claim, e.g. 8142, 6.4%, Mumbai")
    unit: str = Field(default="", description="Measurement unit, e.g. INR crore, percent, metric tonnes")
    time_period: str = Field(default="", description="Time period covered, e.g. FY2024, Q4 FY24, 2024-25, current")
    scope: str = Field(default="", description="Scope of reporting, e.g. consolidated, standalone, headline, core")
    qualifiers: Dict[str, Any] = Field(default_factory=dict, description="Additional context, footnotes, YoY growth rate")
    evidence: str = Field(description="Exact verbatim text quoted from the source document supporting this fact")
    confidence: float = Field(default=0.95, ge=0.0, le=1.0, description="Extraction confidence score")
    evidence_status: str = Field(default="EXACT_MATCH", description="EXACT_MATCH, NORMALIZED_MATCH, or UNVERIFIED")
    extraction_method: str = Field(default="LLM", description="LLM, TABLE_PARSER, or HEURISTIC_FALLBACK")

class FactRecord(BaseModel):
    id: Optional[int] = None
    document_id: int
    chunk_id: Optional[int] = None
    page: int
    subject: str
    predicate: str
    value: str
    unit: str = ""
    time_period: str = ""
    scope: str = ""
    qualifiers_json: str = "{}"
    evidence: str
    evidence_status: str = "EXACT_MATCH"
    extraction_method: str = "LLM"
    confidence: float = 0.95
    fact_json: str
    embedding_blob: Optional[bytes] = None
    created_at: Optional[str] = None

class ConfidenceBreakdown(BaseModel):
    semantic_similarity: float = 0.0
    entity_match: float = 0.0
    predicate_match: float = 0.0
    time_compatibility: float = 0.0
    scope_compatibility: float = 0.0
    numerical_compatibility: float = 0.0
    composite_score: float = 0.0

class RelationshipResult(BaseModel):
    relationship: str = Field(description="CORROBORATES, CONTRADICTS, LIKELY_CONTRADICTION, RECONCILES, NEEDS_REVIEW, or UNRELATED")
    confidence: float = Field(ge=0.0, le=1.0, description="Composite evidence-based confidence score")
    reasoning: str = Field(description="Detailed explanation justifying the classification based on context and evidence")
    why_explanation: str = Field(default="", description="Explicit breakdown of positive evidence supporting this class")
    why_not_explanation: str = Field(default="", description="Explicit justification for rejecting alternative classifications")
    breakdown: Optional[Dict[str, float]] = Field(default_factory=dict, description="Calibrated component weights")

class RelationshipRecord(BaseModel):
    id: Optional[int] = None
    fact_a_id: int
    fact_b_id: int
    relationship: str
    confidence: float
    reasoning: str
    why_explanation: str = ""
    why_not_explanation: str = ""
    confidence_breakdown_json: str = "{}"
    similarity: Optional[float] = 0.0
    created_at: Optional[str] = None
