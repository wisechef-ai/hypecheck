from __future__ import annotations


def clamp_score(value: float, floor: int = 0, ceil: int = 100) -> int:
    return max(floor, min(ceil, int(round(value))))


def compute_trust_score(
    code_audit_score: float,
    claims_verification_score: float,
    coordination_score: float,
    clustering_score: float,
    red_flags_count: int = 0,
) -> int:
    # Formula defined in SPEC.md
    score = (
        0.30 * code_audit_score
        + 0.30 * claims_verification_score
        + 0.20 * (100 - coordination_score)
        + 0.20 * (100 - clustering_score)
    )
    score -= 5 * max(0, red_flags_count)
    return clamp_score(score)


def verdict_from_score(score: int) -> str:
    if score >= 75:
        return "LEGIT"
    if score >= 35:
        return "SUSPICIOUS"
    return "LIKELY_HYPE"
