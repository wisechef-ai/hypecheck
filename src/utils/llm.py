from __future__ import annotations

from typing import Any

from openai import OpenAI

from src.config import settings


class LLMSynthesizer:
    def __init__(self) -> None:
        self._enabled = bool(settings.openai_api_key)
        self._client = None
        if self._enabled:
            kwargs: dict[str, Any] = {"api_key": settings.openai_api_key}
            if settings.openai_base_url:
                kwargs["base_url"] = settings.openai_base_url
            self._client = OpenAI(**kwargs)

    @property
    def enabled(self) -> bool:
        return self._enabled and self._client is not None

    def summarize(self, report_payload: dict[str, Any]) -> str | None:
        if not self.enabled:
            return None

        prompt = (
            "You are an investigator producing concise trust reports for hyped AI/crypto projects. "
            "Summarize risks, confidence, and most important evidence in 5-7 sentences. "
            "Be direct and avoid hype. JSON:\n"
            f"{report_payload}"
        )

        response = self._client.responses.create(
            model=settings.openai_model,
            input=prompt,
            max_output_tokens=300,
        )
        return response.output_text.strip() if response.output_text else None
