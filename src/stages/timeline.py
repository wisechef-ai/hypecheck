from __future__ import annotations

from collections import Counter
from datetime import datetime
import re
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

    # Find the densest 120h window (sliding) — not always from the first post
    best_window_authors: set[str] = set()
    best_window_start = first_dt
    for i, (dt_i, _) in enumerate(enriched):
        window_end = dt_i.timestamp() + (120 * 3600)
        authors_in_window: set[str] = set()
        for dt_j, post_j in enriched:
            if dt_i.timestamp() <= dt_j.timestamp() <= window_end and post_j.get("author"):
                authors_in_window.add(str(post_j["author"]).lower())
        if len(authors_in_window) > len(best_window_authors):
            best_window_authors = authors_in_window
            best_window_start = dt_i

    unique_authors_120h = len(best_window_authors)

    # Also find the densest 48h window for tighter coordination detection
    best_48h_authors: set[str] = set()
    for i, (dt_i, _) in enumerate(enriched):
        window_end = dt_i.timestamp() + (48 * 3600)
        authors_in_window: set[str] = set()
        for dt_j, post_j in enriched:
            if dt_i.timestamp() <= dt_j.timestamp() <= window_end and post_j.get("author"):
                authors_in_window.add(str(post_j["author"]).lower())
        if len(authors_in_window) > len(best_48h_authors):
            best_48h_authors = authors_in_window

    unique_authors_48h = len(best_48h_authors)

    by_hour = Counter(dt.strftime("%Y-%m-%dT%H") for dt, _ in enriched)
    max_per_hour = max(by_hour.values())
    total = len(enriched)
    concentration = max_per_hour / total

    # Elevated when many posts occur in narrow windows.
    clustering_score = clamp_score(concentration * 100)
    if unique_authors_120h >= 5:
        clustering_score = max(clustering_score, 80)
    if unique_authors_48h >= 4:
        clustering_score = max(clustering_score, 85)
    if unique_authors_48h >= 6:
        clustering_score = max(clustering_score, 95)

    # Coordination signal also considers tight overall window.
    window_signal = 30 if amplification_window_hours <= 48 else 15 if amplification_window_hours <= 120 else 5
    coordination_score = clamp_score(clustering_score * 0.7 + window_signal)

    seed_posts: list[dict[str, Any]] = []
    hype_posts: list[dict[str, Any]] = []
    amount_pattern = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?\s*(?:[kKmMbB])?")
    for dt, post in enriched:
        text = (post.get("text") or "").strip()
        if len(text) < 50:
            seed_posts.append(
                {
                    "id": post.get("id"),
                    "author": post.get("author"),
                    "timestamp": dt.isoformat(),
                    "text": text[:220],
                }
            )
        if len(text) >= 80 and amount_pattern.search(text):
            hype_posts.append(
                {
                    "id": post.get("id"),
                    "author": post.get("author"),
                    "timestamp": dt.isoformat(),
                    "text": text[:220],
                }
            )

    return {
        "events": events,
        "seed_post": {
            "id": first_post.get("id"),
            "author": first_post.get("author"),
            "timestamp": first_dt.isoformat(),
            "text": first_post.get("text", "")[:220],
        },
        "amplification_window_hours": amplification_window_hours,
        "unique_authors_120h": unique_authors_120h,
        "unique_authors_48h": unique_authors_48h,
        "clustering_score": clustering_score,
        "coordination_score": coordination_score,
        "seed_posts": seed_posts,
        "hype_posts": hype_posts,
    }
