"""Market fundamentals schema · macro context for AIOV."""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from swarmnet.schema.comp import Provenance, SourceRef


class MarketMetrics(BaseModel):
    """The economic + cap rate metrics that backstop AIOV's valuation."""
    stnl_retail_cap_median_pct: Optional[float] = None
    stnl_retail_cap_range_low_pct: Optional[float] = None
    stnl_retail_cap_range_high_pct: Optional[float] = None
    shopping_center_vacancy_pct: Optional[float] = None
    shopping_center_rent_psf_usd: Optional[float] = None
    cre_loan_growth_yoy_pct: Optional[float] = None
    fed_funds_rate_pct: Optional[float] = None
    treasury_10yr_pct: Optional[float] = None
    cmbs_delinquency_pct: Optional[float] = None
    bank_concentration_top5: list[dict] = Field(default_factory=list)


class MarketDemographics(BaseModel):
    """ACS-derived population + income data."""
    population: Optional[int] = None
    population_growth_5yr_pct: Optional[float] = None
    median_household_income_usd: Optional[int] = None
    employment_growth_yoy_pct: Optional[float] = None


class Market(BaseModel):
    """A market snapshot for a specific period."""
    schema_version: str = "1.0"
    market_id: str  # e.g., "market/memphis-msa-2026-q1"
    market_slug: str  # e.g., "memphis-msa"
    market_name: str  # e.g., "Memphis MSA"
    period: str  # e.g., "2026-Q1"

    ts_extracted: datetime

    metrics: MarketMetrics
    demographics: MarketDemographics

    # provenance · per-source list since markets aggregate many sources
    sources: list[SourceRef] = Field(default_factory=list)
    review_status: str = "pending"

    tags: list[str] = Field(default_factory=list)
