from __future__ import annotations

import re
from typing import Any

import httpx

from src.config import settings
from src.scrapers.polymarket import PolymarketScraper
from src.utils.scoring import clamp_score

PROFIT_CLAIM_RE = re.compile(
    r"(?:\$\s?\d[\d,]*(?:\.\d+)?|\d+[xX]|\d+%|pnl|profit|made\s+\$\d[\d,]*)",
    re.IGNORECASE,
)
ARROW_CLAIM_RE = re.compile(
    r"\$?\s?\d[\d,]*(?:\.\d+)?\s*[kKmMbB]?\s*(?:to|->|→)\s*\$?\s?\d[\d,]*(?:\.\d+)?\s*[kKmMbB]?",
    re.IGNORECASE,
)
MULTIPLIER_CLAIM_RE = re.compile(r"\b\d+(?:\.\d+)?\s*[xX]\b")
MONEY_RE = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?\s*(?:[kKmMbB])?")


def _parse_money_token(token: str) -> float:
    cleaned = token.replace("$", "").replace(",", "").strip().lower()
    multiplier = 1.0
    if cleaned.endswith("k"):
        multiplier = 1_000.0
        cleaned = cleaned[:-1].strip()
    elif cleaned.endswith("m"):
        multiplier = 1_000_000.0
        cleaned = cleaned[:-1].strip()
    elif cleaned.endswith("b"):
        multiplier = 1_000_000_000.0
        cleaned = cleaned[:-1].strip()
    try:
        return float(cleaned) * multiplier
    except ValueError:
        return 0.0


def _claim_over_100k(claim: str) -> bool:
    amounts = MONEY_RE.findall(claim)
    if not amounts:
        return False
    return any(_parse_money_token(amount) > 100_000 for amount in amounts)


async def run(scrape_data: dict[str, Any]) -> dict[str, Any]:
    posts = scrape_data.get("x", {}).get("posts", [])
    text_blob = "\n".join([p.get("text", "") for p in posts])

    profit_claims = PROFIT_CLAIM_RE.findall(text_blob)
    arrow_claims = ARROW_CLAIM_RE.findall(text_blob)
    multiplier_claims = MULTIPLIER_CLAIM_RE.findall(text_blob)
    claims = list(dict.fromkeys([*profit_claims, *arrow_claims, *multiplier_claims]))
    wallets = list(dict.fromkeys(re.findall(r"0x[a-fA-F0-9]{40}", text_blob)))
    profile_refs = re.findall(r"polymarket\.com/profile/([A-Za-z0-9_\-.]+)", text_blob)

    discrepancies: list[str] = []
    evidence: list[str] = []
    unverifiable_claims_over_100k: list[str] = []

    verified_weight = 100

    if claims:
        evidence.append(f"Detected {len(claims)} potential profit/performance claim(s)")
        verified_weight -= 40

    polymarket_results: list[dict[str, Any]] = []
    timeout = httpx.Timeout(settings.request_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        poly = PolymarketScraper(client)

        for username in list(dict.fromkeys(profile_refs))[:5]:
            profile = await poly.fetch_profile(username)
            polymarket_results.append(profile)
            wallets.extend(profile.get("wallets", []))

        for wallet in list(dict.fromkeys(wallets))[:8]:
            result = await poly.fetch_wallet_positions(wallet)
            polymarket_results.append(result)

    if claims and not polymarket_results:
        discrepancies.append("Profit claims present, but no wallet/profile evidence could be retrieved")
        verified_weight -= 30
        unverifiable_claims_over_100k = [c for c in claims if _claim_over_100k(c)]

    if claims and polymarket_results:
        # MVP heuristic: if we have claims but no explicit PnL fields, treat as weakly verified.
        pnl_signals = 0
        for item in polymarket_results:
            text = str(item).lower()
            if "pnl" in text or "profit" in text or "realized" in text:
                pnl_signals += 1
        if pnl_signals == 0:
            discrepancies.append("Found wallets/profiles but could not validate claimed PnL amounts")
            verified_weight -= 25
            unverifiable_claims_over_100k = [c for c in claims if _claim_over_100k(c)]
        else:
            verified_weight += 10

    if not claims:
        evidence.append("No explicit profit claim patterns detected")

    score = clamp_score(verified_weight)

    return {
        "claims": claims,
        "arrow_claims": list(dict.fromkeys(arrow_claims)),
        "multiplier_claims": list(dict.fromkeys(multiplier_claims)),
        "wallets_detected": list(dict.fromkeys(wallets)),
        "polymarket_results": polymarket_results,
        "claims_verified": score,
        "discrepancies": discrepancies,
        "evidence": evidence,
        "unverifiable_claims_over_100k": unverifiable_claims_over_100k,
    }
