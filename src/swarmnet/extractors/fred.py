"""FRED (Federal Reserve Economic Data) extractor.

Free · API-key required (free signup at fred.stlouisfed.org/docs/api/api_key.html).
Pulls time-series economic data · feeds Market schema.

CRE-relevant series we extract by default:
  · DGS10               10-Year Treasury Constant Maturity Rate
  · DFF                 Effective Federal Funds Rate
  · SOFR30DAYAVG        SOFR 30-day average
  · REALLN              Real Estate Loans · all commercial banks
  · BUSLOANS            Commercial and Industrial Loans
  · DRTSCILM            Delinquency Rate · CRE Loans (Booked in Domestic Offices)
  · DRSDCRELLNS         Delinquency Rate · STNL CRE
  · CSUSHPINSA          Case-Shiller Home Price Index (residential proxy)
"""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from typing import Optional

from swarmnet.config import FRED_API_BASE, FRED_API_KEY
from swarmnet.extractors._base import BaseExtractor, ExtractorError
from swarmnet.storage.filesystem import save_raw, save_staging
from swarmnet.schema.market import Market, MarketMetrics, MarketDemographics
from swarmnet.schema.comp import SourceRef


# the default CRE-relevant series we always pull · series IDs verified
DEFAULT_SERIES = [
    "DGS10",                # 10-Year Treasury Constant Maturity Rate
    "DFF",                  # Federal Funds Effective Rate
    "REALLN",               # Real Estate Loans · All Commercial Banks
    "BUSLOANS",             # Commercial and Industrial Loans
    "DRBLACBN",             # Delinquency Rate on Loans Secured by Real Estate
    "DRCLACBS",             # Delinquency Rate on CRE Loans (booked in domestic offices)
    "CSUSHPINSA",           # Case-Shiller National HPI
]

# map FRED series → Market.metrics field name (best-effort)
SERIES_TO_METRIC = {
    "DGS10": "treasury_10yr_pct",
    "DFF": "fed_funds_rate_pct",
    "DRCLACBS": "cmbs_delinquency_pct",  # CRE delinquency · use as proxy
}


class FredExtractor(BaseExtractor):
    name = "fred"
    rate_limit_per_sec = 5.0  # FRED is generous

    def __init__(self, *args, api_key: Optional[str] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.api_key = api_key or FRED_API_KEY or os.environ.get("FRED_API_KEY", "")
        if not self.api_key:
            raise ExtractorError(
                "FRED_API_KEY not set. Get a free key at "
                "https://fred.stlouisfed.org/docs/api/api_key.html"
            )

    # ─── public API ────────────────────────────────────────────────
    def extract(self, target: str = "us-national") -> dict:
        """Pull DEFAULT_SERIES · build a national-level Market record.

        target = market slug (default: "us-national")
        """
        ext_id = self.ledger.log_extraction(self.name, target, status="ok")
        observations: dict[str, list] = {}
        artifact_paths: list[tuple[str, str]] = []

        failed_series: list[str] = []
        try:
            for series_id in DEFAULT_SERIES:
                # per-series resilience · one bad series doesn't kill the run
                try:
                    obs = self._fetch_series_latest(series_id, limit=4)
                except Exception as e:
                    print(f"  ⚠ skip {series_id}: {type(e).__name__}")
                    failed_series.append(series_id)
                    continue

                observations[series_id] = obs

                raw_path, sha = save_raw(
                    source=self.name,
                    sub_path=f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}/{series_id}",
                    content=json.dumps(obs, indent=2).encode(),
                    ext="json",
                )
                self.ledger.log_artifact(
                    ext_id, str(raw_path), sha, len(json.dumps(obs)),
                    source_url=f"{FRED_API_BASE}/series/observations?series_id={series_id}",
                )
                artifact_paths.append((series_id, str(raw_path)))

            # build Market record with macro metrics
            market = self._build_market(target, observations, artifact_paths)

            slug = market.market_slug
            period = market.period
            staging_path = save_staging(
                "markets",
                f"{slug}-{period}",
                market.model_dump(mode="json", exclude_none=False),
            )

            with self.ledger._conn() as cx:
                cx.execute(
                    "UPDATE extractions SET artifacts_count = ? WHERE id = ?",
                    (len(artifact_paths), ext_id),
                )

            return {
                "extraction_id": ext_id,
                "target": target,
                "series_pulled": len(observations),
                "series_failed": failed_series,
                "staging_path": str(staging_path),
                "metrics_filled": [k for k in SERIES_TO_METRIC if k in observations],
            }
        except Exception as e:
            self.ledger.log_extraction(self.name, target, status="error", notes=str(e))
            raise ExtractorError(f"FRED extraction for {target} failed: {e}") from e

    # ─── series fetcher ────────────────────────────────────────────
    def _fetch_series_latest(self, series_id: str, limit: int = 4) -> list[dict]:
        """Fetch the most-recent N observations for a series."""
        url = (
            f"{FRED_API_BASE}/series/observations"
            f"?series_id={series_id}&api_key={self.api_key}"
            f"&file_type=json&sort_order=desc&limit={limit}"
        )
        resp = self._http_get(url)
        data = resp.json()
        return data.get("observations", [])

    # ─── market builder ────────────────────────────────────────────
    def _build_market(
        self,
        target: str,
        observations: dict[str, list],
        artifact_paths: list[tuple[str, str]],
    ) -> Market:
        """Build a national-level Market record from FRED observations."""
        now = datetime.now(timezone.utc)
        # current period · YYYY-Qn
        q = (now.month - 1) // 3 + 1
        period = f"{now.year}-Q{q}"

        # extract scalar values from FRED observations · use most recent valid
        metrics_kwargs: dict = {}
        for series_id, field in SERIES_TO_METRIC.items():
            obs = observations.get(series_id, [])
            for o in obs:
                v = o.get("value", ".")
                if v != "." and v != "":
                    try:
                        metrics_kwargs[field] = float(v)
                        break
                    except ValueError:
                        continue

        # CRE loan growth (REALLN year-over-year)
        realln = observations.get("REALLN", [])
        if len(realln) >= 2:
            try:
                latest = float(realln[0]["value"])
                prior = float(realln[3]["value"]) if len(realln) >= 4 else float(realln[-1]["value"])
                if prior > 0:
                    metrics_kwargs["cre_loan_growth_yoy_pct"] = round(
                        (latest - prior) / prior * 100, 2
                    )
            except (ValueError, KeyError, IndexError):
                pass

        sources = [
            SourceRef(
                name=f"FRED · {series_id}",
                url=f"{FRED_API_BASE}/series/observations?series_id={series_id}",
                artifact_path=path,
                fetched_at=now,
            )
            for series_id, path in artifact_paths
        ]

        return Market(
            market_id=f"market/{target}-{period}",
            market_slug=target,
            market_name=target.replace("-", " ").title(),
            period=period,
            ts_extracted=now,
            metrics=MarketMetrics(**metrics_kwargs),
            demographics=MarketDemographics(),  # populated by Census extractor
            sources=sources,
            tags=["macro", "fred", "national" if target == "us-national" else "msa"],
        )
