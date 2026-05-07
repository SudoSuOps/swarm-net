"""Census ACS (American Community Survey) extractor.

Free · API key required (free at https://api.census.gov/data/key_signup.html).
Pulls demographics by MSA (and other geographies) · feeds Market schema.

Default variables (5-year ACS · most stable):
  · B01003_001E    Total population
  · B19013_001E    Median household income
  · B25001_001E    Total housing units
  · B23025_005E    Civilian labor force unemployed (for unemployment rate calc)
  · B23025_002E    Civilian labor force total
"""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from typing import Optional

from swarmnet.config import CENSUS_API_BASE, CENSUS_API_KEY
from swarmnet.extractors._base import BaseExtractor, ExtractorError
from swarmnet.storage.filesystem import save_raw, save_staging
from swarmnet.schema.market import Market, MarketMetrics, MarketDemographics
from swarmnet.schema.comp import SourceRef


# CRE-relevant ACS variables
DEFAULT_VARS = [
    "NAME",
    "B01003_001E",   # total population
    "B19013_001E",   # median household income
    "B25001_001E",   # total housing units
    "B23025_002E",   # civilian labor force
    "B23025_005E",   # civilian labor force unemployed
]


# common MSA → CBSA code map (extend as needed)
MSA_TO_CBSA = {
    "memphis-msa":       "32820",  # Memphis, TN-MS-AR
    "ingleside-tx":      "18580",  # Corpus Christi MSA (Ingleside is in this MSA)
    "del-rio-tx":        None,     # non-MSA · use county
    "woodward-ok":       None,     # non-MSA · use county
    "dallas-msa":        "19100",
    "houston-msa":       "26420",
    "austin-msa":        "12420",
    "san-antonio-msa":   "41700",
    "miami-msa":         "33100",
    "tampa-msa":         "45300",
    "orlando-msa":       "36740",
    "atlanta-msa":       "12060",
    "nashville-msa":     "34980",
    "charlotte-msa":     "16740",
    "phoenix-msa":       "38060",
    "denver-msa":        "19740",
}


class CensusExtractor(BaseExtractor):
    name = "census-acs"
    rate_limit_per_sec = 4.0

    def __init__(self, *args, api_key: Optional[str] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.api_key = api_key or CENSUS_API_KEY or os.environ.get("CENSUS_API_KEY", "")
        if not self.api_key:
            raise ExtractorError(
                "CENSUS_API_KEY not set. Get a free key at "
                "https://api.census.gov/data/key_signup.html"
            )

    # ─── public API ────────────────────────────────────────────────
    def extract(self, market_slug: str = "memphis-msa", year: int = 2023) -> dict:
        """Pull ACS demographics for an MSA.

        target = market slug (e.g., "memphis-msa")
        """
        ext_id = self.ledger.log_extraction(self.name, market_slug, status="ok")

        try:
            cbsa = MSA_TO_CBSA.get(market_slug)
            if not cbsa:
                raise ExtractorError(
                    f"market {market_slug} has no CBSA code mapped. "
                    f"Add to MSA_TO_CBSA in census.py."
                )

            data = self._fetch_acs_msa(year, cbsa)

            # save raw
            raw_path, sha = save_raw(
                source=self.name,
                sub_path=f"{year}/{market_slug}-cbsa-{cbsa}",
                content=json.dumps(data, indent=2).encode(),
                ext="json",
            )
            self.ledger.log_artifact(
                ext_id, str(raw_path), sha, len(json.dumps(data)),
                source_url=f"{CENSUS_API_BASE}/{year}/acs/acs5",
            )

            market = self._build_market(market_slug, year, data, raw_path)
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
                    (1, ext_id),
                )

            return {
                "extraction_id": ext_id,
                "market_slug": market_slug,
                "year": year,
                "cbsa": cbsa,
                "staging_path": str(staging_path),
                "population": market.demographics.population,
                "median_hh_income": market.demographics.median_household_income_usd,
            }
        except Exception as e:
            self.ledger.log_extraction(self.name, market_slug, status="error", notes=str(e))
            raise ExtractorError(f"Census extraction for {market_slug} failed: {e}") from e

    # ─── ACS fetcher ───────────────────────────────────────────────
    def _fetch_acs_msa(self, year: int, cbsa: str) -> list[list]:
        """Fetch ACS 5-year for a specific CBSA (MSA)."""
        var_str = ",".join(DEFAULT_VARS)
        url = (
            f"{CENSUS_API_BASE}/{year}/acs/acs5"
            f"?get={var_str}"
            f"&for=metropolitan%20statistical%20area/micropolitan%20statistical%20area:{cbsa}"
            f"&key={self.api_key}"
        )
        resp = self._http_get(url)
        return resp.json()

    # ─── market builder ────────────────────────────────────────────
    def _build_market(
        self, market_slug: str, year: int, data: list[list], raw_path
    ) -> Market:
        now = datetime.now(timezone.utc)
        period = f"{year}-ACS5"

        # Census API returns [[headers], [row1], ...]
        if not data or len(data) < 2:
            raise ExtractorError(f"Census returned no data for {market_slug}")

        headers = data[0]
        row = data[1]
        idx = {h: i for i, h in enumerate(headers)}

        def _f(var: str) -> Optional[float]:
            try:
                v = row[idx[var]]
                return float(v) if v not in (None, "", "null") else None
            except (KeyError, ValueError, IndexError):
                return None

        population = int(_f("B01003_001E") or 0) or None
        median_income = int(_f("B19013_001E") or 0) or None

        # unemployment rate
        labor_force = _f("B23025_002E")
        unemployed = _f("B23025_005E")
        unemployment_pct = None
        if labor_force and labor_force > 0 and unemployed is not None:
            unemployment_pct = round(unemployed / labor_force * 100, 2)

        market_name = (row[idx["NAME"]] if "NAME" in idx else market_slug.title())

        demographics = MarketDemographics(
            population=population,
            median_household_income_usd=median_income,
        )

        sources = [
            SourceRef(
                name=f"Census ACS 5-Year {year}",
                url=f"{CENSUS_API_BASE}/{year}/acs/acs5",
                artifact_path=str(raw_path),
                fetched_at=now,
            )
        ]

        return Market(
            market_id=f"market/{market_slug}-{period}",
            market_slug=market_slug,
            market_name=market_name,
            period=period,
            ts_extracted=now,
            metrics=MarketMetrics(),  # filled by FRED extractor
            demographics=demographics,
            sources=sources,
            tags=["msa", "demographics", "census", "acs5"],
        )
