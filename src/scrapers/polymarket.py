from __future__ import annotations

import re
from typing import Any

import httpx
from bs4 import BeautifulSoup

GAMMA_API = "https://gamma-api.polymarket.com"
DATA_API = "https://data-api.polymarket.com"
PROFILE_URL = "https://polymarket.com/profile/{username}"


class PolymarketScraper:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def fetch_profile_wallets(self, username: str) -> list[str]:
        response = await self.client.get(PROFILE_URL.format(username=username))
        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        text = soup.get_text(" ", strip=True)
        wallets = re.findall(r"0x[a-fA-F0-9]{40}", text)
        return list(dict.fromkeys(wallets))

    async def fetch_wallet_positions(self, wallet: str) -> dict[str, Any]:
        # Public endpoints can vary by deployment; try a few known shapes.
        attempts = [
            (f"{DATA_API}/positions", {"user": wallet}),
            (f"{DATA_API}/positions", {"address": wallet}),
            (f"{GAMMA_API}/positions", {"user": wallet}),
            (f"{GAMMA_API}/positions", {"address": wallet}),
        ]

        for url, params in attempts:
            try:
                response = await self.client.get(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    return {"wallet": wallet, "positions": data}
            except (httpx.HTTPError, ValueError):
                continue

        return {"wallet": wallet, "positions": [], "error": "No public positions endpoint response"}

    async def fetch_profile(self, username: str) -> dict[str, Any]:
        wallets = await self.fetch_profile_wallets(username)
        positions = []
        for wallet in wallets:
            positions.append(await self.fetch_wallet_positions(wallet))
        return {
            "username": username,
            "wallets": wallets,
            "positions": positions,
        }
