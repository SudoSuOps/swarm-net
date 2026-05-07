"""SwarmNet config · paths · API keys · rate limits."""
from __future__ import annotations
import os
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────
# storage roots (override with SWARMNET_DATA_ROOT env)
# ──────────────────────────────────────────────────────────────────────
DATA_ROOT = Path(os.environ.get("SWARMNET_DATA_ROOT", "/data1/swarmnet-intake"))
RAW_DIR = DATA_ROOT / "_raw"
STAGING_DIR = DATA_ROOT / "_staging"
INGESTED_DIR = DATA_ROOT / "_ingested"
ARCHIVED_DIR = DATA_ROOT / "_archived"
LOGS_DIR = DATA_ROOT / "_logs"
REVIEW_QUEUE_DIR = DATA_ROOT / "_review-queue"

LEDGER_PATH = LOGS_DIR / "intake.sqlite"

# hack-wiki + Kuzu integration
HACK_WIKI_DIR = Path(os.environ.get("HACK_WIKI_DIR", "/data1/hack-wiki"))
KUZU_DB_PATH = os.environ.get("KUZU_DB_PATH", "/data2/swarmdev/hack_graph.kuzu")

# ──────────────────────────────────────────────────────────────────────
# extractor config
# ──────────────────────────────────────────────────────────────────────
SEC_EDGAR_BASE = "https://data.sec.gov"
SEC_EDGAR_USER_AGENT = os.environ.get(
    "SEC_EDGAR_USER_AGENT",
    "Swarm and Bee LLC contact@swarmandbee.ai",  # SEC requires identifying UA
)
SEC_EDGAR_RATE_LIMIT_PER_SEC = 8  # SEC allows 10/sec · we self-limit at 8

FRED_API_BASE = "https://api.stlouisfed.org/fred"
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")

CENSUS_API_BASE = "https://api.census.gov/data"
CENSUS_API_KEY = os.environ.get("CENSUS_API_KEY", "")

# ──────────────────────────────────────────────────────────────────────
# review UI
# ──────────────────────────────────────────────────────────────────────
REVIEW_UI_PORT = int(os.environ.get("SWARMNET_REVIEW_PORT", "7863"))
REVIEW_UI_HOST = os.environ.get("SWARMNET_REVIEW_HOST", "0.0.0.0")


def ensure_dirs() -> None:
    """Create all storage directories if they don't exist."""
    for d in (RAW_DIR, STAGING_DIR, INGESTED_DIR, ARCHIVED_DIR, LOGS_DIR, REVIEW_QUEUE_DIR):
        d.mkdir(parents=True, exist_ok=True)
