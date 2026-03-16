from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import settings
from src.stages import code_audit, intake, network, report, scrape, timeline, verify_claims


async def run_pipeline_async(url: str, full: bool = False) -> dict[str, Any]:
    intake_out = intake.run(url)
    scrape_out = await scrape.run(intake_out)

    network_out = network.run(scrape_out)
    code_out = code_audit.run(scrape_out)
    claims_out = await verify_claims.run(scrape_out)
    timeline_out = timeline.run(scrape_out)

    final = report.run(
        url=url,
        intake=intake_out,
        scrape=scrape_out,
        network=network_out,
        code_audit=code_out,
        claims=claims_out,
        timeline=timeline_out,
    )

    if full:
        final["full_stage_output"] = {
            "intake": intake_out,
            "scrape": scrape_out,
            "network": network_out,
            "code_audit": code_out,
            "claims": claims_out,
            "timeline": timeline_out,
        }

    final["report_id"] = save_report(final)
    return final


def run_pipeline(url: str, full: bool = False) -> dict[str, Any]:
    return asyncio.run(run_pipeline_async(url=url, full=full))


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
