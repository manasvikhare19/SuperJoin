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
    fact_json: str
    embedding_blob: Optional[bytes] = None
    created_at: Optional[str] = None

class RelationshipResult(BaseModel):
    relationship: str = Field(description="CORROBORATES, CONTRADICTS, RECONCILES, or UNRELATED")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0")
    reasoning: str = Field(description="Detailed explanation justifying the classification based on context and evidence")

class RelationshipRecord(BaseModel):
    id: Optional[int] = None
    fact_a_id: int
    fact_b_id: int
    relationship: str
    confidence: float
    reasoning: str
    similarity: Optional[float] = 0.0
    created_at: Optional[str] = None
