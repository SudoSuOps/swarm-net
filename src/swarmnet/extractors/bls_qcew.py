"""BLS QCEW (Quarterly Census of Employment and Wages) extractor · STUB.

Bulk CSV downloads · free · no API key.
URL pattern: https://data.bls.gov/cew/data/files/<year>/csv/<year>_qtrly_singlefile.zip

Phase 2B work: parse the bulk ZIP · filter to county-level NAICS per market ·
produce Market.metrics.employment_growth_yoy_pct.

NOT YET IMPLEMENTED.
"""
from __future__ import annotations

from swarmnet.extractors._base import BaseExtractor, ExtractorError


class BLSQCEWExtractor(BaseExtractor):
    name = "bls-qcew"
    rate_limit_per_sec = 1.0

    def extract(self, target: str) -> dict:
        raise ExtractorError(
            "bls-qcew extractor not yet implemented · Phase 2B work. "
            "Bulk CSV download + county/NAICS filter pending."
        )
