from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.utils.llm import LLMSynthesizer
from src.utils.scoring import compute_trust_score, verdict_from_score


def _fallback_summary(verdict: str, trust_score: int, stages: dict[str, Any]) -> str:
    claims = stages["claims"]
    code = stages["code_audit"]
    network = stages["network"]
    timeline = stages["timeline"]

    return (
        f"Verdict: {verdict} (trust score {trust_score}/100). "
        f"Code risk is {code.get('risk')} and claims verification score is {claims.get('claims_verified')}. "
        f"Coordination likelihood is {network.get('coordination_likelihood')} with clustering score {timeline.get('clustering_score')}. "
        f"Primary discrepancies: {', '.join(claims.get('discrepancies', [])[:2]) or 'none observed'}."
    )


def run(
    url: str,
    intake: dict[str, Any],
    scrape: dict[str, Any],
    network: dict[str, Any],
    code_audit: dict[str, Any],
    claims: dict[str, Any],
    timeline: dict[str, Any],
) -> dict[str, Any]:
    trust_score = compute_trust_score(
        code_audit_score=code_audit.get("score", 50),
        claims_verification_score=claims.get("claims_verified", 50),
        coordination_score=max(network.get("coordination_likelihood", 0), timeline.get("coordination_score", 0)),
        clustering_score=timeline.get("clustering_score", 0),
    )

    verdict = verdict_from_score(trust_score)

    stages = {
        "intake": intake,
        "scrape": scrape,
        "network": network,
        "code_audit": code_audit,
        "claims": claims,
        "timeline": timeline,
    }

    payload = {
        "url": url,
        "verdict": verdict,
        "trust_score": trust_score,
        "stages": stages,
    }

    llm = LLMSynthesizer()
    summary = llm.summarize(payload) if llm.enabled else None
    if not summary:
        summary = _fallback_summary(verdict, trust_score, stages)

    evidence = []
    evidence.extend(code_audit.get("findings", []))
    evidence.extend(claims.get("evidence", []))
    if network.get("shared_groups"):
        evidence.append(f"Shared group tags in bios: {', '.join(network['shared_groups'])}")

    return {
        "url": url,
        "verdict": verdict,
        "trust_score": trust_score,
        "summary": summary,
        "stages": {
            "code_audit": {
                "risk": code_audit.get("risk"),
                "score": code_audit.get("score"),
                "findings": code_audit.get("findings", []),
            },
            "claims": {
                "score": claims.get("claims_verified"),
                "claims": claims.get("claims", []),
                "discrepancies": claims.get("discrepancies", []),
            },
            "network": {
                "coordination": network.get("coordination_likelihood"),
                "shared_groups": network.get("shared_groups", []),
            },
            "timeline": {
                "clustering": timeline.get("clustering_score"),
                "seed_post": timeline.get("seed_post"),
                "amplification_window_hours": timeline.get("amplification_window_hours"),
            },
        },
        "evidence": evidence,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
