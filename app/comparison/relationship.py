import json
import logging
from typing import Optional, Dict, Any
from app.extraction.llm import UnifiedLLM, clean_json_response
from app.extraction.prompts import FACT_COMPARISON_SYSTEM_PROMPT, build_comparison_prompt
from app.comparison.normalizer import (
    normalize_time_period,
    are_numerically_equivalent
)
from app.comparison.decision_pipeline import evaluate_fact_relationship
from app.database.models import FactRecord, RelationshipResult

logger = logging.getLogger(__name__)

class RelationshipClassifier:
    def __init__(self, llm: Optional[UnifiedLLM] = None):
        self.llm = llm or UnifiedLLM()
        self._llm_circuit_broken = False

    def compare_facts(
        self,
        fact_a: FactRecord,
        fact_b: FactRecord,
        doc_a_name: str = "Doc A",
        doc_b_name: str = "Doc B",
        similarity: float = 0.0
    ) -> RelationshipResult:
        """
        Compares two facts from different documents using a hybrid approach:
        1. Evaluates multi-stage structural constraints (entity compatibility, predicate match,
           time & scope analysis, numerical equivalence, calibrated composite confidence).
        2. Leverages LLM for deep contextual and nuanced linguistic explanations when available.
        3. Enforces strict entity & scope boundaries to prevent false reconciliations or contradictions.
        """
        dict_a = {
            "document_name": doc_a_name,
            "page": fact_a.page,
            "subject": fact_a.subject,
            "predicate": fact_a.predicate,
            "value": fact_a.value,
            "unit": fact_a.unit,
            "time_period": fact_a.time_period,
            "scope": fact_a.scope,
            "qualifiers": json.loads(fact_a.qualifiers_json) if fact_a.qualifiers_json else {},
            "evidence": fact_a.evidence
        }
        dict_b = {
            "document_name": doc_b_name,
            "page": fact_b.page,
            "subject": fact_b.subject,
            "predicate": fact_b.predicate,
            "value": fact_b.value,
            "unit": fact_b.unit,
            "time_period": fact_b.time_period,
            "scope": fact_b.scope,
            "qualifiers": json.loads(fact_b.qualifiers_json) if fact_b.qualifiers_json else {},
            "evidence": fact_b.evidence
        }

        # Deterministic analysis pre-checks
        norm_period_a = normalize_time_period(fact_a.time_period)
        norm_period_b = normalize_time_period(fact_b.time_period)
        is_num_equiv, equiv_reason = are_numerically_equivalent(
            fact_a.value, fact_a.unit, fact_b.value, fact_b.unit
        )

        llm_relationship = None
        llm_confidence = None
        llm_reasoning = None
        # Attempt LLM reasoning if circuit breaker is not tripped
        if not self._llm_circuit_broken:
            try:
                prompt = build_comparison_prompt(dict_a, dict_b)
                prompt += f"""
Context Clues:
- Normalized Time Period A: '{norm_period_a}', Time Period B: '{norm_period_b}'
- Numerical Equivalence Check: {is_num_equiv} ({equiv_reason or 'Values not equivalent'})
- Vector Embedding Similarity: {similarity:.3f}
"""
                raw_response = self.llm.generate(
                    prompt=prompt,
                    system_prompt=FACT_COMPARISON_SYSTEM_PROMPT,
                    json_mode=True
                )
                cleaned_json = clean_json_response(raw_response)
                parsed = json.loads(cleaned_json)
                llm_relationship = parsed.get("relationship", "").strip().upper()
                raw_conf = parsed.get("confidence")
                if isinstance(raw_conf, (int, float)):
                    llm_confidence = float(raw_conf)
                llm_reasoning = parsed.get("reasoning", "").strip()
            except Exception as e:
                logger.info(f"LLM comparison endpoint unavailable or timed out ({e}). Tripping circuit breaker for remaining pairs.")
                self._llm_circuit_broken = True

        # Run multi-stage analytical decision pipeline with LLM signals and structural guardrails
        return evaluate_fact_relationship(
            fact_a=fact_a,
            fact_b=fact_b,
            similarity=similarity,
            llm_relationship=llm_relationship,
            llm_confidence=llm_confidence,
            llm_reasoning=llm_reasoning
        )
