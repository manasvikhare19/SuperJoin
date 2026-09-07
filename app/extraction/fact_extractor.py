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
            logger.warning(f"LLM not available for chunk {chunk.id}: {e}. Triggering deterministic rule-based extraction fallback.")
            return self.fallback_heuristic_extraction(chunk, page_texts)

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

    def fallback_heuristic_extraction(
        self,
        chunk: ChunkRecord,
        page_texts: Optional[Dict[int, str]] = None
    ) -> List[FactRecord]:
        """
        Deterministic pattern-based fallback extractor when LLM is offline.
        Extracts grounded numerical claims, currency metrics, and percentages
        directly from sentences with exact source evidence.
        """
        import re
        text = chunk.text
        sentences = re.split(r'(?<=[.!?\n])\s+', text)
        facts: List[FactRecord] = []
        seen_values = set()

        subject = "Entity"
        t_lower = text.lower()
        if "delhivery" in t_lower:
            subject = "Delhivery"
        elif "india" in t_lower or "economy" in t_lower or "gdp" in t_lower:
            subject = "India"
        elif "reserve bank" in t_lower or "rbi" in t_lower:
            subject = "Reserve Bank of India"
        elif "imf" in t_lower:
            subject = "IMF"

        for s in sentences:
            s = s.strip()
            if len(s) < 15 or len(s) > 300:
                continue

            fin_match = re.search(r'(?:₹|INR|Rs\.?)\s*([\d,]+(?:\.\d+)?)\s*(Cr|crore|million|mn|billion|bn|lakh)?', s, re.IGNORECASE)
            pct_match = re.search(r'([\d]+(?:\.\d+)?)\s*(%|per\s*cent|percent)', s, re.IGNORECASE)

            metric_name = None
            s_lower = s.lower()
            if "revenue" in s_lower:
                metric_name = "revenue from operations"
            elif "ebitda" in s_lower:
                metric_name = "EBITDA"
            elif "gdp" in s_lower:
                metric_name = "real GDP growth rate"
            elif "inflation" in s_lower:
                metric_name = "CPI inflation"
            elif "shipment" in s_lower or "parcel" in s_lower:
                metric_name = "express parcel shipments"
            elif "freight" in s_lower or "tonnage" in s_lower:
                metric_name = "PTL freight tonnage"

            if metric_name and (fin_match or pct_match):
                if fin_match:
                    val = fin_match.group(1).replace(",", "")
                    unit = (fin_match.group(2) or "INR").strip()
                    if "cr" in unit.lower():
                        unit = "INR crore"
                    elif "million" in unit.lower() or "mn" in unit.lower():
                        unit = "million INR"
                else:
                    val = pct_match.group(1)
                    unit = "percent"

                key = (metric_name, val)
                if key in seen_values:
                    continue
                seen_values.add(key)

                period = ""
                fy_match = re.search(r'\b(FY\s*\d{2,4}|20\d{2}-\d{2}|Q[1-4]\s*FY\s*\d{2,4})\b', s, re.IGNORECASE)
                if fy_match:
                    period = fy_match.group(0)

                scope = "consolidated" if "consolidated" in s_lower else ("standalone" if "standalone" in s_lower else "")

                assigned_page = chunk.page_start
                if page_texts:
                    for p_num in range(chunk.page_start, chunk.page_end + 1):
                        if s[:25].lower() in page_texts.get(p_num, "").lower():
                            assigned_page = p_num
                            break

                fact_dict = {
                    "subject": subject,
                    "predicate": metric_name,
                    "value": val,
                    "unit": unit,
                    "time_period": period,
                    "scope": scope,
                    "qualifiers": {"extracted_via": "deterministic_fallback"},
                    "evidence": s
                }

                facts.append(
                    FactRecord(
                        document_id=chunk.document_id,
                        chunk_id=chunk.id,
                        page=assigned_page,
                        subject=subject,
                        predicate=metric_name,
                        value=val,
                        unit=unit,
                        time_period=period,
                        scope=scope,
                        qualifiers_json=json.dumps(fact_dict["qualifiers"]),
                        evidence=s,
                        fact_json=json.dumps(fact_dict, ensure_ascii=False)
                    )
                )

                if len(facts) >= 6:
                    break

        return facts
