"""Filesystem storage · raw / staging / ingested / archived.

PROVENANCE-FIRST · every artifact is sha256-stamped.
HITL-GATED · /staging/ is the human review queue.
"""
from __future__ import annotations
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from swarmnet.config import RAW_DIR, STAGING_DIR, INGESTED_DIR, ARCHIVED_DIR, ensure_dirs


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def save_raw(source: str, sub_path: str, content: bytes, ext: str = "json") -> tuple[Path, str]:
    """Save a raw artifact under data/_raw/<source>/<sub_path>.<ext>.

    Returns (path, sha256).
    """
    ensure_dirs()
    out = RAW_DIR / source / f"{sub_path}.{ext}"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(content)
    return out, sha256_file(out)


def save_staging(record_type: str, slug: str, payload: dict) -> Path:
    """Save a parsed candidate to /staging/<record_type>/<slug>.json.

    record_type · "tenants" | "comps" | "markets" | "deeds"
    """
    ensure_dirs()
    out = STAGING_DIR / record_type / f"{slug}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, default=str))
    return out


def list_pending_staging(record_type: Optional[str] = None) -> Iterator[Path]:
    """Yield staging entries pending review.

    A staging entry is "pending" if the record's provenance.review_status == "pending".
    Filter by record_type if specified.
    """
    ensure_dirs()
    if record_type:
        roots = [STAGING_DIR / record_type]
    else:
        roots = [d for d in STAGING_DIR.iterdir() if d.is_dir()]

    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.json")):
            try:
                rec = json.loads(path.read_text())
            except Exception:
                continue
            # tenants / markets keep `review_status` at top level (sources is a list)
            # comps keep it under provenance
            status = (
                rec.get("provenance", {}).get("review_status")
                or rec.get("review_status")
                or "pending"
            )
            if status == "pending":
                yield path


def promote_to_ingested(staging_path: Path, reviewer: str = "donovan", notes: str = "") -> Path:
    """Move a staging record to /ingested/ · stamps approval metadata."""
    ensure_dirs()
    rec = json.loads(staging_path.read_text())
    now = datetime.now(timezone.utc).isoformat()

    # write approval into provenance · works for comps and tenants
    if "provenance" in rec:
        rec["provenance"]["review_status"] = "approved"
        rec["provenance"]["human_reviewer"] = reviewer
        rec["provenance"]["review_ts"] = now
        rec["provenance"]["review_notes"] = notes
    else:
        # markets-style: top-level fields
        rec["review_status"] = "approved"
        rec["human_reviewer"] = reviewer
        rec["review_ts"] = now
        rec["review_notes"] = notes

    rel = staging_path.relative_to(STAGING_DIR)
    out = INGESTED_DIR / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rec, indent=2, default=str))
    staging_path.unlink()
    return out


def archive_rejected(staging_path: Path, reviewer: str = "donovan", reason: str = "") -> Path:
    """Move a staging record to /archived/ with rejection rationale."""
    ensure_dirs()
    rec = json.loads(staging_path.read_text())
    now = datetime.now(timezone.utc).isoformat()

    if "provenance" in rec:
        rec["provenance"]["review_status"] = "rejected"
        rec["provenance"]["human_reviewer"] = reviewer
        rec["provenance"]["review_ts"] = now
        rec["provenance"]["review_notes"] = reason
    else:
        rec["review_status"] = "rejected"
        rec["human_reviewer"] = reviewer
        rec["review_ts"] = now
        rec["review_notes"] = reason

    rel = staging_path.relative_to(STAGING_DIR)
    out = ARCHIVED_DIR / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rec, indent=2, default=str))
    staging_path.unlink()
    return out
