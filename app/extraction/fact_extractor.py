import json
import logging
import re
from typing import List, Dict, Any, Optional
from app.extraction.llm import UnifiedLLM, clean_json_response
from app.extraction.prompts import (
    FACT_EXTRACTION_SYSTEM_PROMPT,
    build_fact_extraction_prompt
)
from app.database.models import ChunkRecord, FactModel, FactRecord
from app.ingestion.evidence_verifier import verify_evidence

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
        Extracts structured facts from a chunk, verifies evidence grounding against
        page text, and assigns confidence and provenance metadata.
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
            try:
                obj = json.loads(cleaned_json + "]")
                parsed = obj if isinstance(obj, list) else obj.get("facts", [])
            except Exception:
                logger.error(f"Failed to parse JSON response: {cleaned_json[:200]}")
                return self.fallback_heuristic_extraction(chunk, page_texts)

        if isinstance(parsed, dict) and "facts" in parsed:
            parsed = parsed["facts"]

        if not isinstance(parsed, list):
            logger.warning("Parsed output is not a list, falling back to heuristic extraction")
            return self.fallback_heuristic_extraction(chunk, page_texts)

        fact_records: List[FactRecord] = []

        for item in parsed:
            if not isinstance(item, dict):
                continue
            try:
                fact_model = FactModel(**item)
            except Exception as val_err:
                logger.debug(f"Fact validation error: {val_err} for item {item}")
                continue

            evidence = fact_model.evidence.strip()
            if not evidence or len(evidence) < 5:
                continue

            # Identify exact page number and verify evidence
            assigned_page = chunk.page_start
            evidence_status = "EXACT_MATCH"
            grounding_score = 0.95

            target_text = chunk.text
            if page_texts:
                for p_num in range(chunk.page_start, chunk.page_end + 1):
                    p_content = page_texts.get(p_num, "")
                    status, score = verify_evidence(evidence, p_content)
                    if status in ("EXACT_MATCH", "NORMALIZED_MATCH"):
                        assigned_page = p_num
                        evidence_status = status
                        grounding_score = score
                        break
            else:
                evidence_status, grounding_score = verify_evidence(evidence, target_text)

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
                    evidence_status=evidence_status,
                    extraction_method="LLM",
                    confidence=grounding_score,
                    fact_json=fact_json_str
                )
            )

        if not fact_records:
            return self.fallback_heuristic_extraction(chunk, page_texts)

        return fact_records

    def fallback_heuristic_extraction(
        self,
        chunk: ChunkRecord,
        page_texts: Optional[Dict[int, str]] = None
    ) -> List[FactRecord]:
        """
        Deterministic pattern-based fallback extractor when LLM is offline.
        Handles both continuous narrative sentences and multi-line slide presentations
        via a sliding window across adjacent lines.
        """
        text = chunk.text
        lines = [l.strip() for l in text.splitlines() if l.strip()]

        # Generate candidate text segments: single sentences, individual lines, and 2-line pairs
        raw_candidates = re.split(r'(?<=[.!?])\s+', text)
        for i in range(len(lines)):
            raw_candidates.append(lines[i])
            if i + 1 < len(lines):
                raw_candidates.append(lines[i] + " " + lines[i+1])

        facts: List[FactRecord] = []
        seen_keys = set()

        # Generic candidate proper-noun extraction without hardcoded entity names
        non_entity_words = {
            "The", "This", "That", "These", "Those", "In", "On", "At", "For", "To", "From", "With", "By",
            "As", "According", "Figure", "Table", "Source", "Note", "Total", "During", "Over", "Between",
            "Revenue", "EBITDA", "PAT", "GDP", "CPI", "FY", "Quarter", "Reported", "Consolidated", "Standalone",
            "Adjusted", "Annual", "Financial", "Statement", "Results", "Operations", "Balance", "Net", "Gross"
        }

        def extract_entities(segment: str) -> List[str]:
            found = []
            for match in re.finditer(r'\b[A-Z][a-zA-Z0-9\.]+(?:\s+[A-Z][a-zA-Z0-9\.]+)*\b', segment):
                cand_str = match.group(0).strip()
                words = [w for w in cand_str.split() if w not in non_entity_words]
                if words and len(" ".join(words)) > 2:
                    found.append(" ".join(words))
            return found

        # Determine chunk-level dominant entity
        chunk_entities = extract_entities(text)
        default_subject = "Entity"
        if chunk_entities:
            from collections import Counter
            default_subject = Counter(chunk_entities).most_common(1)[0][0]

        for cand in raw_candidates:
            s = cand.strip()
            if len(s) < 12 or len(s) > 350:
                continue

            fin_match = re.search(r'(?:₹|INR|Rs\.?|\$|€|£)\s*([\d,]+(?:\.\d+)?)\s*(Cr|crore|million|mn|billion|bn|lakh)?', s, re.IGNORECASE)
            pct_match = re.search(r'([\d]+(?:\.\d+)?)\s*(%|per\s*cent|percent)', s, re.IGNORECASE)
            vol_match = re.search(r'([\d,]+(?:\.\d+)?)\s*(Mn|million|Bn|billion|K)\s*(?:Tons|tons|shipments|parcels)', s, re.IGNORECASE)
            sci_match = re.search(r'([\d,]+(?:\.\d+)?)\s*(ppm|ppb|°C|deg\s*C|GW|gigawatts?|million\s*sq\s*km|sq\s*km|sq\s*mi)\b', s, re.IGNORECASE)

            val = None
            unit = ""

            # Determine value and unit first to ensure dimensional predicate alignment
            if fin_match:
                val = fin_match.group(1).replace(",", "")
                unit_raw = (fin_match.group(2) or "INR").strip().lower()
                if "cr" in unit_raw:
                    unit = "INR crore"
                elif "million" in unit_raw or "mn" in unit_raw:
                    unit = "million INR"
                elif "bn" in unit_raw or "billion" in unit_raw:
                    unit = "billion INR"
                else:
                    unit = "INR"
            elif pct_match:
                val = pct_match.group(1)
                unit = "percent"
            elif vol_match:
                val = vol_match.group(1).replace(",", "")
                unit = f"{vol_match.group(2)} {vol_match.group(0).split()[-1]}"
            elif sci_match:
                val = sci_match.group(1).replace(",", "")
                unit_raw = sci_match.group(2).strip()
                if unit_raw.lower() in ["°c", "deg c"]:
                    unit = "°C"
                else:
                    unit = unit_raw

            if not val:
                continue

            metric_name = None
            s_lower = s.lower()

            # 1. Primary: Generic Domain-Agnostic Metric Anchor Extraction
            # Extracts noun phrase preceding the value across arbitrary domains (medical, science, legal, finance)
            anchor_match = re.search(
                r'\b(?:of|is|was|stood at|reached|reported at|recorded at|grew by|declined by|amounted to|totaled|at|rose to|dropped to|averaged)\b\s*(?:₹|\$|€|£|INR|USD)?\s*[\d,]+|(?<=\s)(?:₹|\$|€|£|INR|USD)?\s*[\d,]+',
                s,
                re.IGNORECASE
            )
            generic_metric = None
            if anchor_match:
                pre_text = s[:anchor_match.start()].strip()
                words = re.findall(r'\b[a-zA-Z0-9\-_%°/]+\b', pre_text)
                if words:
                    cand_words = words[-5:]
                    stop_words = {
                        "reported", "recorded", "announced", "posted", "clocked",
                        "the", "a", "an", "for", "in", "by", "to", "during",
                        "its", "our", "their", "confirmed", "observations", "and", "that", "per"
                    }
                    clean_tokens = [w for w in cand_words if w.lower() not in stop_words]
                    if clean_tokens and len(" ".join(clean_tokens)) >= 3:
                        generic_metric = " ".join(clean_tokens)

            if unit == "percent":
                # Percentage metrics must never be conflated with aggregate currency totals
                if "customer" in s_lower:
                    metric_name = "customer revenue concentration"
                elif "fair value" in s_lower:
                    metric_name = "fair value loss on financial instruments"
                elif "real gdp" in s_lower or "gdp growth" in s_lower or "economic growth" in s_lower or "gdp is estimated" in s_lower:
                    metric_name = "real GDP growth rate"
                elif "inflation" in s_lower or "cpi" in s_lower:
                    metric_name = "CPI inflation"
                elif "ptl" in s_lower or "freight" in s_lower:
                    metric_name = "PTL freight revenue contribution"
                elif "growth" in s_lower:
                    metric_name = "revenue growth rate"
                elif "margin" in s_lower or "ebitda" in s_lower:
                    metric_name = "operating margin percentage"
                elif "share" in s_lower or "contribut" in s_lower or "portion" in s_lower:
                    metric_name = "revenue contribution share"
                elif generic_metric:
                    metric_name = generic_metric if any(k in generic_metric.lower() for k in ["rate", "margin", "share", "percent", "ratio", "efficacy"]) else generic_metric + " percentage"
                else:
                    metric_name = "percentage disclosure"
            else:
                # Absolute currency, volume, or count metrics
                if "revenue from services" in s_lower:
                    metric_name = "revenue from services"
                elif "revenue from operation" in s_lower or "revenue from contract" in s_lower:
                    metric_name = "revenue from operations"
                elif "revenue" in s_lower and any(kw in s_lower for kw in ["cr", "mn", "million", "billion", "₹", "$", "€", "inr"]):
                    metric_name = "revenue from operations"
                elif "adj" in s_lower and "ebitda" in s_lower:
                    metric_name = "adjusted EBITDA"
                elif "ebitda" in s_lower:
                    metric_name = "EBITDA"
                elif "express parcel" in s_lower or "parcel shipment" in s_lower:
                    metric_name = "express parcel shipments"
                elif "freight tonnage" in s_lower or "ptl" in s_lower:
                    metric_name = "PTL freight tonnage"
                elif "current account deficit" in s_lower or "cad" in s_lower:
                    metric_name = "current account deficit"
                elif generic_metric:
                    metric_name = generic_metric
                else:
                    metric_name = "unspecified metric"

            if metric_name and val:
                period = ""
                fy_match = re.search(r'\b(Q[1-4]\s*FY\s*\d{2,4}|Q[1-4]\s*20\d{2}-\d{2}|FY\s*\d{2,4}|20\d{2}-\d{2}|20\d{2}/\d{2}|(?:19|20)\d{2})\b', s, re.IGNORECASE)
                if fy_match:
                    period = fy_match.group(0)

                scope = ""
                if any(k in s_lower for k in ["financial", "statement", "revenue", "ebitda", "pat", "profit", "balance sheet", "basis"]):
                    if "consolidated" in s_lower:
                        scope = "consolidated"
                    elif "standalone" in s_lower:
                        scope = "standalone"

                # Generic subject resolution: local sentence proper-noun candidate or dominant chunk subject
                sentence_entities = extract_entities(s)
                subject = sentence_entities[0] if sentence_entities else default_subject

                key = (subject, metric_name, val, period, scope)
                if key in seen_keys:
                    continue
                seen_keys.add(key)

                assigned_page = chunk.page_start
                evidence_status = "EXACT_MATCH"
                score = 0.95

                if page_texts:
                    for p_num in range(chunk.page_start, chunk.page_end + 1):
                        p_content = page_texts.get(p_num, "")
                        ev_status, ev_score = verify_evidence(s, p_content)
                        if ev_status in ("EXACT_MATCH", "NORMALIZED_MATCH"):
                            assigned_page = p_num
                            evidence_status = ev_status
                            score = ev_score
                            break
                else:
                    evidence_status, score = verify_evidence(s, chunk.text)

                # Heuristic fallback trust score is set to 0.65 to reflect lower certainty vs 0.95 LLM
                heuristic_trust_score = 0.65

                fact_dict = {
                    "subject": subject,
                    "predicate": metric_name,
                    "value": val,
                    "unit": unit,
                    "time_period": period,
                    "scope": scope,
                    "qualifiers": {"extracted_via": "deterministic_heuristic"},
                    "evidence": s,
                    "evidence_status": evidence_status,
                    "extraction_method": "HEURISTIC",
                    "confidence": heuristic_trust_score
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
                        evidence_status=evidence_status,
                        extraction_method="HEURISTIC",
                        confidence=heuristic_trust_score,
                        fact_json=json.dumps(fact_dict, ensure_ascii=False)
                    )
                )

                if len(facts) >= 12:
                    break

        return facts
