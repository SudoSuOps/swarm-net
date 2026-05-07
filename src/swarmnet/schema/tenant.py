"""Tenant credit schema · the DG-IG-fix in code.

Per dmack doctrine (🛰️ DATA SOURCING · slice 3):
The rating field is two-keyed:
  {rating: "BBB", source: "S&P", as_of: "2026-Q1",
   guarantor_entity: "Dollar General Corporation",
   guarantor_type: "corporate_parent"}

If guarantor_type != corporate_parent → route to franchisee credit path.
"""
from __future__ import annotations
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field, HttpUrl


class TenantRating(BaseModel):
    """A single agency rating with full provenance."""
    agency: Literal["S&P", "Moody's", "Fitch"]
    rating: str  # e.g., "BBB", "Baa2", "BB+"
    as_of: str  # e.g., "2026-Q1" or ISO date
    investment_grade: bool
    outlook: Optional[Literal["positive", "stable", "negative", "developing"]] = None
    source_url: Optional[str] = None
    source_sha256: Optional[str] = None
    source_doc: Optional[str] = None  # e.g., "10-K filed 2026-03-10"


class GuarantorModel(BaseModel):
    """How does this tenant typically structure its lease guaranty?"""
    type: Literal[
        "corporate_parent",       # always signs · DG, Walmart
        "franchisee",             # franchisee LLC signs · BK, McDonald's franchised
        "operating_subsidiary",   # named OpCo · varies
        "personal",               # PG · small operators
        "mixed",                  # depends on the deal · investigate per
        "unknown",
    ]
    franchisee_pct: Optional[float] = Field(default=None, ge=0, le=100)
    notes: Optional[str] = None


class Tenant(BaseModel):
    """Canonical tenant credit + guarantor profile."""
    schema_version: str = "1.0"
    tenant_id: str  # e.g., "tenant/dollar-general"
    tenant_slug: str  # e.g., "dollar-general"
    tenant_name: str  # e.g., "Dollar General Corporation"
    ticker: Optional[str] = None
    cik: Optional[str] = None  # SEC Central Index Key

    # status
    ts_extracted: datetime
    ts_event: Optional[datetime] = None  # the rating-date or filing-date this snapshot reflects

    # ratings (multi-agency)
    ratings: list[TenantRating] = Field(default_factory=list)

    # guarantor model
    guarantor_model: GuarantorModel

    # filings (paths in /raw/)
    filings: dict[str, str] = Field(default_factory=dict)  # {"latest_10k": path, "latest_10q": path}

    # tags
    tags: list[str] = Field(default_factory=list)

    # convenience properties
    @property
    def is_investment_grade(self) -> bool:
        """True if ANY agency rates this tenant IG."""
        return any(r.investment_grade for r in self.ratings)

    @property
    def latest_sp_rating(self) -> Optional[str]:
        sp = [r for r in self.ratings if r.agency == "S&P"]
        return sp[0].rating if sp else None
