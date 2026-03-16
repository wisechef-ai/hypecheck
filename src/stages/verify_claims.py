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


async def run(scrape_data: dict[str, Any]) -> dict[str, Any]:
    posts = scrape_data.get("x", {}).get("posts", [])
    text_blob = "\n".join([p.get("text", "") for p in posts])

    claims = list(dict.fromkeys(PROFIT_CLAIM_RE.findall(text_blob)))
    wallets = list(dict.fromkeys(re.findall(r"0x[a-fA-F0-9]{40}", text_blob)))
    profile_refs = re.findall(r"polymarket\.com/profile/([A-Za-z0-9_\-.]+)", text_blob)

    discrepancies: list[str] = []
    evidence: list[str] = []

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
        else:
            verified_weight += 10

    if not claims:
        evidence.append("No explicit profit claim patterns detected")

    score = clamp_score(verified_weight)

    return {
        "claims": claims,
        "wallets_detected": list(dict.fromkeys(wallets)),
        "polymarket_results": polymarket_results,
        "claims_verified": score,
        "discrepancies": discrepancies,
        "evidence": evidence,
    }
