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

# Known entity aliases for financial & macroeconomic corpora
ENTITY_CLUSTERS = [
    {"delhivery", "delhivery limited", "delhivery ltd", "the company", "management"},
    {"india", "indian economy", "republic of india", "government of india", "national economy"},
    {"rbi", "reserve bank of india", "central bank", "monetary policy committee", "mpc"},
    {"mospi", "nsso", "cso", "ministry of statistics and programme implementation", "national statistical office"},
    {"fed", "federal reserve", "us federal reserve"},
]

PREDICATE_SYNONYMS = [
    {"revenue from operations", "revenue from services", "total revenue", "revenue", "operating revenue", "turnover"},
    {"real gdp growth", "gdp growth rate", "economic growth", "growth in real gdp", "gdp growth", "real gross domestic product"},
    {"ebitda", "adjusted ebitda", "operating ebitda"},
    {"pat", "profit after tax", "net profit", "net loss", "loss after tax"},
    {"inflation", "cpi inflation", "headline inflation", "consumer price index"},
]

def check_entity_compatibility(subj_a: str, subj_b: str) -> Tuple[bool, float, str]:
    """
    Evaluates whether two subjects refer to the same or compatible entity.
    Returns (is_compatible, score, explanation).
    """
    sa = subj_a.strip().lower()
    sb = subj_b.strip().lower()

    if not sa or not sb:
        return True, 0.5, "Incomplete entity names"

    if sa == sb:
        return True, 1.0, f"Exact entity match ('{subj_a}')"

    # Check clusters
    for cluster in ENTITY_CLUSTERS:
        if any(alias in sa for alias in cluster) and any(alias in sb for alias in cluster):
            return True, 0.95, f"Entity alias match in cluster ({subj_a} ~ {subj_b})"

    # Token overlap check
    tokens_a = set(re.findall(r'\w+', sa)) - {"the", "ltd", "limited", "corp", "inc", "co"}
    tokens_b = set(re.findall(r'\w+', sb)) - {"the", "ltd", "limited", "corp", "inc", "co"}

    if tokens_a and tokens_b:
        intersection = tokens_a.intersection(tokens_b)
        overlap = len(intersection) / min(len(tokens_a), len(tokens_b))
        if overlap >= 0.7:
            return True, 0.85, f"High entity token overlap ({subj_a} ~ {subj_b})"
        elif overlap > 0:
            return True, 0.60, f"Partial entity token overlap ({subj_a} ~ {subj_b})"

    # Clear distinction
    return False, 0.1, f"Distinct entities ('{subj_a}' vs '{subj_b}')"

def check_predicate_compatibility(pred_a: str, pred_b: str) -> Tuple[bool, float, str]:
    """
    Evaluates whether two predicates measure the same economic/financial metric.
    Returns (is_compatible, score, explanation).
    """
    pa = pred_a.strip().lower()
    pb = pred_b.strip().lower()

    if not pa or not pb:
        return False, 0.2, "Incomplete predicate names"

    if pa == pb:
        return True, 1.0, f"Exact predicate match ('{pred_a}')"

    for syn_group in PREDICATE_SYNONYMS:
        if any(syn in pa for syn in syn_group) and any(syn in pb for syn in syn_group):
            return True, 0.90, f"Synonymous metric group ('{pred_a}' ~ '{pred_b}')"

    tokens_a = set(re.findall(r'\w+', pa)) - {"from", "of", "in", "and", "the"}
    tokens_b = set(re.findall(r'\w+', pb)) - {"from", "of", "in", "and", "the"}

    if tokens_a and tokens_b:
        intersection = tokens_a.intersection(tokens_b)
        overlap = len(intersection) / max(len(tokens_a), len(tokens_b))
        if overlap >= 0.6:
            return True, 0.80, f"High predicate overlap ({pred_a} ~ {pred_b})"
        elif overlap > 0.3:
            return True, 0.55, f"Moderate predicate overlap ({pred_a} ~ {pred_b})"

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
    llm_reasoning: Optional[str] = None
) -> RelationshipResult:
    """
    Executes the 6-stage analytical decision pipeline to determine the cross-document
    relationship between Fact A and Fact B with calibrated composite confidence
    and explicit explainability (Why and Why Not).
    """
    # ----------------------------------------------------
    # Stage 1: Entity Compatibility
    # ----------------------------------------------------
    ent_ok, ent_score, ent_expl = check_entity_compatibility(fact_a.subject, fact_b.subject)
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
        return RelationshipResult(
            relationship="UNRELATED",
            confidence=0.95,
            reasoning=f"Entities are fundamentally distinct: '{fact_a.subject}' vs '{fact_b.subject}'. No cross-document relation applies.",
            why_explanation=f"Fact A refers to entity '{fact_a.subject}' whereas Fact B refers to entity '{fact_b.subject}'.",
            why_not_explanation="Rejected CORROBORATES, CONTRADICTS, and RECONCILES: Facts from unrelated corporate or national entities cannot corroborate, contradict, or reconcile each other.",
            breakdown=breakdown
        )

    # ----------------------------------------------------
    # Stage 2: Predicate Semantic Match
    # ----------------------------------------------------
    pred_ok, pred_score, pred_expl = check_predicate_compatibility(fact_a.predicate, fact_b.predicate)
    if not pred_ok and similarity < 0.70:
        breakdown = {
            "semantic_similarity": round(similarity, 3),
            "entity_match": round(ent_score, 3),
            "predicate_match": round(pred_score, 3),
            "time_compatibility": 0.5,
            "scope_compatibility": 0.5,
            "numerical_compatibility": 0.1,
            "composite_score": round(0.30 * similarity + 0.20 * ent_score + 0.20 * pred_score + 0.10, 3)
        }
        return RelationshipResult(
            relationship="UNRELATED",
            confidence=0.90,
            reasoning=f"Metrics measure distinct operational phenomena: '{fact_a.predicate}' vs '{fact_b.predicate}'.",
            why_explanation=f"Fact A reports on '{fact_a.predicate}' while Fact B reports on '{fact_b.predicate}'.",
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
    # Stage 6: Relationship Decision & Explainability (Why / Why Not)
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
