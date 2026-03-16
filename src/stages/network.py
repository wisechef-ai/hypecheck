from __future__ import annotations

import re
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
    x_data = scrape_data.get("x", {})
    posts = x_data.get("posts", [])
    accounts = x_data.get("accounts", {})

    bios = [v.get("bio", "") for v in accounts.values() if isinstance(v, dict)]
    group_tags = []
    for bio in bios:
        group_tags.extend(re.findall(r"@[A-Za-z0-9_]{2,20}", bio.lower()))

    shared_groups = [tag for tag, count in Counter(group_tags).items() if count >= 2]

    mention_edges = 0
    for post in posts:
        text = post.get("text", "")
        mentions = re.findall(r"@[A-Za-z0-9_]{1,20}", text)
        mention_edges += len(mentions)

    times = sorted([_to_dt(p.get("created_at")) for p in posts if p.get("created_at")])
    times = [t for t in times if t is not None]
    clustered_pairs = 0
    for i in range(1, len(times)):
        delta_hours = abs((times[i] - times[i - 1]).total_seconds()) / 3600
        if delta_hours <= 2:
            clustered_pairs += 1

    account_count = max(1, len(accounts))
    posts_count = max(1, len(posts))

    group_signal = min(40, len(shared_groups) * 20)
    mention_signal = min(30, int((mention_edges / posts_count) * 10))
    cluster_signal = min(30, int((clustered_pairs / max(1, len(times) - 1)) * 30)) if len(times) > 1 else 0

    coordination_likelihood = clamp_score(group_signal + mention_signal + cluster_signal)

    return {
        "accounts_analyzed": account_count,
        "posts_analyzed": posts_count,
        "shared_groups": shared_groups,
        "cross_reference_count": mention_edges,
        "coordination_likelihood": coordination_likelihood,
    }
