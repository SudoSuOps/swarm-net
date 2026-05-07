"""SEC EDGAR extractor · the DG-IG fix in code.

Resolves ticker → CIK · pulls latest filings · extracts entity metadata.
Free · 10 req/s · no auth (just identifying User-Agent).

Produces a candidate Tenant record into /staging/tenants/<slug>.json
for senior-broker review (HITL discipline · per dmack doctrine).

Note: SEC EDGAR does NOT provide credit ratings. Ratings come from
S&P/Moody's/Fitch. EDGAR gives us:
  · entity name + CIK + ticker
  · 10-K/10-Q/8-K filings (raw business data + lease guarantor language
    can be parsed from filings)
  · subsidiaries list (Exhibit 21)

For ratings, we layer in:
  · InvestmentGrade.com curated table (free · scrape weekly)
  · Manual entry for bootstrap (Donovan provides DG=BBB)
  · Future: Bloomberg / S&P Capital IQ / Moody's APIs

This extractor handles the EDGAR side · returns a candidate Tenant
with filings paths + entity metadata. Ratings are merged in by the
transformer + reviewer.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from typing import Optional

from swarmnet.config import SEC_EDGAR_BASE, SEC_EDGAR_USER_AGENT, SEC_EDGAR_RATE_LIMIT_PER_SEC
from swarmnet.extractors._base import BaseExtractor, ExtractorError
from swarmnet.storage.filesystem import save_raw, save_staging
from swarmnet.schema.tenant import Tenant, TenantRating, GuarantorModel


# tenant slug curation · maps ticker → slug used in hack-wiki
TICKER_TO_SLUG = {
    "DG": "dollar-general",
    "DLTR": "dollar-tree",
    "WMT": "walmart",
    "TGT": "target",
    "SBUX": "starbucks",
    "MCD": "mcdonalds",
    "TSCO": "tractor-supply",
    "AZO": "autozone",
    "ORLY": "oreilly",
    "TXRH": "texas-roadhouse",
    "WAG": "walgreens",
    "WBA": "walgreens-boots",
    "CVS": "cvs",
    "ROST": "ross-stores",
    "BURL": "burlington",
}

# bootstrap rating table · until we wire S&P/Moody's APIs
# (safe to maintain by hand · curated from public company disclosures)
KNOWN_RATINGS = {
    "DG": [
        {"agency": "S&P", "rating": "BBB", "as_of": "2026-Q1", "investment_grade": True,
         "outlook": "negative", "source_doc": "S&P public ratings"},
        {"agency": "Moody's", "rating": "Baa3", "as_of": "2026-Q1", "investment_grade": True,
         "outlook": "negative", "source_doc": "Moody's downgrade Mar 2025 from Baa2"},
    ],
    "SBUX": [
        {"agency": "S&P", "rating": "BBB+", "as_of": "2026-Q1", "investment_grade": True,
         "outlook": "stable", "source_doc": "S&P public ratings"},
        {"agency": "Moody's", "rating": "Baa1", "as_of": "2026-Q1", "investment_grade": True,
         "outlook": "stable", "source_doc": "Moody's public ratings"},
    ],
    "TXRH": [
        {"agency": "S&P", "rating": "BB+", "as_of": "2026-Q1", "investment_grade": False,
         "outlook": "stable", "source_doc": "S&P public ratings"},
        {"agency": "Moody's", "rating": "Ba1", "as_of": "2026-Q1", "investment_grade": False,
         "outlook": "stable", "source_doc": "Moody's public ratings"},
    ],
    "TSCO": [
        {"agency": "S&P", "rating": "BBB", "as_of": "2026-Q1", "investment_grade": True,
         "outlook": "stable"},
    ],
    "AZO": [
        {"agency": "S&P", "rating": "BBB", "as_of": "2026-Q1", "investment_grade": True,
         "outlook": "stable"},
        {"agency": "Moody's", "rating": "Baa1", "as_of": "2026-Q1", "investment_grade": True},
    ],
}

# guarantor model table · bootstrap doctrine knowledge
# distinguishes 100%-corporate from franchised verticals
KNOWN_GUARANTOR_MODELS = {
    "DG":   {"type": "corporate_parent", "franchisee_pct": 0,
             "notes": "100% corporate-operated · always corporate guaranty on lease"},
    "SBUX": {"type": "corporate_parent", "franchisee_pct": 0,
             "notes": "Company-operated stores · licensed (not franchised) for the rest"},
    "TXRH": {"type": "corporate_parent", "franchisee_pct": 5,
             "notes": "~95% corporate · ~5% franchise · verify on a per-deal basis"},
    "TSCO": {"type": "corporate_parent", "franchisee_pct": 0},
    "AZO":  {"type": "corporate_parent", "franchisee_pct": 0},
    "MCD":  {"type": "franchisee", "franchisee_pct": 95,
             "notes": "~95% franchisee-operated · lease guaranty usually franchisee LLC"},
    "BK":   {"type": "franchisee", "franchisee_pct": 99,
             "notes": "~99% franchisee · CRITICAL to verify guarantor entity"},
}


class SECEdgarExtractor(BaseExtractor):
    name = "sec-edgar"
    rate_limit_per_sec = float(SEC_EDGAR_RATE_LIMIT_PER_SEC)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._ticker_cik_map: Optional[dict] = None

    # ─── public API ───────────────────────────────────────────────
    def extract(self, ticker: str) -> dict:
        """Pull entity metadata + filings list + bootstrap ratings.

        target = ticker (e.g., "DG")
        """
        ticker = ticker.upper()
        ext_id = self.ledger.log_extraction(self.name, ticker, status="ok")

        try:
            cik = self._resolve_cik(ticker)
            entity = self._fetch_company_facts(cik)

            # save raw entity facts
            raw_path, sha = save_raw(
                source=self.name,
                sub_path=f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}/{ticker}-companyfacts",
                content=json.dumps(entity, indent=2).encode(),
                ext="json",
            )
            self.ledger.log_artifact(
                ext_id, str(raw_path), sha, len(json.dumps(entity)),
                source_url=f"{SEC_EDGAR_BASE}/api/xbrl/companyfacts/CIK{cik}.json",
            )

            # build canonical tenant record
            tenant = self._build_tenant(ticker, cik, entity, raw_path)

            # save to staging for HITL review
            slug = tenant.tenant_slug
            staging_path = save_staging(
                "tenants",
                slug,
                tenant.model_dump(mode="json", exclude_none=False),
            )

            # update ledger artifact count
            with self.ledger._conn() as cx:
                cx.execute(
                    "UPDATE extractions SET artifacts_count = ? WHERE id = ?",
                    (1, ext_id),
                )

            return {
                "extraction_id": ext_id,
                "ticker": ticker,
                "cik": cik,
                "tenant_slug": slug,
                "raw_path": str(raw_path),
                "staging_path": str(staging_path),
                "is_investment_grade": tenant.is_investment_grade,
                "ratings_count": len(tenant.ratings),
            }
        except Exception as e:
            self.ledger.log_extraction(self.name, ticker, status="error", notes=str(e))
            raise ExtractorError(f"sec-edgar extraction for {ticker} failed: {e}") from e

    # ─── CIK resolution ───────────────────────────────────────────
    def _resolve_cik(self, ticker: str) -> str:
        """Resolve ticker → padded 10-digit CIK string."""
        if self._ticker_cik_map is None:
            url = f"https://www.sec.gov/files/company_tickers.json"
            resp = self._http_get(url, headers={"User-Agent": SEC_EDGAR_USER_AGENT})
            data = resp.json()
            self._ticker_cik_map = {
                v["ticker"].upper(): str(v["cik_str"]).zfill(10)
                for v in data.values()
            }
        if ticker not in self._ticker_cik_map:
            raise ExtractorError(f"ticker {ticker} not found in SEC ticker map")
        return self._ticker_cik_map[ticker]

    def _fetch_company_facts(self, cik: str) -> dict:
        """Fetch the company-facts JSON · entity name + recent filings."""
        url = f"{SEC_EDGAR_BASE}/api/xbrl/companyfacts/CIK{cik}.json"
        resp = self._http_get(url, headers={"User-Agent": SEC_EDGAR_USER_AGENT})
        return resp.json()

    # ─── tenant builder ──────────────────────────────────────────
    def _build_tenant(self, ticker: str, cik: str, entity_data: dict, raw_path) -> Tenant:
        """Compose a canonical Tenant from EDGAR data + curated bootstrap tables."""
        slug = TICKER_TO_SLUG.get(ticker, ticker.lower())

        # name from entity data
        name = entity_data.get("entityName", ticker)

        # ratings · bootstrap from curated table (TODO · wire S&P/Moody's APIs)
        ratings = [TenantRating(**r) for r in KNOWN_RATINGS.get(ticker, [])]

        # guarantor model · bootstrap from curated table
        gm_data = KNOWN_GUARANTOR_MODELS.get(ticker, {"type": "unknown"})
        guarantor_model = GuarantorModel(**gm_data)

        return Tenant(
            tenant_id=f"tenant/{slug}",
            tenant_slug=slug,
            tenant_name=name,
            ticker=ticker,
            cik=cik,
            ts_extracted=datetime.now(timezone.utc),
            ratings=ratings,
            guarantor_model=guarantor_model,
            filings={"company_facts": str(raw_path)},
            tags=[
                "public-co",
                "ig" if any(r.investment_grade for r in ratings) else "non-ig",
                "stnl-tenant",
            ],
        )
