from __future__ import annotations

from typing import Any

import httpx
from bs4 import BeautifulSoup

from src.config import settings
from src.scrapers.github_scraper import GitHubScraper
from src.scrapers.polymarket import PolymarketScraper
from src.scrapers.x_scraper import XScraper


async def _scrape_x(client: httpx.AsyncClient, intake: dict[str, Any]) -> dict[str, Any]:
    scraper = XScraper(client)
    tweet_id = intake["metadata"].get("tweet_id")
    author = intake["metadata"].get("author")

    posts: list[dict[str, Any]] = []
    accounts: dict[str, dict[str, str]] = {}

    if tweet_id:
        try:
            first = await scraper.fetch_tweet(str(tweet_id))
            posts.append(first)
            if first.get("author"):
                accounts[first["author"]] = {"bio": first.get("author_bio", "")}

            # Follow a shallow quote/reference chain.
            for related_id in first.get("related_tweet_ids", [])[:8]:
                try:
                    related = await scraper.fetch_tweet(str(related_id))
                    posts.append(related)
                    if related.get("author"):
                        accounts[related["author"]] = {"bio": related.get("author_bio", "")}
                except httpx.HTTPError:
                    continue
        except httpx.HTTPError:
            posts.append(
                {
                    "id": str(tweet_id),
                    "url": intake.get("url"),
                    "text": "",
                    "author": author,
                    "author_bio": "",
                    "created_at": None,
                    "related_tweet_ids": [],
                    "urls": [],
                    "scrape_error": "fxtwitter_unavailable",
                }
            )

    if author:
        try:
            timeline = await scraper.fetch_user_timeline(str(author))
            posts.extend(timeline[:20])
            accounts.setdefault(str(author), {"bio": ""})
        except httpx.HTTPError:
            pass

    deduped: dict[str, dict[str, Any]] = {}
    for post in posts:
        pid = str(post.get("id") or "")
        if pid and pid not in deduped:
            deduped[pid] = post

    return {
        "posts": list(deduped.values()),
        "accounts": accounts,
    }


async def _scrape_github(client: httpx.AsyncClient, intake: dict[str, Any]) -> dict[str, Any]:
    scraper = GitHubScraper(client)
    owner = intake["metadata"].get("repo_owner")
    repo = intake["metadata"].get("repo_name")
    if not owner or not repo:
        return {"repo": None}
    repo_data = await scraper.fetch_repo(str(owner), str(repo))
    return {"repo": repo_data}


async def _scrape_website(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    response = await client.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    return {
        "url": url,
        "title": (soup.title.string.strip() if soup.title and soup.title.string else ""),
        "text": soup.get_text(" ", strip=True)[:6000],
        "links": [a.get("href") for a in soup.find_all("a", href=True)[:100]],
    }


async def _scrape_polymarket(client: httpx.AsyncClient, intake: dict[str, Any]) -> dict[str, Any]:
    scraper = PolymarketScraper(client)
    username = intake["metadata"].get("author")
    if not username:
        return {"profile": None}
    return {"profile": await scraper.fetch_profile(str(username))}


async def run(intake: dict[str, Any]) -> dict[str, Any]:
    timeout = httpx.Timeout(settings.request_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        source_type = intake["source_type"]
        output: dict[str, Any] = {"source_type": source_type}

        if source_type == "x_post":
            output["x"] = await _scrape_x(client, intake)
        elif source_type == "github_repo":
            output["github"] = await _scrape_github(client, intake)
        elif source_type == "polymarket_wallet":
            output["polymarket"] = await _scrape_polymarket(client, intake)
        else:
            output["website"] = await _scrape_website(client, intake["url"])

        # Opportunistic extraction: if any scraped text links a GitHub repo, fetch it too.
        urls: list[str] = []
        for post in output.get("x", {}).get("posts", []):
            urls.extend(post.get("urls", []))
        for link in output.get("website", {}).get("links", []):
            if isinstance(link, str):
                urls.append(link)

        for maybe_url in urls:
            parsed = GitHubScraper.parse_repo(maybe_url)
            if parsed:
                owner, repo = parsed
                output.setdefault("github", await _scrape_github(client, {
                    "metadata": {"repo_owner": owner, "repo_name": repo}
                }))
                break

        return output
