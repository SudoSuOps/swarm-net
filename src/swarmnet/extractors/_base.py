"""Base extractor · shared retry · rate-limiting · provenance."""
from __future__ import annotations
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone

import httpx

from swarmnet.storage.ledger import Ledger


class ExtractorError(Exception):
    pass


class BaseExtractor(ABC):
    """All extractors inherit from this."""

    name: str = "base"  # override
    rate_limit_per_sec: float = 5.0  # override per source

    def __init__(self, ledger: Ledger | None = None) -> None:
        self.ledger = ledger or Ledger()
        self._last_request_ts: float = 0.0

    # ─── abstract ─────────────────────────────────────────────────
    @abstractmethod
    def extract(self, target: str) -> dict:
        """Run extraction for `target` (e.g., a ticker, county, etc.).

        Returns a result dict with extraction metadata.
        Subclasses persist raw + staging artifacts as side effects.
        """
        ...

    # ─── shared utilities ─────────────────────────────────────────
    def _throttle(self) -> None:
        """Self-rate-limit · respects per-source rate limit."""
        gap = 1.0 / self.rate_limit_per_sec
        elapsed = time.monotonic() - self._last_request_ts
        if elapsed < gap:
            time.sleep(gap - elapsed)
        self._last_request_ts = time.monotonic()

    def _http_get(self, url: str, headers: dict | None = None, **kwargs) -> httpx.Response:
        """GET with throttle + retry."""
        self._throttle()
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                    resp = client.get(url, headers=headers, **kwargs)
                    if resp.status_code == 200:
                        return resp
                    if resp.status_code == 429:  # rate limited
                        time.sleep(2 ** attempt)
                        continue
                    resp.raise_for_status()
            except httpx.HTTPError as e:
                last_exc = e
                time.sleep(2 ** attempt)
        raise ExtractorError(f"GET {url} failed after 3 attempts · last={last_exc}")

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()
