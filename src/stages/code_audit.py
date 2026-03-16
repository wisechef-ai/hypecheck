from __future__ import annotations

import json
import re
from typing import Any


WALLET_LIBS = ["ethers", "web3", "wagmi", "solana", "viem"]
MALICIOUS_HINTS = ["event-stream", "node-ipc", "crossenv-malware"]
SUSPICIOUS_ENV_VARS = ["PRIVATE_KEY", "SEED_PHRASE", "MNEMONIC", "WALLET", "RPC_URL"]


def _contains_any(text: str, needles: list[str]) -> list[str]:
    lower = text.lower()
    return [n for n in needles if n.lower() in lower]


def _scan_postinstall(package_json_text: str) -> bool:
    try:
        payload = json.loads(package_json_text)
    except json.JSONDecodeError:
        return bool(re.search(r'"postinstall"\s*:', package_json_text))

    scripts = payload.get("scripts", {})
    return "postinstall" in scripts


def run(scrape_data: dict[str, Any]) -> dict[str, Any]:
    repo = scrape_data.get("github", {}).get("repo")
    if not repo:
        return {
            "risk": "unknown",
            "score": 50,
            "findings": ["No repository data available"],
            "wallet_libs": [],
            "malicious_packages": [],
            "postinstall_detected": False,
            "env_wallet_vars": [],
        }

    files = repo.get("files", {})
    readme = repo.get("readme", "")

    all_text = "\n".join([readme, *files.values()])

    wallet_libs = _contains_any(all_text, WALLET_LIBS)
    malicious_packages = _contains_any(all_text, MALICIOUS_HINTS)

    postinstall = False
    if "package.json" in files:
        postinstall = _scan_postinstall(files["package.json"])

    env_wallet_vars = []
    env_example = files.get(".env.example", "")
    for var in SUSPICIOUS_ENV_VARS:
        if re.search(rf"\b{re.escape(var)}\b", env_example):
            env_wallet_vars.append(var)

    findings: list[str] = []
    risk_points = 0

    if malicious_packages:
        findings.append(f"Potentially malicious package indicators found: {', '.join(malicious_packages)}")
        risk_points += 60
    if postinstall:
        findings.append("Found postinstall script in package.json")
        risk_points += 20
    if env_wallet_vars:
        findings.append(f"Wallet-sensitive env vars in .env.example: {', '.join(env_wallet_vars)}")
        risk_points += 10
    if wallet_libs:
        findings.append(f"Wallet/chain libraries detected: {', '.join(wallet_libs)}")

    claimed_polymarket = "polymarket" in readme.lower()
    if claimed_polymarket and not wallet_libs:
        findings.append("README claims Polymarket-related behavior but little wallet/trading code detected")
        risk_points += 10

    if not findings:
        findings.append("No obvious wallet-drain or dependency red flags detected")

    if risk_points >= 70:
        risk = "critical"
    elif risk_points >= 45:
        risk = "high"
    elif risk_points >= 20:
        risk = "medium"
    else:
        risk = "low"

    safety_score = max(0, 100 - risk_points)

    return {
        "risk": risk,
        "score": safety_score,
        "findings": findings,
        "wallet_libs": wallet_libs,
        "malicious_packages": malicious_packages,
        "postinstall_detected": postinstall,
        "env_wallet_vars": env_wallet_vars,
    }
