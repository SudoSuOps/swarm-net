"""FFIEC CDR (Call Reports) extractor · STUB.

Bulk XBRL downloads · free.
URL: https://cdr.ffiec.gov/public/PWS/DownloadBulkData.aspx

Phase 2B work: parse Call Report XBRL · extract per-bank CRE concentration
ratios · feed Market.metrics.bank_concentration_top5.

The 1,374 banks above 300% CRE concentration (per CRE debt wall thesis)
are the lender-pullback signal we want to track quarter-by-quarter.

NOT YET IMPLEMENTED.
"""
from __future__ import annotations

from swarmnet.extractors._base import BaseExtractor, ExtractorError


class FFIECCDRExtractor(BaseExtractor):
    name = "ffiec-cdr"
    rate_limit_per_sec = 1.0

    def extract(self, target: str) -> dict:
        raise ExtractorError(
            "ffiec-cdr extractor not yet implemented · Phase 2B work. "
            "Bulk XBRL parser pending."
        )
