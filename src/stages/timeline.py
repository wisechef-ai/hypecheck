from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from src.utils.scoring import clamp_score


def _to_dt(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def run(scrape_data: dict[str, Any]) -> dict[str, Any]:
    posts = scrape_data.get("x", {}).get("posts", [])

    enriched = []
    for post in posts:
        dt = _to_dt(post.get("created_at"))
        if dt:
            enriched.append((dt, post))

    enriched.sort(key=lambda t: t[0])

    if not enriched:
        return {
            "events": [],
            "seed_post": None,
            "amplification_window_hours": None,
            "clustering_score": 0,
            "coordination_score": 0,
        }

    events = [
        {
            "timestamp": dt.isoformat(),
            "author": post.get("author"),
            "text": post.get("text", "")[:220],
            "id": post.get("id"),
        }
        for dt, post in enriched
    ]

    first_dt, first_post = enriched[0]
    last_dt, _ = enriched[-1]
    amplification_window_hours = int((last_dt - first_dt).total_seconds() / 3600)

    by_hour = Counter(dt.strftime("%Y-%m-%dT%H") for dt, _ in enriched)
    max_per_hour = max(by_hour.values())
    total = len(enriched)
    concentration = max_per_hour / total

    # Elevated when many posts occur in narrow windows.
    clustering_score = clamp_score(concentration * 100)

    # Coordination signal also considers tight overall window.
    window_signal = 30 if amplification_window_hours <= 48 else 15 if amplification_window_hours <= 120 else 0
    coordination_score = clamp_score(clustering_score * 0.7 + window_signal)

    return {
        "events": events,
        "seed_post": {
            "id": first_post.get("id"),
            "author": first_post.get("author"),
            "timestamp": first_dt.isoformat(),
            "text": first_post.get("text", "")[:220],
        },
        "amplification_window_hours": amplification_window_hours,
        "clustering_score": clustering_score,
        "coordination_score": coordination_score,
    }
