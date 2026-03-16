from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import settings
from src.stages import code_audit, intake, network, report, scrape, timeline, verify_claims


def _merge_scrape_outputs(scrape_outputs: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {
        "source_type": "multi" if len(scrape_outputs) > 1 else (scrape_outputs[0].get("source_type") if scrape_outputs else None),
        "x": {"posts": [], "accounts": {}},
        "github": {"repo": None},
        "website": {"pages": []},
        "polymarket": {"profiles": []},
    }

    seen_post_ids: set[str] = set()
    seen_website_urls: set[str] = set()

    for out in scrape_outputs:
        x_data = out.get("x", {})
        for post in x_data.get("posts", []):
            pid = str(post.get("id") or "")
            if pid and pid in seen_post_ids:
                continue
            if pid:
                seen_post_ids.add(pid)
            merged["x"]["posts"].append(post)

        for author, account in x_data.get("accounts", {}).items():
            merged["x"]["accounts"].setdefault(author, account)

        repo = out.get("github", {}).get("repo")
        if repo and merged["github"]["repo"] is None:
            merged["github"]["repo"] = repo

        website = out.get("website")
        if isinstance(website, dict) and website:
            page_url = website.get("url")
            if page_url and page_url in seen_website_urls:
                continue
            if page_url:
                seen_website_urls.add(page_url)
            merged["website"]["pages"].append(website)

        profile = out.get("polymarket", {}).get("profile")
        if profile:
            merged["polymarket"]["profiles"].append(profile)

    return merged


async def run_pipeline_async(urls: list[str], full: bool = False) -> dict[str, Any]:
    intake_outputs = [intake.run(url) for url in urls]
    scrape_outputs = [await scrape.run(intake_out) for intake_out in intake_outputs]
    scrape_out = _merge_scrape_outputs(scrape_outputs)

    network_out = network.run(scrape_out)
    code_out = code_audit.run(scrape_out)
    claims_out = await verify_claims.run(scrape_out)
    timeline_out = timeline.run(scrape_out)

    display_url = urls[0] if len(urls) == 1 else ", ".join(urls)

    final = report.run(
        url=display_url,
        intake={"sources": intake_outputs},
        scrape=scrape_out,
        network=network_out,
        code_audit=code_out,
        claims=claims_out,
        timeline=timeline_out,
    )

    if full:
        final["full_stage_output"] = {
            "intake": intake_outputs,
            "scrape": scrape_outputs,
            "scrape_merged": scrape_out,
            "network": network_out,
            "code_audit": code_out,
            "claims": claims_out,
            "timeline": timeline_out,
        }

    final["report_id"] = save_report(final)
    return final


def run_pipeline(urls: list[str], full: bool = False) -> dict[str, Any]:
    return asyncio.run(run_pipeline_async(urls=urls, full=full))


def _report_filename(payload: dict[str, Any]) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    digest = hashlib.sha1(payload["url"].encode("utf-8")).hexdigest()[:10]
    return f"{ts}_{digest}.json"


def save_report(payload: dict[str, Any]) -> str:
    report_dir = Path(settings.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    filename = _report_filename(payload)
    path = report_dir / filename
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    return filename


def load_report(report_id: str) -> dict[str, Any]:
    path = Path(settings.report_dir) / report_id
    if not path.exists():
        raise FileNotFoundError(f"Report not found: {report_id}")
    return json.loads(path.read_text(encoding="utf-8"))
