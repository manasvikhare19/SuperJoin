import json
import logging
from typing import Optional, Dict, Any
from app.extraction.llm import UnifiedLLM, clean_json_response
from app.extraction.prompts import FACT_COMPARISON_SYSTEM_PROMPT, build_comparison_prompt
from app.comparison.normalizer import (
    normalize_time_period,
    are_numerically_equivalent
)
from app.database.models import FactRecord, RelationshipResult

logger = logging.getLogger(__name__)

class RelationshipClassifier:
    def __init__(self, llm: Optional[UnifiedLLM] = None):
        self.llm = llm or UnifiedLLM()

    def compare_facts(
        self,
        fact_a: FactRecord,
        fact_b: FactRecord,
        doc_a_name: str = "Doc A",
        doc_b_name: str = "Doc B",
        similarity: float = 0.0
    ) -> RelationshipResult:
        """
        Compares two facts from different documents and classifies their relationship.
        Incorporates deterministic normalization signals into the analytical reasoning.
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

        prompt = build_comparison_prompt(dict_a, dict_b)

        # Append deterministic context clues to assist the LLM reasoning
        prompt += f"""
Context Clues:
- Normalized Time Period A: '{norm_period_a}', Time Period B: '{norm_period_b}'
- Numerical Equivalence Check: {is_num_equiv} ({equiv_reason or 'Values not equivalent'})
- Vector Embedding Similarity: {similarity:.3f}
"""

        try:
            raw_response = self.llm.generate(
                prompt=prompt,
                system_prompt=FACT_COMPARISON_SYSTEM_PROMPT,
                json_mode=True
            )
            cleaned_json = clean_json_response(raw_response)
            parsed = json.loads(cleaned_json)

            rel_str = parsed.get("relationship", "UNRELATED").upper()
            if rel_str not in ["CORROBORATES", "CONTRADICTS", "RECONCILES", "UNRELATED"]:
                rel_str = "UNRELATED"

            confidence = float(parsed.get("confidence", 0.75))
            reasoning = parsed.get("reasoning", "").strip()

            return RelationshipResult(
                relationship=rel_str,
                confidence=min(1.0, max(0.0, confidence)),
                reasoning=reasoning
            )

        except Exception as e:
            logger.warning(f"LLM comparison encountered error: {e}. Falling back to rule-guided classification.")
            
            # Rule-guided fallback if LLM is unreachable
            if is_num_equiv and norm_period_a == norm_period_b and norm_period_a != "":
                return RelationshipResult(
                    relationship="CORROBORATES",
                    confidence=0.88,
                    reasoning=f"Both documents report equivalent metrics ({equiv_reason}) for the matching period {norm_period_a}."
                )
            elif norm_period_a != norm_period_b and norm_period_a and norm_period_b:
                return RelationshipResult(
                    relationship="RECONCILES",
                    confidence=0.85,
                    reasoning=f"The apparent difference in reported values ({fact_a.value} vs {fact_b.value}) is explained by differing time periods ({norm_period_a} vs {norm_period_b})."
                )
            elif fact_a.scope.lower() != fact_b.scope.lower() and fact_a.scope and fact_b.scope:
                return RelationshipResult(
                    relationship="RECONCILES",
                    confidence=0.84,
                    reasoning=f"The differing figures reflect reporting scope differences: Fact A refers to '{fact_a.scope}' while Fact B refers to '{fact_b.scope}'."
                )
            elif similarity > 0.85 and not is_num_equiv and norm_period_a == norm_period_b:
                return RelationshipResult(
                    relationship="CONTRADICTS",
                    confidence=0.80,
                    reasoning=f"Both facts refer to the same metric and period ({norm_period_a}), but report incompatible values ({fact_a.value} vs {fact_b.value})."
                )
            else:
                return RelationshipResult(
                    relationship="UNRELATED",
                    confidence=0.60,
                    reasoning="The facts do not exhibit a direct corroborative, contradictory, or reconcilable relationship."
                )
