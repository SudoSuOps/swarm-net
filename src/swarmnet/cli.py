"""SwarmNet CLI · extract · review · status · ui."""
from __future__ import annotations
import json
import sys
from pathlib import Path

import click

from swarmnet.config import ensure_dirs
from swarmnet.extractors.sec_edgar import SECEdgarExtractor
from swarmnet.storage import Ledger, list_pending_staging


@click.group()
def main():
    """SwarmNet · CRE data moat ingestion · provenance + HITL."""
    ensure_dirs()


@main.command()
@click.argument("source")
@click.option("--ticker", "-t", help="Ticker symbol (for sec-edgar)")
def extract(source: str, ticker: str | None):
    """Run an extractor for a target.

    Examples:
      swarmnet extract sec-edgar --ticker DG
    """
    if source == "sec-edgar":
        if not ticker:
            click.echo("--ticker required for sec-edgar", err=True)
            sys.exit(1)
        ext = SECEdgarExtractor()
        result = ext.extract(ticker)
        click.echo(json.dumps(result, indent=2, default=str))
    else:
        click.echo(f"unknown source: {source}", err=True)
        sys.exit(1)


@main.command()
def status():
    """Print the ledger stats."""
    ledger = Ledger()
    click.echo(json.dumps(ledger.stats(), indent=2))


@main.command()
@click.option("--type", "record_type", default=None, help="tenants | comps | markets | deeds")
def pending(record_type: str | None):
    """List pending /staging/ records awaiting review."""
    items = list(list_pending_staging(record_type))
    click.echo(f"pending: {len(items)} record(s)")
    for path in items:
        click.echo(f"  {path}")


@main.command()
def ui():
    """Launch the HITL review UI on swarmrails:7863."""
    from swarmnet.review.ui import launch_ui
    launch_ui()


if __name__ == "__main__":
    main()
