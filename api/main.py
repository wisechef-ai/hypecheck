"""HypeCheck FastAPI backend — v0.4.0 with tiered access + Stripe fulfillment."""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import stripe
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from src.pipeline import run_pipeline_async, load_report

app = FastAPI(title="HypeCheck API", version="0.4.0", root_path="/api/hypecheck")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Config ---
RATE_LIMIT = 3  # free checks/day
STRIPE_SECRET = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
REPORT_DIR = Path(os.getenv("HYPECHECK_REPORT_DIR", ".hypecheck/reports"))
KEYS_FILE = Path(os.getenv("HYPECHECK_KEYS_FILE", ".hypecheck/api_keys.json"))
REPORT_CREDITS_FILE = Path(os.getenv("HYPECHECK_CREDITS_FILE", ".hypecheck/report_credits.json"))

stripe.api_key = STRIPE_SECRET

# --- State ---
_rate_store: dict[str, list[float]] = defaultdict(list)

# Report credits: {session_id: {credits: int, email: str, urls_pending: list}}
_report_credits: dict[str, dict] = {}

# Load persistent API keys
def _load_api_keys() -> set[str]:
    keys = set(
        k.strip()
        for k in os.getenv("HYPECHECK_API_KEYS", "").split(",")
        if k.strip()
    )
    if KEYS_FILE.exists():
        try:
            data = json.loads(KEYS_FILE.read_text())
            keys.update(k for k in data.get("keys", []) if k)
        except Exception:
            pass
    return keys

def _save_api_key(key: str, email: str):
    KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {"keys": [], "details": []}
    if KEYS_FILE.exists():
        try:
            data = json.loads(KEYS_FILE.read_text())
        except Exception:
            pass
    data.setdefault("keys", []).append(key)
    data.setdefault("details", []).append({
        "key": key, "email": email,
        "created": datetime.now(timezone.utc).isoformat(),
        "plan": "pro_monthly",
    })
    KEYS_FILE.write_text(json.dumps(data, indent=2))
    API_KEYS.add(key)

def _save_report_credit(session_id: str, email: str, credits: int):
    REPORT_CREDITS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if REPORT_CREDITS_FILE.exists():
        try:
            data = json.loads(REPORT_CREDITS_FILE.read_text())
        except Exception:
            pass
    data[session_id] = {
        "email": email,
        "credits": credits,
        "created": datetime.now(timezone.utc).isoformat(),
        "used": 0,
    }
    REPORT_CREDITS_FILE.write_text(json.dumps(data, indent=2))
    _report_credits[session_id] = {"credits": credits, "email": email, "used": 0}

API_KEYS = _load_api_keys()


# --- Helpers ---
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
    if isinstance(summary, dict):
        return summary
    if isinstance(summary, str):
        cleaned = re.sub(r"```(?:json)?\s*", "", summary).strip().rstrip("`")
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        return {"risk_summary": cleaned}
    return {"risk_summary": str(summary)}

def _strip_for_free(result: dict) -> dict:
    """Strip paid-only fields from free tier results."""
    return {
        "verdict": result.get("verdict"),
        "trust_score": result.get("trust_score"),
        "analysis_mode": result.get("analysis_mode"),
        "note": result.get("note"),
        "tier": "free",
        "stages": {
            stage: {"score": data.get("score"), "risk": data.get("risk")}
            if isinstance(data, dict) else data
            for stage, data in (result.get("stages") or {}).items()
        },
        "upgrade": {
            "message": "Full evidence, detailed analysis, and LLM summary available with a paid report or Pro API key.",
            "report_url": "https://wisechef.ai/hypecheck#pricing",
            "per_report": "$5",
            "pro_api": "$49/mo",
        },
    }


# --- Models ---
class CheckRequest(BaseModel):
    urls: list[str]
    full: bool = False

class RedeemRequest(BaseModel):
    session_id: str
    urls: list[str]


# --- Endpoints ---
@app.get("/api/hypecheck/health")
@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.4.0"}


@app.post("/api/hypecheck/check")
@app.post("/check")
async def check(body: CheckRequest, request: Request):
    if not body.urls:
        raise HTTPException(400, "At least one URL required")
    if len(body.urls) > 20:
        raise HTTPException(400, "Max 20 URLs per request")

    is_paid = _is_authed(request)

    if not is_paid and not _check_rate_limit(request):
        return JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit exceeded (3 checks/day). Get an API key for unlimited access.",
                "upgrade_url": "https://wisechef.ai/hypecheck#pricing",
            },
        )

    tweet_count = sum(1 for u in body.urls if "x.com/" in u or "twitter.com/" in u)
    non_tweet = [u for u in body.urls if "x.com/" not in u and "twitter.com/" not in u]
    is_campaign = tweet_count >= 3 or (tweet_count >= 1 and len(non_tweet) >= 1)

    try:
        result = await run_pipeline_async(urls=body.urls, full=is_paid and body.full)
        result["summary"] = _clean_summary(result.get("summary"))

        if is_campaign:
            result["analysis_mode"] = "campaign"
        elif tweet_count == 1:
            result["analysis_mode"] = "single_tweet"
            result["note"] = "Single-tweet analysis provides limited coordination detection. For full campaign analysis, submit 3+ related tweet URLs."
        elif non_tweet:
            result["analysis_mode"] = "project"
        else:
            result["analysis_mode"] = "general"

        # Free tier: strip detailed evidence + summary
        if not is_paid:
            return _strip_for_free(result)

        result["tier"] = "pro"
        return result
    except Exception as e:
        raise HTTPException(500, f"Pipeline error: {str(e)}")


@app.post("/api/hypecheck/check/report")
@app.post("/check/report")
async def check_with_report_credit(body: RedeemRequest, request: Request):
    """Redeem a purchased report credit to run a full investigation."""
    sid = body.session_id
    # Check in-memory first, then persistent storage
    credit = _report_credits.get(sid)
    if not credit:
        if REPORT_CREDITS_FILE.exists():
            try:
                all_credits = json.loads(REPORT_CREDITS_FILE.read_text())
                if sid in all_credits and all_credits[sid]["used"] < all_credits[sid]["credits"]:
                    credit = all_credits[sid]
                    _report_credits[sid] = credit
            except Exception:
                pass
    if not credit or credit.get("used", 0) >= credit.get("credits", 0):
        raise HTTPException(403, "No report credits remaining for this session. Purchase a report at wisechef.ai/hypecheck#pricing")

    if not body.urls or len(body.urls) > 20:
        raise HTTPException(400, "Provide 1-20 URLs")

    try:
        result = await run_pipeline_async(urls=body.urls, full=True)
        result["summary"] = _clean_summary(result.get("summary"))
        result["tier"] = "paid_report"

        # Save full report
        report_id = hashlib.sha256(f"{sid}:{time.time()}".encode()).hexdigest()[:12]
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        report_path = REPORT_DIR / f"{report_id}.json"
        report_data = {
            "id": report_id,
            "created": datetime.now(timezone.utc).isoformat(),
            "urls": body.urls,
            "result": result,
        }
        report_path.write_text(json.dumps(report_data, indent=2))

        # Decrement credit
        credit["used"] = credit.get("used", 0) + 1
        if REPORT_CREDITS_FILE.exists():
            try:
                all_credits = json.loads(REPORT_CREDITS_FILE.read_text())
                if sid in all_credits:
                    all_credits[sid]["used"] = credit["used"]
                    REPORT_CREDITS_FILE.write_text(json.dumps(all_credits, indent=2))
            except Exception:
                pass

        result["report_id"] = report_id
        result["report_url"] = f"https://wisechef.ai/api/hypecheck/report/{report_id}"
        return result
    except Exception as e:
        raise HTTPException(500, f"Pipeline error: {str(e)}")


@app.get("/api/hypecheck/report/{report_id}")
@app.get("/report/{report_id}")
async def get_report(report_id: str):
    """Retrieve a saved full report by ID."""
    # Sanitize
    report_id = re.sub(r"[^a-f0-9]", "", report_id)[:12]
    report_path = REPORT_DIR / f"{report_id}.json"
    if report_path.exists():
        return json.loads(report_path.read_text())
    # Legacy fallback
    try:
        return load_report(report_id)
    except FileNotFoundError:
        raise HTTPException(404, "Report not found")


@app.get("/api/hypecheck/credits/{session_id}")
@app.get("/credits/{session_id}")
async def check_credits(session_id: str):
    """Check remaining report credits for a Stripe checkout session."""
    credit = _report_credits.get(session_id)
    if not credit and REPORT_CREDITS_FILE.exists():
        try:
            all_credits = json.loads(REPORT_CREDITS_FILE.read_text())
            credit = all_credits.get(session_id)
        except Exception:
            pass
    if not credit:
        return {"credits": 0, "used": 0, "valid": False}
    return {
        "credits": credit.get("credits", 0),
        "used": credit.get("used", 0),
        "valid": credit.get("used", 0) < credit.get("credits", 0),
    }


# --- Stripe Webhook ---
@app.post("/api/hypecheck/webhook")
@app.post("/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(400, "Invalid webhook signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        email = session.get("customer_email") or session.get("customer_details", {}).get("email", "")
        session_id = session["id"]
        metadata = session.get("metadata", {})
        plan = metadata.get("plan", "")

        if plan == "pro" or "pro" in str(session.get("mode", "")):
            # Pro subscription — provision API key
            api_key = f"hc_{secrets.token_hex(16)}"
            _save_api_key(api_key, email)
            # TODO: Email the key to the customer via Resend
            # For now, log it
            log_path = Path(".hypecheck/webhook_log.jsonl")
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a") as f:
                f.write(json.dumps({
                    "type": "pro_key_created",
                    "email": email,
                    "key": api_key,
                    "session_id": session_id,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }) + "\n")

        elif plan == "report" or session.get("mode") == "payment":
            # Per-report purchase — add credits
            qty = 1
            try:
                line_items = stripe.checkout.Session.list_line_items(session_id)
                if line_items and line_items.data:
                    qty = line_items.data[0].quantity or 1
            except Exception:
                pass
            _save_report_credit(session_id, email, qty)
            log_path = Path(".hypecheck/webhook_log.jsonl")
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a") as f:
                f.write(json.dumps({
                    "type": "report_credits_added",
                    "email": email,
                    "credits": qty,
                    "session_id": session_id,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }) + "\n")

    return {"received": True}
