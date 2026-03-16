from __future__ import annotations

import json
import sys

import click
from rich.console import Console
from rich.table import Table

from src.pipeline import load_report, run_pipeline

console = Console()


def _render_human(report: dict) -> None:
    verdict = report["verdict"]
    trust_score = report["trust_score"]

    console.print(f"[bold]HypeCheck Report[/bold] :: [cyan]{report['url']}[/cyan]")
    console.print(f"Verdict: [bold]{verdict}[/bold] | Trust score: [bold]{trust_score}/100[/bold]")
    console.print(report["summary"])

    table = Table(title="Stage Scores")
    table.add_column("Stage")
    table.add_column("Value")
    table.add_row("Code Audit Risk", str(report["stages"]["code_audit"]["risk"]))
    table.add_row("Claims Verified", str(report["stages"]["claims"]["score"]))
    table.add_row("Network Coordination", str(report["stages"]["network"]["coordination"]))
    table.add_row("Timeline Clustering", str(report["stages"]["timeline"]["clustering"]))
    console.print(table)

    if report.get("evidence"):
        console.print("\n[bold]Evidence[/bold]")
        for item in report["evidence"][:8]:
            console.print(f"- {item}")

    console.print(f"\nSaved report id: [green]{report.get('report_id', 'n/a')}[/green]")


@click.command(name="check")
@click.argument("urls", nargs=-1, required=True)
@click.option("--full", "full", is_flag=True, help="Include full raw stage output.")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
def check_command(urls: tuple[str, ...], full: bool, as_json: bool) -> None:
    """Quick check: hypecheck <url> [<url> ...] [--full] [--json]."""
    tweet_urls = [u for u in urls if "x.com/" in u or "twitter.com/" in u]
    non_tweet = [u for u in urls if u not in tweet_urls]
    if len(tweet_urls) < 3 and not non_tweet:
        console.print(
            "[red]⚠ Minimum 3 tweet URLs required for campaign analysis.[/red]\n"
            "Single tweets can't reveal coordination patterns — paste the full thread."
        )
        raise SystemExit(1)
    report = run_pipeline(urls=list(urls), full=full)
    if as_json:
        click.echo(json.dumps(report, indent=2, ensure_ascii=True))
        return
    _render_human(report)


@click.command(name="report")
@click.argument("report_id")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
def report_command(report_id: str, as_json: bool) -> None:
    """View a saved report by id."""
    report = load_report(report_id)
    if as_json:
        click.echo(json.dumps(report, indent=2, ensure_ascii=True))
        return
    _render_human(report)


def main() -> None:
    """
    Dispatch command while keeping `hypecheck <url>` as the main entry point.
    Also supports: `hypecheck report <report-id>`.
    """
    argv = sys.argv[1:]
    if not argv:
        click.echo("Usage: hypecheck <url> [<url> ...] [--full] [--json] | hypecheck report <report-id> [--json]")
        raise SystemExit(2)

    if argv[0] == "report":
        report_command.main(args=argv[1:], prog_name="hypecheck report", standalone_mode=True)
        return

    check_command.main(args=argv, prog_name="hypecheck", standalone_mode=True)


if __name__ == "__main__":
    main()
