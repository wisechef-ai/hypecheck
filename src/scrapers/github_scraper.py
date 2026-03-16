from __future__ import annotations

import base64
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from src.config import settings

GITHUB_API = "https://api.github.com"


class GitHubScraper:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    @staticmethod
    def parse_repo(url: str) -> tuple[str, str] | None:
        parsed = urlparse(url)
        if parsed.netloc.lower() not in {"github.com", "www.github.com"}:
            return None
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) < 2:
            return None
        return parts[0], re.sub(r"\.git$", "", parts[1])

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github+json"}
        if settings.github_token:
            headers["Authorization"] = f"Bearer {settings.github_token}"
        return headers

    async def _get_json(self, path: str) -> dict[str, Any] | list[Any]:
        response = await self.client.get(f"{GITHUB_API}{path}", headers=self._headers())
        response.raise_for_status()
        return response.json()

    async def fetch_repo(self, owner: str, repo: str) -> dict[str, Any]:
        info = await self._get_json(f"/repos/{owner}/{repo}")
        contributors = await self._get_json(f"/repos/{owner}/{repo}/contributors?per_page=20")

        readme = ""
        try:
            readme_raw = await self.client.get(
                f"{GITHUB_API}/repos/{owner}/{repo}/readme",
                headers={**self._headers(), "Accept": "application/vnd.github.raw+json"},
            )
            if readme_raw.status_code == 200:
                readme = readme_raw.text
        except httpx.HTTPError:
            readme = ""

        files: dict[str, str] = {}
        for path in ["package.json", "pyproject.toml", "requirements.txt", ".env.example"]:
            content = await self.fetch_file(owner, repo, path)
            if content is not None:
                files[path] = content

        return {
            "owner": owner,
            "repo": repo,
            "html_url": info.get("html_url"),
            "description": info.get("description"),
            "stars": info.get("stargazers_count", 0),
            "forks": info.get("forks_count", 0),
            "open_issues": info.get("open_issues_count", 0),
            "default_branch": info.get("default_branch"),
            "contributors": [c.get("login") for c in contributors if isinstance(c, dict)],
            "readme": readme,
            "files": files,
        }

    async def search_repo_by_name(self, name: str) -> tuple[str, str] | None:
        payload = await self._get_json(
            f"/search/repositories?q={name}+in:name&sort=stars&order=desc&per_page=1"
        )
        if not isinstance(payload, dict):
            return None
        items = payload.get("items", [])
        if not items:
            return None
        top = items[0]
        full_name = top.get("full_name", "")
        if "/" not in full_name:
            return None
        owner, repo = full_name.split("/", 1)
        return owner, repo

    async def fetch_file(self, owner: str, repo: str, path: str) -> str | None:
        try:
            payload = await self._get_json(f"/repos/{owner}/{repo}/contents/{path}")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise

        if not isinstance(payload, dict):
            return None

        if payload.get("encoding") == "base64" and payload.get("content"):
            raw = payload["content"].replace("\n", "")
            return base64.b64decode(raw).decode("utf-8", errors="replace")
        if payload.get("download_url"):
            response = await self.client.get(payload["download_url"])
            if response.status_code == 200:
                return response.text
        return None
