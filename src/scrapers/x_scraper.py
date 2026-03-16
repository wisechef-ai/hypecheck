from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

FXTWITTER_URL = "https://api.fxtwitter.com/status/{tweet_id}"
SYNDICATION_USER_URL = "https://syndication.twitter.com/srv/timeline-profile/screen-name/{username}"
JINA_READER_X_URL = "https://r.jina.ai/http://x.com/i/status/{tweet_id}"

TWEET_URL_RE = re.compile(r"https?://(?:x|twitter)\.com/[^/]+/status/(\d+)", re.IGNORECASE)


def parse_tweet_id(url: str) -> str | None:
    match = TWEET_URL_RE.search(url)
    return match.group(1) if match else None


def parse_username(url: str) -> str | None:
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    if not parts:
        return None
    return parts[0].lstrip("@")


def _collect_urls(text: str) -> list[str]:
    return re.findall(r"https?://\S+", text)


def _safe_date(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).isoformat()
    except ValueError:
        try:
            return datetime.strptime(raw, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            return raw


class XScraper:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def fetch_tweet(self, tweet_id: str) -> dict[str, Any]:
        url = FXTWITTER_URL.format(tweet_id=tweet_id)
        response = await self.client.get(url)
        if response.status_code != 200:
            return await self._fetch_tweet_via_reader(tweet_id)
        payload = response.json()

        tweet = payload.get("tweet", payload)
        text = (
            tweet.get("text")
            or tweet.get("content")
            or payload.get("text")
            or payload.get("content")
            or ""
        )
        author = tweet.get("author") or payload.get("author") or {}
        author_name = author.get("screen_name") or author.get("username") or tweet.get("author_name")

        created_at = (
            tweet.get("created_at")
            or tweet.get("date")
            or payload.get("created_at")
            or payload.get("date")
        )

        urls = _collect_urls(text)
        urls.extend(
            u.get("expanded_url", "")
            for u in tweet.get("entities", {}).get("urls", [])
            if isinstance(u, dict)
        )
        urls = [u for u in urls if u]

        related_ids = []
        for candidate in urls:
            maybe = parse_tweet_id(candidate)
            if maybe and maybe != tweet_id:
                related_ids.append(maybe)

        # Include quoted/replied IDs if present.
        for key in ("quote_id", "quoted_tweet_id", "in_reply_to_status_id"):
            value = tweet.get(key) or payload.get(key)
            if value:
                related_ids.append(str(value))

        return {
            "id": str(tweet.get("id") or payload.get("id") or tweet_id),
            "url": f"https://x.com/i/status/{tweet_id}",
            "text": text,
            "author": author_name,
            "author_bio": author.get("description") or "",
            "created_at": _safe_date(created_at),
            "like_count": tweet.get("likes") or tweet.get("favorite_count") or 0,
            "retweet_count": tweet.get("retweets") or tweet.get("retweet_count") or 0,
            "reply_count": tweet.get("replies") or tweet.get("reply_count") or 0,
            "quote_count": tweet.get("quote_count") or 0,
            "urls": list(dict.fromkeys(urls)),
            "related_tweet_ids": list(dict.fromkeys(related_ids)),
        }

    async def _fetch_tweet_via_reader(self, tweet_id: str) -> dict[str, Any]:
        reader_url = JINA_READER_X_URL.format(tweet_id=tweet_id)
        response = await self.client.get(reader_url)
        response.raise_for_status()
        text = response.text

        # Reader output is markdown/plain text; keep extraction lightweight.
        content_match = re.search(r"Conversation\\n[-]+\\n\\n(.+)", text, re.DOTALL)
        content = content_match.group(1).strip() if content_match else text[:2000]
        content = re.sub(r"\\s+", " ", content).strip()

        urls = _collect_urls(text)
        related_ids = []
        for candidate in urls:
            maybe = parse_tweet_id(candidate)
            if maybe and maybe != tweet_id:
                related_ids.append(maybe)

        author_match = re.search(r"Title:\\s*([A-Za-z0-9_]+)\\s+on\\s+X", text)
        author = author_match.group(1) if author_match else None
        published_match = re.search(r"Published Time:\\s*(.+)", text)
        published = _safe_date(published_match.group(1).strip()) if published_match else None

        return {
            "id": str(tweet_id),
            "url": f"https://x.com/i/status/{tweet_id}",
            "text": content[:5000],
            "author": author,
            "author_bio": "",
            "created_at": published,
            "like_count": 0,
            "retweet_count": 0,
            "reply_count": 0,
            "quote_count": 0,
            "urls": list(dict.fromkeys(urls)),
            "related_tweet_ids": list(dict.fromkeys(related_ids)),
        }

    async def fetch_user_timeline(self, username: str) -> list[dict[str, Any]]:
        url = SYNDICATION_USER_URL.format(username=username)
        response = await self.client.get(url)
        response.raise_for_status()
        payload = response.json()

        items = payload.get("timeline", []) or payload.get("items", [])
        out: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            text = item.get("text") or item.get("content") or ""
            out.append(
                {
                    "id": str(item.get("id") or ""),
                    "author": username,
                    "text": text,
                    "created_at": _safe_date(item.get("created_at") or item.get("date")),
                    "urls": _collect_urls(text),
                }
            )
        return out
