"""HypeCheck FastAPI backend."""
from __future__ import annotations

import os
import time
from collections import defaultdict
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.pipeline import run_pipeline_async, load_report

app = FastAPI(title="HypeCheck API", version="0.2.0")

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


# --- Models ---
class CheckRequest(BaseModel):
    urls: list[str]
    full: bool = False


# --- Endpoints ---
@app.get("/api/hypecheck/health")
async def health():
    return {"status": "ok", "version": "0.2.0"}


@app.post("/api/hypecheck/check")
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

    try:
        result = await run_pipeline_async(urls=body.urls, full=body.full)
        return result
    except Exception as e:
        raise HTTPException(500, f"Pipeline error: {str(e)}")


@app.get("/api/hypecheck/report/{report_id}")
async def get_report(report_id: str):
    try:
        return load_report(report_id)
    except FileNotFoundError:
        raise HTTPException(404, "Report not found")
