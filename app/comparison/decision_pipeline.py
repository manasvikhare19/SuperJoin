import re
import logging
from typing import Dict, Any, Tuple, Optional
from app.comparison.normalizer import (
    normalize_time_period,
    extract_numeric_value,
    are_numerically_equivalent
)
from app.database.models import FactRecord, RelationshipResult, ConfidenceBreakdown

logger = logging.getLogger(__name__)

# Generic legal and corporate entity suffixes to strip during normalization
LEGAL_SUFFIXES = {
    "limited", "ltd", "corp", "corporation", "inc", "co", "company",
    "plc", "llc", "sa", "gmbh", "pvt", "holdings", "group"
}

def check_acronym_match(s1: str, s2: str) -> bool:
    """
    Checks if s1 is an acronym/abbreviation of s2 or vice versa.
    e.g. 'RBI' vs 'Reserve Bank of India', 'IMF' vs 'International Monetary Fund',
    'SEBI' vs 'Securities and Exchange Board of India'.
    """
    for a, b in [(s1, s2), (s2, s1)]:
        cleaned_a = re.sub(r'[^a-zA-Z]', '', a).upper()
        if len(cleaned_a) < 2:
            continue
        words = [w for w in re.split(r'[\s\-_]+', b) if w and w.lower() not in {"of", "the", "and", "in", "for", "at", "on", "to"}]
        if len(words) >= 2:
            initials = "".join(w[0].upper() for w in words if w)
            if cleaned_a == initials:
                return True
        all_words = [w for w in re.split(r'[\s\-_]+', b) if w]
        if len(all_words) >= 2:
            all_initials = "".join(w[0].upper() for w in all_words if w)
            if cleaned_a == all_initials:
                return True
    return False

def check_entity_compatibility(subj_a: str, subj_b: str, embedder: Optional[Any] = None) -> Tuple[bool, float, str]:
    """
    Evaluates whether two subjects refer to the same or compatible entity.
    Zero hardcoded entity lists: uses legal designation stripping, acronym matching,
    token overlap, and dense vector embedding similarity.
    Returns (is_compatible, score, explanation).
    """
    sa = (subj_a or "").strip().lower()
    sb = (subj_b or "").strip().lower()

    if not sa or not sb:
        return True, 0.5, "Incomplete entity names"

    if sa == sb:
        return True, 1.0, f"Exact entity match ('{subj_a}')"

    # Acronym / Abbreviation check (e.g. RBI vs Reserve Bank of India)
    if check_acronym_match(subj_a, subj_b):
        return True, 0.92, f"Acronym match ('{subj_a}' ~ '{subj_b}')"

    # Legal designation stripping (e.g. Delhivery vs Delhivery Limited)
    tokens_a = [w for w in re.findall(r'\w+', sa) if w not in LEGAL_SUFFIXES]
    tokens_b = [w for w in re.findall(r'\w+', sb) if w not in LEGAL_SUFFIXES]

    if tokens_a and tokens_b and tokens_a == tokens_b:
        return True, 0.95, f"Entity match excluding legal designations ('{subj_a}' ~ '{subj_b}')"

    # Token overlap check on non-legal tokens
    set_a, set_b = set(tokens_a), set(tokens_b)
    if set_a and set_b:
        intersection = set_a.intersection(set_b)
        min_len = min(len(set_a), len(set_b))
        if min_len > 0:
            overlap = len(intersection) / min_len
            if overlap >= 0.7:
                return True, 0.85, f"High entity token overlap ({subj_a} ~ {subj_b})"
            elif overlap > 0:
                return True, 0.60, f"Partial entity token overlap ({subj_a} ~ {subj_b})"

    # Dense vector embedding similarity check
    if embedder is None:
        try:
            from app.embeddings.embedder import FactEmbedder
            embedder = FactEmbedder()
        except Exception:
            embedder = None

    if embedder is not None:
        try:
            vecs = embedder.embed_texts([subj_a, subj_b])
            import numpy as np
            sim = float(np.dot(vecs[0], vecs[1]))
            if sim >= 0.85:
                return True, round(sim, 3), f"High semantic embedding similarity ({sim:.2f}) between entities ('{subj_a}' ~ '{subj_b}')"
            elif sim <= 0.35:
                return False, round(sim, 3), f"Distinct entities by semantic embedding distance ({sim:.2f}): '{subj_a}' vs '{subj_b}'"
        except Exception as e:
            logger.debug(f"Embedding check error in entity compatibility: {e}")

    # Clear distinction
    return False, 0.10, f"Distinct entities ('{subj_a}' vs '{subj_b}')"

def check_predicate_compatibility(pred_a: str, pred_b: str, embedder: Optional[Any] = None) -> Tuple[bool, float, str]:
    """
    Evaluates whether two predicates measure the same economic/financial metric.
    Zero hardcoded domain lists: uses normalized token overlap and dense MiniLM semantic similarity.
    Returns (is_compatible, score, explanation).
    """
    pa = (pred_a or "").strip().lower()
    pb = (pred_b or "").strip().lower()

    if not pa or not pb:
        return False, 0.2, "Incomplete predicate names"

    if pa == pb:
        return True, 1.0, f"Exact predicate match ('{pred_a}')"

    # Token overlap check on informative content tokens
    stop_words = {"from", "of", "in", "and", "the", "on", "for", "to", "at", "by", "rate", "basis", "level", "total"}
    tokens_a = set(re.findall(r'\w+', pa)) - stop_words
    tokens_b = set(re.findall(r'\w+', pb)) - stop_words

    overlap = 0.0
    if tokens_a and tokens_b:
        intersection = tokens_a.intersection(tokens_b)
        max_len = max(len(tokens_a), len(tokens_b))
        overlap = len(intersection) / max_len if max_len > 0 else 0.0
        if overlap >= 0.5:
            return True, 0.85, f"High predicate token overlap ({pred_a} ~ {pred_b})"

    # Dense vector embedding similarity check
    if embedder is None:
        try:
            from app.embeddings.embedder import FactEmbedder
            embedder = FactEmbedder()
        except Exception:
            embedder = None

    if embedder is not None:
        try:
            vecs = embedder.embed_texts([pred_a, pred_b])
            import numpy as np
            sim = float(np.dot(vecs[0], vecs[1]))
            if sim >= 0.65:
                return True, round(sim, 3), f"High semantic predicate similarity ({sim:.2f}) between metrics ('{pred_a}' ~ '{pred_b}')"
            elif sim < 0.35 and overlap == 0:
                return False, round(sim, 3), f"Incompatible metrics ('{pred_a}' vs '{pred_b}')"
        except Exception as e:
            logger.debug(f"Embedding check error in predicate compatibility: {e}")

    if overlap > 0.25:
        return True, 0.60, f"Moderate predicate overlap ({pred_a} ~ {pred_b})"

    return False, 0.15, f"Incompatible metrics ('{pred_a}' vs '{pred_b}')"

def analyze_time_relationship(period_a: str, period_b: str) -> Tuple[str, float, str]:
    """
    Classifies temporal relationship:
    - 'IDENTICAL': Same fiscal period
    - 'SUBSET': One is a quarterly component of the other's full year
    - 'SEQUENTIAL': Consecutive periods (e.g. FY23 vs FY24)
    - 'UNKNOWN': Ambiguous or undefined
    """
    norm_a = normalize_time_period(period_a)
    norm_b = normalize_time_period(period_b)

    if not norm_a or not norm_b:
        return "UNKNOWN", 0.5, "Unspecified time periods"

    if norm_a == norm_b:
        return "IDENTICAL", 1.0, f"Identical time period ({norm_a})"

    # Check if one is a quarter of the same year
    is_q_a = norm_a.startswith("Q") and "-" in norm_a
    is_q_b = norm_b.startswith("Q") and "-" in norm_b

    if is_q_a and not is_q_b:
        q_year = norm_a.split("-")[1]
        if q_year == norm_b:
            return "SUBSET", 0.95, f"{norm_a} is a quarterly subset of {norm_b}"
    elif is_q_b and not is_q_a:
        q_year = norm_b.split("-")[1]
        if q_year == norm_a:
            return "SUBSET", 0.95, f"{norm_b} is a quarterly subset of {norm_a}"

    return "SEQUENTIAL", 0.85, f"Distinct time periods ({norm_a} vs {norm_b})"

def analyze_scope_relationship(scope_a: str, scope_b: str) -> Tuple[str, float, str]:
    """
    Classifies scope relationship (Consolidated vs Standalone vs Headline).
    """
    sa = (scope_a or "").strip().lower()
    sb = (scope_b or "").strip().lower()

    if not sa and not sb:
        return "DEFAULT_IDENTICAL", 0.9, "Both report under standard default scope"

    if sa == sb:
        return "IDENTICAL", 1.0, f"Matching scope ('{scope_a}')"

    scopes = {sa, sb}
    if "consolidated" in scopes and "standalone" in scopes:
        return "SCOPE_DIVERGENCE", 0.95, "Consolidated (group perimeter) vs Standalone (parent legal entity)"

    return "DIFFERENT", 0.75, f"Different scopes ('{scope_a}' vs '{scope_b}')"

def evaluate_fact_relationship(
    fact_a: FactRecord,
    fact_b: FactRecord,
    similarity: float = 0.0,
    llm_relationship: Optional[str] = None,
    llm_confidence: Optional[float] = None,
    llm_reasoning: Optional[str] = None,
    embedder: Optional[Any] = None
) -> RelationshipResult:
    """
    Executes the 6-stage analytical decision pipeline to determine the cross-document
    relationship between Fact A and Fact B with calibrated composite confidence,
    LLM primary classification, structural sanity guardrails, and explainability.
    """
    # ----------------------------------------------------
    # Stage 1: Entity Compatibility
    # ----------------------------------------------------
    ent_ok, ent_score, ent_expl = check_entity_compatibility(fact_a.subject, fact_b.subject, embedder=embedder)
    if not ent_ok:
        breakdown = {
            "semantic_similarity": round(similarity, 3),
            "entity_match": round(ent_score, 3),
            "predicate_match": 0.1,
            "time_compatibility": 0.5,
            "scope_compatibility": 0.5,
            "numerical_compatibility": 0.1,
            "composite_score": round(0.30 * similarity + 0.20 * ent_score + 0.05, 3)
        }
        why = f"Entities are fundamentally distinct: '{fact_a.subject}' vs '{fact_b.subject}'. No cross-document relation applies."
        if llm_relationship and llm_relationship.upper() not in ("UNRELATED", "UNKNOWN"):
            why = f"Structural guardrail overrule: LLM suggested '{llm_relationship}', but entities '{fact_a.subject}' and '{fact_b.subject}' are distinct (score: {ent_score:.2f}). Overruled to UNRELATED."
        return RelationshipResult(
            relationship="UNRELATED",
            confidence=0.95,
            reasoning=why,
            why_explanation=f"Fact A refers to entity '{fact_a.subject}' whereas Fact B refers to entity '{fact_b.subject}'.",
            why_not_explanation="Rejected CORROBORATES, CONTRADICTS, and RECONCILES: Facts from unrelated corporate or national entities cannot corroborate, contradict, or reconcile each other.",
            breakdown=breakdown
        )

    # ----------------------------------------------------
    # Stage 2: Predicate Semantic Match
    # ----------------------------------------------------
    pred_ok, pred_score, pred_expl = check_predicate_compatibility(fact_a.predicate, fact_b.predicate, embedder=embedder)
    if not pred_ok and similarity < 0.65:
        breakdown = {
            "semantic_similarity": round(similarity, 3),
            "entity_match": round(ent_score, 3),
            "predicate_match": round(pred_score, 3),
            "time_compatibility": 0.5,
            "scope_compatibility": 0.5,
            "numerical_compatibility": 0.1,
            "composite_score": round(0.30 * similarity + 0.20 * ent_score + 0.20 * pred_score + 0.10, 3)
        }
        why = f"Metrics measure distinct operational phenomena: '{fact_a.predicate}' vs '{fact_b.predicate}'."
        return RelationshipResult(
            relationship="UNRELATED",
            confidence=0.90,
            reasoning=why,
            why_explanation=why,
            why_not_explanation="Rejected CORROBORATES and CONTRADICTS: Independent operational metrics do not validate or invalidate each other.",
            breakdown=breakdown
        )

    # ----------------------------------------------------
    # Stage 3: Time & Scope Analysis
    # ----------------------------------------------------
    time_rel, time_score, time_expl = analyze_time_relationship(fact_a.time_period, fact_b.time_period)
    scope_rel, scope_score, scope_expl = analyze_scope_relationship(fact_a.scope, fact_b.scope)

    # ----------------------------------------------------
    # Stage 4: Numerical Equivalence
    # ----------------------------------------------------
    is_num_equiv, num_expl = are_numerically_equivalent(
        fact_a.value, fact_a.unit, fact_b.value, fact_b.unit
    )
    num_score = 1.0 if is_num_equiv else 0.40

    # ----------------------------------------------------
    # Stage 5: Calibrated Composite Confidence Calculation
    # ----------------------------------------------------
    composite_confidence = (
        0.30 * min(1.0, max(0.0, similarity)) +
        0.20 * ent_score +
        0.20 * pred_score +
        0.15 * time_score +
        0.10 * scope_score +
        0.05 * num_score
    )
    composite_confidence = round(min(0.99, max(0.50, composite_confidence)), 3)

    breakdown = {
        "semantic_similarity": round(similarity, 3),
        "entity_match": round(ent_score, 3),
        "predicate_match": round(pred_score, 3),
        "time_compatibility": round(time_score, 3),
        "scope_compatibility": round(scope_score, 3),
        "numerical_compatibility": round(num_score, 3),
        "composite_score": composite_confidence
    }

    # ----------------------------------------------------
    # Stage 6: Relationship Decision & Explainability (LLM Primacy with Structural Guardrails)
    # ----------------------------------------------------
    clean_llm_rel = (llm_relationship or "").strip().upper()

    # Guardrail Check 1: Temporal Subset or Scope Divergence falsely called CONTRADICTION by LLM
    if clean_llm_rel in ("CONTRADICTS", "LIKELY_CONTRADICTION"):
        if time_rel == "SUBSET":
            why = (
                f"Structural guardrail reconciliation: LLM flagged contradiction on numerical difference, "
                f"but temporal analysis proves granularity subset: {time_expl}."
            )
            why_not = (
                "Rejected CONTRADICTS: A single quarter's financial results are an additive component of "
                "the annual aggregate, not a contradictory claim. Rejected CORROBORATES: Quarterly and annual totals represent different operational durations."
            )
            return RelationshipResult(
                relationship="RECONCILES",
                confidence=composite_confidence,
                reasoning=llm_reasoning or why,
                why_explanation=why,
                why_not_explanation=why_not,
                breakdown=breakdown
            )
        elif scope_rel == "SCOPE_DIVERGENCE":
            why = (
                f"Structural guardrail reconciliation: LLM flagged contradiction on differing figures, "
                f"but scope analysis proves perimeter divergence: {scope_expl}."
            )
            why_not = (
                "Rejected CONTRADICTS: Standalone statements reflect only the legal parent, while consolidated "
                "statements incorporate subsidiaries, joint ventures, and eliminations. Rejected CORROBORATES: Different reporting perimeters."
            )
            return RelationshipResult(
                relationship="RECONCILES",
                confidence=composite_confidence,
                reasoning=llm_reasoning or why,
                why_explanation=why,
                why_not_explanation=why_not,
                breakdown=breakdown
            )

    # Guardrail Check 2: Identical Time & Scope with distinct numbers falsely called CORROBORATES by LLM
    if clean_llm_rel == "CORROBORATES":
        if time_rel in ("IDENTICAL", "UNKNOWN") and scope_rel in ("IDENTICAL", "DEFAULT_IDENTICAL") and not is_num_equiv:
            why = (
                f"Structural guardrail overrule: LLM suggested CORROBORATES, but values ({fact_a.value} {fact_a.unit} vs "
                f"{fact_b.value} {fact_b.unit}) differ for identical period '{normalize_time_period(fact_a.time_period)}' and scope."
            )
            why_not = "Rejected CORROBORATES: Figures are mathematically irreconcilable."
            return RelationshipResult(
                relationship="CONTRADICTS",
                confidence=composite_confidence,
                reasoning=llm_reasoning or why,
                why_explanation=why,
                why_not_explanation=why_not,
                breakdown=breakdown
            )

    # Guardrail Check 3: If LLM gave a recognized relationship that passed all guardrails: ADOPT AS PRIMARY
    if clean_llm_rel in ("CORROBORATES", "CONTRADICTS", "LIKELY_CONTRADICTION", "RECONCILES", "UNRELATED", "NEEDS_REVIEW"):
        final_conf = round(max(composite_confidence, float(llm_confidence) if llm_confidence else 0.85), 3)
        why = llm_reasoning or f"Classified as {clean_llm_rel} based on comprehensive cross-document semantic analysis."
        if clean_llm_rel == "CORROBORATES":
            why_not = "Rejected CONTRADICTS: Figures and reporting metrics agree under normalized scale."
        elif clean_llm_rel in ("CONTRADICTS", "LIKELY_CONTRADICTION"):
            why_not = "Rejected CORROBORATES: Figures are materially divergent under identical reporting conditions."
        elif clean_llm_rel == "RECONCILES":
            why_not = "Rejected CONTRADICTS: Apparent numerical difference is explained by differing context, period, or scope."
        else:
            why_not = f"Alternative relationships rejected due to entity alignment score {ent_score:.2f} and metric score {pred_score:.2f}."

        return RelationshipResult(
            relationship=clean_llm_rel,
            confidence=final_conf,
            reasoning=llm_reasoning or why,
            why_explanation=why,
            why_not_explanation=why_not,
            breakdown=breakdown
        )

    # ----------------------------------------------------
    # Fallback / Deterministic Decision Modes (when LLM is offline or uninformative)
    # ----------------------------------------------------

    # Case A: Same Time & Same Scope
    if time_rel in ("IDENTICAL", "UNKNOWN") and scope_rel in ("IDENTICAL", "DEFAULT_IDENTICAL"):
        if is_num_equiv:
            why = (
                f"Both documents report concordant metrics for {fact_a.subject} ({fact_a.predicate}). "
                f"Fact A ({fact_a.value} {fact_a.unit}) matches Fact B ({fact_b.value} {fact_b.unit}) "
                f"under normalized scale for period '{normalize_time_period(fact_a.time_period)}'."
            )
            why_not = (
                "Rejected CONTRADICTS: Values match within corporate reporting rounding tolerances. "
                "Rejected RECONCILES: No contextual, temporal, or scope discrepancy exists to reconcile."
            )
            return RelationshipResult(
                relationship="CORROBORATES",
                confidence=composite_confidence,
                reasoning=llm_reasoning or why,
                why_explanation=why,
                why_not_explanation=why_not,
                breakdown=breakdown
            )
        else:
            # Check for vintage revision clues in evidence or qualifiers
            combined_ev = (fact_a.evidence + " " + fact_b.evidence).lower()
            is_vintage = any(v in combined_ev for v in ["advance estimate", "provisional estimate", "revised estimate", "first advance"])
            
            if is_vintage:
                why = (
                    f"Both documents evaluate {fact_a.subject} {fact_a.predicate} for {fact_a.time_period}, "
                    f"but report differing figures ({fact_a.value} vs {fact_b.value}) representing successive "
                    f"statistical revisions (e.g. Advance Estimate vs Provisional Estimate)."
                )
                why_not = (
                    "Rejected CORROBORATES: Figures are numerically distinct. "
                    "Classified as LIKELY_CONTRADICTION / VINTAGE_RECONCILIATION because the discrepancy is due to updated official statistical releases over time."
                )
                return RelationshipResult(
                    relationship="LIKELY_CONTRADICTION",
                    confidence=composite_confidence,
                    reasoning=llm_reasoning or why,
                    why_explanation=why,
                    why_not_explanation=why_not,
                    breakdown=breakdown
                )
            else:
                why = (
                    f"Direct empirical contradiction: Fact A reports {fact_a.value} {fact_a.unit} whereas "
                    f"Fact B reports {fact_b.value} {fact_b.unit} for the exact same subject ({fact_a.subject}), "
                    f"predicate ({fact_a.predicate}), time period ({normalize_time_period(fact_a.time_period)}), and scope."
                )
                why_not = (
                    "Rejected CORROBORATES: Figures are mathematically irreconcilable. "
                    "Rejected RECONCILES: Time horizon and perimeter are identical; there is no contextual parameter explaining the numerical clash."
                )
                return RelationshipResult(
                    relationship="CONTRADICTS",
                    confidence=composite_confidence,
                    reasoning=llm_reasoning or why,
                    why_explanation=why,
                    why_not_explanation=why_not,
                    breakdown=breakdown
                )

    # Case B: Temporal Subset (Quarter vs Full Year)
    if time_rel == "SUBSET":
        why = (
            f"The numerical difference between {fact_a.value} {fact_a.unit} and {fact_b.value} {fact_b.unit} "
            f"is fully reconciled by temporal granularity: {time_expl}."
        )
        why_not = (
            "Rejected CONTRADICTS: A single quarter's financial results are an additive component of "
            "the annual aggregate, not a contradictory claim. "
            "Rejected CORROBORATES: Quarterly and annual totals represent different operational durations."
        )
        return RelationshipResult(
            relationship="RECONCILES",
            confidence=composite_confidence,
            reasoning=llm_reasoning or why,
            why_explanation=why,
            why_not_explanation=why_not,
            breakdown=breakdown
        )

    # Case C: Scope Divergence (Consolidated vs Standalone)
    if scope_rel == "SCOPE_DIVERGENCE":
        why = (
            f"The apparent discrepancy ({fact_a.value} vs {fact_b.value}) is reconciled by reporting perimeter: "
            f"{scope_expl}."
        )
        why_not = (
            "Rejected CONTRADICTS: Standalone statements reflect only the legal parent, while consolidated "
            "statements incorporate subsidiaries, joint ventures, and eliminations. "
            "Rejected CORROBORATES: The perimeters measure different operational boundaries."
        )
        return RelationshipResult(
            relationship="RECONCILES",
            confidence=composite_confidence,
            reasoning=llm_reasoning or why,
            why_explanation=why,
            why_not_explanation=why_not,
            breakdown=breakdown
        )

    # Case D: Sequential / Multi-Year Progression
    if time_rel == "SEQUENTIAL":
        why = (
            f"Metrics represent multi-period historical evolution for {fact_a.subject} ({fact_a.predicate}): "
            f"period {normalize_time_period(fact_a.time_period)} ({fact_a.value} {fact_a.unit}) vs "
            f"period {normalize_time_period(fact_b.time_period)} ({fact_b.value} {fact_b.unit})."
        )
        why_not = (
            "Rejected CONTRADICTS: Economic and business figures naturally fluctuate across fiscal cycles. "
            "Classified as RECONCILES to capture inter-temporal continuity."
        )
        return RelationshipResult(
            relationship="RECONCILES",
            confidence=composite_confidence,
            reasoning=llm_reasoning or why,
            why_explanation=why,
            why_not_explanation=why_not,
            breakdown=breakdown
        )

    # Fallback
    return RelationshipResult(
        relationship="NEEDS_REVIEW",
        confidence=0.60,
        reasoning="Insufficient structural constraints to deterministically resolve relationship.",
        why_explanation="Entities and predicates are loosely aligned, but time or scope dimensions require manual inspection.",
        why_not_explanation="Rejected automatic CORROBORATES / CONTRADICTS due to ambiguous reporting context.",
        breakdown=breakdown
    )
