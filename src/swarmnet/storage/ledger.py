"""SQLite intake ledger · run-by-run audit trail."""
from __future__ import annotations
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from swarmnet.config import LEDGER_PATH, ensure_dirs


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS extractions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    source TEXT NOT NULL,
    target TEXT NOT NULL,           -- e.g., ticker "DG" or county "harris-tx"
    status TEXT NOT NULL,           -- "ok" | "error"
    artifacts_count INTEGER DEFAULT 0,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    extraction_id INTEGER NOT NULL,
    path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    bytes INTEGER NOT NULL,
    fetched_at TEXT NOT NULL,
    source_url TEXT,
    FOREIGN KEY (extraction_id) REFERENCES extractions(id)
);

CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    record_type TEXT NOT NULL,      -- "tenant" | "comp" | "market" | "deed"
    record_slug TEXT NOT NULL,
    decision TEXT NOT NULL,         -- "approved" | "rejected" | "needs-edit"
    reviewer TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS ingestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    record_type TEXT NOT NULL,
    record_slug TEXT NOT NULL,
    ingested_path TEXT NOT NULL,
    hack_wiki_path TEXT,
    graph_upserted INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_extractions_source ON extractions(source);
CREATE INDEX IF NOT EXISTS idx_artifacts_sha ON artifacts(sha256);
CREATE INDEX IF NOT EXISTS idx_reviews_slug ON reviews(record_slug);
CREATE INDEX IF NOT EXISTS idx_ingestions_slug ON ingestions(record_slug);
"""


class Ledger:
    """SQLite-backed intake ledger."""

    def __init__(self, db_path: Path = LEDGER_PATH):
        ensure_dirs()
        self.db_path = db_path
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn() as cx:
            cx.executescript(SCHEMA_SQL)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        cx = sqlite3.connect(self.db_path)
        cx.row_factory = sqlite3.Row
        try:
            yield cx
            cx.commit()
        finally:
            cx.close()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    # ─── extractions ──────────────────────────────────────────────────
    def log_extraction(
        self,
        source: str,
        target: str,
        status: str = "ok",
        notes: str = "",
        artifacts_count: int = 0,
    ) -> int:
        with self._conn() as cx:
            cur = cx.execute(
                "INSERT INTO extractions (ts, source, target, status, artifacts_count, notes) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (self._now(), source, target, status, artifacts_count, notes),
            )
            return cur.lastrowid

    def log_artifact(
        self,
        extraction_id: int,
        path: str,
        sha256: str,
        bytes_: int,
        source_url: str = "",
    ) -> None:
        with self._conn() as cx:
            cx.execute(
                "INSERT INTO artifacts (extraction_id, path, sha256, bytes, fetched_at, source_url) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (extraction_id, path, sha256, bytes_, self._now(), source_url),
            )

    # ─── reviews ──────────────────────────────────────────────────────
    def log_review(
        self,
        record_type: str,
        record_slug: str,
        decision: str,
        reviewer: str = "donovan",
        notes: str = "",
    ) -> None:
        with self._conn() as cx:
            cx.execute(
                "INSERT INTO reviews (ts, record_type, record_slug, decision, reviewer, notes) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (self._now(), record_type, record_slug, decision, reviewer, notes),
            )

    # ─── ingestions ───────────────────────────────────────────────────
    def log_ingestion(
        self,
        record_type: str,
        record_slug: str,
        ingested_path: str,
        hack_wiki_path: str = "",
        graph_upserted: bool = False,
    ) -> None:
        with self._conn() as cx:
            cx.execute(
                "INSERT INTO ingestions (ts, record_type, record_slug, ingested_path, "
                "hack_wiki_path, graph_upserted) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    self._now(),
                    record_type,
                    record_slug,
                    ingested_path,
                    hack_wiki_path,
                    int(graph_upserted),
                ),
            )

    # ─── reads ────────────────────────────────────────────────────────
    def stats(self) -> dict:
        with self._conn() as cx:
            return {
                "extractions": cx.execute("SELECT COUNT(*) c FROM extractions").fetchone()["c"],
                "artifacts": cx.execute("SELECT COUNT(*) c FROM artifacts").fetchone()["c"],
                "reviews": cx.execute("SELECT COUNT(*) c FROM reviews").fetchone()["c"],
                "ingestions": cx.execute("SELECT COUNT(*) c FROM ingestions").fetchone()["c"],
            }
