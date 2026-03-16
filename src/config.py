from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_base_url: str | None = os.getenv("OPENAI_BASE_URL")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    github_token: str | None = os.getenv("GITHUB_TOKEN")
    request_timeout_seconds: float = float(os.getenv("HYPECHECK_TIMEOUT", "20"))
    report_dir: str = os.getenv("HYPECHECK_REPORT_DIR", ".hypecheck/reports")


settings = Settings()
