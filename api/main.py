"""HypeCheck FastAPI backend."""
from __future__ import annotations

import os
import re
import time
from collections import defaultdict
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.pipeline import run_pipeline_async, load_report

app = FastAPI(title="HypeCheck API", version="0.3.0", root_path="/api/hypecheck")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Rate limiting ---
RATE_LIMIT = 3  # checks/day for unauthenticated
_rate_store: dict[str, list[float]] = defaultdict(list)

API_KEYS = set(
    k.strip()
    for k in os.getenv("HYPECHECK_API_KEYS", "").split(",")
    if k.strip()
)


def _is_authed(request: Request) -> bool:
    key = request.headers.get("X-API-Key", "")
    return key in API_KEYS and len(key) > 0


def _check_rate_limit(request: Request) -> bool:
    if _is_authed(request):
        return True
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    day_ago = now - 86400
    _rate_store[ip] = [t for t in _rate_store[ip] if t > day_ago]
    if len(_rate_store[ip]) >= RATE_LIMIT:
        return False
    _rate_store[ip].append(now)
    return True


def _clean_summary(summary: Any) -> dict[str, Any]:
    """Normalize the LLM summary into a clean dict with risk_summary and conclusion."""
    if isinstance(summary, dict):
        return summary

    if isinstance(summary, str):
        # Strip markdown code fences
        cleaned = re.sub(r"```(?:json)?\s*", "", summary).strip().rstrip("`")
        try:
            parsed = __import__("json").loads(cleaned)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        return {"risk_summary": cleaned}

    return {"risk_summary": str(summary)}


# --- Models ---
class CheckRequest(BaseModel):
    urls: list[str]
    full: bool = False


# --- Endpoints (dual-mounted: direct + behind Express proxy) ---
@app.get("/api/hypecheck/health")
@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.3.0"}


@app.post("/api/hypecheck/check")
@app.post("/check")
async def check(body: CheckRequest, request: Request):
    if not body.urls:
        raise HTTPException(400, "At least one URL required")
    if len(body.urls) > 20:
        raise HTTPException(400, "Max 20 URLs per request")

    if not _check_rate_limit(request):
        return JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit exceeded (3 checks/day). Get an API key for unlimited access.",
                "upgrade_url": "https://wisechef.ai/hypecheck#pricing",
            },
        )

    # Determine analysis mode based on URL count
    tweet_count = sum(1 for u in body.urls if "x.com/" in u or "twitter.com/" in u)
    non_tweet = [u for u in body.urls if "x.com/" not in u and "twitter.com/" not in u]
    is_campaign = tweet_count >= 3 or (tweet_count >= 1 and len(non_tweet) >= 1)

    try:
        result = await run_pipeline_async(urls=body.urls, full=body.full)

        # Clean up the summary
        result["summary"] = _clean_summary(result.get("summary"))

        # Add analysis mode indicator
        if is_campaign:
            result["analysis_mode"] = "campaign"
        elif tweet_count == 1:
            result["analysis_mode"] = "single_tweet"
            result["note"] = "Single-tweet analysis provides limited coordination detection. For full campaign analysis, submit 3+ related tweet URLs."
        elif non_tweet:
            result["analysis_mode"] = "project"
        else:
            result["analysis_mode"] = "general"

        return result
    except Exception as e:
        raise HTTPException(500, f"Pipeline error: {str(e)}")


@app.get("/api/hypecheck/report/{report_id}")
@app.get("/report/{report_id}")
async def get_report(report_id: str):
    try:
        return load_report(report_id)
    except FileNotFoundError:
        raise HTTPException(404, "Report not found")
