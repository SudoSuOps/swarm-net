"""Comp schema · the JSON Donovan asked about.

Per dmack 🛠️ SWARMNET ETL ARCHITECTURE doctrine:
Each comp is a self-contained JSON with 4 sections:
  1. SUBJECT      tenant · asset_type · address · market · sf · acres
  2. TRANSACTION  price · NOI · cap_rate · lease_term · bumps · guaranty
  3. PROVENANCE   source URL + sha256 + fetched_at · review status
  4. TAGS         stnl · tenant · market · 1031-eligible · ig-tenant
"""
from __future__ import annotations
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field


class SourceRef(BaseModel):
    """Reference to a source artifact with provenance hash."""
    name: str
    url: Optional[str] = None
    artifact_path: Optional[str] = None  # path under data/_raw/
    artifact_sha256: Optional[str] = None
    fetched_at: Optional[datetime] = None


class Provenance(BaseModel):
    """Provenance + review state for any record."""
    primary_source: SourceRef
    secondary_sources: list[SourceRef] = Field(default_factory=list)
    extraction_method: str  # e.g., "PDF table parse · pdfplumber"
    confidence: float = Field(default=1.0, ge=0, le=1)
    human_reviewer: Optional[str] = None
    review_status: Literal["pending", "approved", "needs-edit", "rejected"] = "pending"
    review_ts: Optional[datetime] = None
    review_notes: Optional[str] = None


class Guaranty(BaseModel):
    type: Literal[
        "corporate_parent", "franchisee", "operating_subsidiary",
        "personal", "mixed", "unknown",
    ]
    entity: Optional[str] = None  # e.g., "Dollar General Corporation"
    notes: Optional[str] = None


class CompSubject(BaseModel):
    """The property/deal being compared."""
    tenant_slug: str
    asset_type: str  # e.g., "STNL retail", "STNL restaurant", "Industrial"
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    market_slug: Optional[str] = None  # e.g., "memphis-msa"
    building_sf: Optional[int] = None
    lot_acres: Optional[float] = None
    year_built: Optional[int] = None


class CompTransaction(BaseModel):
    """The deal economics."""
    price_usd: float
    noi_usd: Optional[float] = None
    cap_rate_pct: Optional[float] = None
    lease_term_years_remaining: Optional[float] = None
    rent_bumps: Optional[str] = None  # e.g., "10% every 5 years"
    guaranty: Optional[Guaranty] = None


class Comp(BaseModel):
    """A single comparable transaction · the AIOV building block."""
    schema_version: str = "1.0"
    comp_id: str  # e.g., "comp/2026-q1/dollar-general-memphis-tn-001"
    type: Literal["closed_comp", "on_market", "asking", "appraisal"] = "closed_comp"

    ts_extracted: datetime
    ts_event: Optional[datetime] = None  # close date for closed_comp

    subject: CompSubject
    transaction: CompTransaction
    provenance: Provenance

    tags: list[str] = Field(default_factory=list)

    # convenience
    @property
    def is_within_12mo(self) -> bool:
        """The 12-month staleness rule from dmack 🎯 AIOV doctrine."""
        if self.ts_event is None:
            return False
        from datetime import timezone
        now = datetime.now(timezone.utc)
        ts = self.ts_event
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        delta = now - ts
        return delta.days <= 365
