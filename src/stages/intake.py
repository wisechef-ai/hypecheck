from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from src.scrapers.github_scraper import GitHubScraper
from src.scrapers.x_scraper import parse_tweet_id, parse_username


@dataclass
class IntakeResult:
    url: str
    source_type: str
    metadata: dict


def _is_polymarket_wallet_url(url: str) -> bool:
    parsed = urlparse(url)
    if "polymarket.com" not in parsed.netloc:
        return False
    return parsed.path.startswith("/profile/")


def run(url: str) -> dict:
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()

    source_type = "website"
    metadata: dict[str, str | list[str] | None] = {
        "domain": netloc,
        "author": None,
        "repo_owner": None,
        "repo_name": None,
        "tweet_id": None,
        "linked_usernames": [],
    }

    tweet_id = parse_tweet_id(url)
    if tweet_id:
        source_type = "x_post"
        metadata["tweet_id"] = tweet_id
        metadata["author"] = parse_username(url)
    elif GitHubScraper.parse_repo(url):
        source_type = "github_repo"
        owner, repo = GitHubScraper.parse_repo(url) or (None, None)
        metadata["repo_owner"] = owner
        metadata["repo_name"] = repo
    elif _is_polymarket_wallet_url(url):
        source_type = "polymarket_wallet"
        username = [p for p in parsed.path.split("/") if p][-1]
        metadata["author"] = username

    metadata["linked_usernames"] = re.findall(r"@([A-Za-z0-9_]{1,20})", url)

    result = IntakeResult(url=url, source_type=source_type, metadata=metadata)
    return {
        "url": result.url,
        "source_type": result.source_type,
        "metadata": result.metadata,
    }
