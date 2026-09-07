import json
import logging
from typing import List, Dict, Any, Optional
from app.extraction.llm import UnifiedLLM, clean_json_response
from app.extraction.prompts import (
    FACT_EXTRACTION_SYSTEM_PROMPT,
    build_fact_extraction_prompt
)
from app.database.models import ChunkRecord, FactModel, FactRecord

logger = logging.getLogger(__name__)

class FactExtractor:
    def __init__(self, llm: Optional[UnifiedLLM] = None):
        self.llm = llm or UnifiedLLM()

    def extract_facts_from_chunk(
        self,
        chunk: ChunkRecord,
        page_texts: Optional[Dict[int, str]] = None
    ) -> List[FactRecord]:
        """
        Extracts structured facts from a chunk and grounds them with precise page numbers.
        """
        prompt = build_fact_extraction_prompt(chunk.text)
        try:
            raw_response = self.llm.generate(
                prompt=prompt,
                system_prompt=FACT_EXTRACTION_SYSTEM_PROMPT,
                json_mode=True
            )
        except Exception as e:
            logger.error(f"Error calling LLM for chunk {chunk.id}: {e}")
            return []

        cleaned_json = clean_json_response(raw_response)
        try:
            parsed = json.loads(cleaned_json)
        except json.JSONDecodeError:
            # Attempt basic repair if wrapped in an object or truncated
            try:
                # If wrapped in {"facts": [...]}
                obj = json.loads(cleaned_json + "]")
                parsed = obj if isinstance(obj, list) else obj.get("facts", [])
            except Exception:
                logger.error(f"Failed to parse JSON response: {cleaned_json[:200]}")
                return []

        if isinstance(parsed, dict) and "facts" in parsed:
            parsed = parsed["facts"]

        if not isinstance(parsed, list):
            logger.warning("Parsed output is not a list")
            return []

        fact_records: List[FactRecord] = []

        for item in parsed:
            if not isinstance(item, dict):
                continue
            try:
                fact_model = FactModel(**item)
            except Exception as val_err:
                logger.debug(f"Fact validation error: {val_err} for item {item}")
                continue

            # Grounding check: verify evidence is non-empty
            evidence = fact_model.evidence.strip()
            if not evidence or len(evidence) < 5:
                continue

            # Identify exact page number if page_texts mapping is available
            assigned_page = chunk.page_start
            if page_texts:
                evidence_lower = evidence.lower()
                for p_num in range(chunk.page_start, chunk.page_end + 1):
                    p_content = page_texts.get(p_num, "").lower()
                    if evidence_lower[:30] in p_content or evidence_lower in p_content:
                        assigned_page = p_num
                        break

            fact_json_str = json.dumps(fact_model.model_dump(), ensure_ascii=False)
            qualifiers_str = json.dumps(fact_model.qualifiers, ensure_ascii=False)

            fact_records.append(
                FactRecord(
                    document_id=chunk.document_id,
                    chunk_id=chunk.id,
                    page=assigned_page,
                    subject=fact_model.subject.strip(),
                    predicate=fact_model.predicate.strip(),
                    value=str(fact_model.value).strip(),
                    unit=fact_model.unit.strip(),
                    time_period=fact_model.time_period.strip(),
                    scope=fact_model.scope.strip(),
                    qualifiers_json=qualifiers_str,
                    evidence=evidence,
                    fact_json=fact_json_str
                )
            )

        return fact_records
