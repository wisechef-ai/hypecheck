from src.stages import intake
from src.utils.scoring import compute_trust_score, verdict_from_score


def test_intake_x_post():
    url = "https://x.com/zostaff/status/2033209676918145231"
    result = intake.run(url)
    assert result["source_type"] == "x_post"
    assert result["metadata"]["tweet_id"] == "2033209676918145231"


def test_intake_github_repo():
    url = "https://github.com/openai/openai-python"
    result = intake.run(url)
    assert result["source_type"] == "github_repo"
    assert result["metadata"]["repo_owner"] == "openai"


def test_scoring_formula():
    score = compute_trust_score(
        code_audit_score=90,
        claims_verification_score=20,
        coordination_score=80,
        clustering_score=90,
    )
    assert score == 39
    assert verdict_from_score(score) == "SUSPICIOUS"


def test_scoring_red_flags_penalty_and_thresholds():
    base_score = compute_trust_score(
        code_audit_score=100,
        claims_verification_score=100,
        coordination_score=0,
        clustering_score=0,
    )
    penalized_score = compute_trust_score(
        code_audit_score=100,
        claims_verification_score=100,
        coordination_score=0,
        clustering_score=0,
        red_flags_count=6,
    )

    assert base_score == 100
    assert penalized_score == 70
    assert verdict_from_score(base_score) == "LEGIT"
    assert verdict_from_score(penalized_score) == "SUSPICIOUS"
    assert verdict_from_score(34) == "LIKELY_HYPE"
