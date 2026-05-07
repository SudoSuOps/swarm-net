# 🛰️ swarm-net

> **SwarmNet** · the data moat for Swarm & Bee · MNET-equivalent for the AI brokerage era · CRE deal intelligence database with provenance + human-in-the-loop discipline.

```
SOURCES         EXTRACT          TRANSFORM         LOAD                SwarmNet
                ───────          ─────────         ────                ────────
SEC EDGAR ────┐
FRED ─────────┤
Census ───────┤
BLS QCEW ─────┤  per-source       canonical         hack-wiki +        Atlas
FFIEC CDR ────┤  extractors       schemas           Kuzu graph    →    Curator
Boulder PDFs ─┼──→  /raw/  ────→  /staging/  ────→                     Hacks
C&W PDFs ─────┤                   ↓                 + Hedera anchor    AIOV
CBRE PDFs ────┤                   HUMAN REVIEW      (eventual)
Newmark PDFs ─┤                   QUEUE (Gradio)
County deeds ─┘                   ↓
                                  approved → /ingested
                                  rejected → /archived
```

## Why

Per `dmack` doctrine (sections 🗃️ SWARMNET, 🛰️ DATA SOURCING, 🛠️ SWARMNET ETL):

- **Compute moat** = 186 GPUs · 14 TB VRAM · 12-18mo lead time. Unreplicable.
- **Data moat** = SwarmNet · the 1099-cultural-unfillable layer that the national platform structurally cannot build.

Together: two orthogonal moats reinforcing each other. AIOV (the customer-facing Opinion of Value product) is downstream — without SwarmNet behind it, AIOV is a re-skinned CoStar export.

## Three principles

1. **PROVENANCE-FIRST.** Every record carries source URL · fetched_at · raw_artifact_sha256. Audit trail back to original byte-for-byte source.
2. **HITL-GATED** (Human-in-the-Loop · MISSION CRITICAL per Donovan, 2026-05-07). No automatic promotion to SwarmNet. Senior-broker reviews every entry via Gradio UI before it lands in the firm's institutional memory.
3. **IDEMPOTENT.** Re-running an extractor doesn't duplicate. Same source-id + ts = same record · re-fetches update.

## Storage layout

```
data/
├── _raw/         original artifacts (PDFs, JSON, HTML) · sha256-stamped
├── _staging/     parsed but pending senior-broker review
├── _ingested/    promoted to SwarmNet (hack-wiki + Kuzu graph)
├── _archived/    rejected entries (audit trail preserved)
├── _logs/        intake.sqlite · run-by-run audit
└── _review-queue/ Gradio UI staging snapshots
```

## Tier 0 sources (free · ships first)

| Source | Type | Cadence | Status |
|--------|------|---------|--------|
| SEC EDGAR | Tenant credit (10-K/10-Q) | Daily | ✅ Phase 1 |
| FRED | Macro · CRE loans · rates | Daily | Phase 2 |
| Census ACS | Demographics | Annual | Phase 2 |
| BLS QCEW | County employment | Quarterly | Phase 2 |
| FFIEC CDR | Bank concentration | Quarterly | Phase 2 |
| Boulder Group | Quarterly STNL cap rates | Quarterly | Phase 3 |
| C&W MarketBeat | Shopping center vacancy | Quarterly | Phase 3 |
| CBRE Cap Rate Survey | Semi-annual | Semi-annual | Phase 3 |
| Newmark Net Lease | Quarterly | Quarterly | Phase 3 |
| TX/FL county deeds | Per-deed | Daily | Phase 4 |

## Quickstart

```bash
git clone git@github.com:SudoSuOps/swarm-net.git
cd swarm-net
uv venv && source .venv/bin/activate
uv pip install -e .

# extract DG tenant credit from SEC EDGAR
swarmnet extract sec-edgar --ticker DG

# review pending entries
swarmnet review

# launch HITL UI
swarmnet ui  # → http://swarmrails:7863
```

## See also

- `dmack` skill · sections 🗃️ SWARMNET, 🎯 AIOV, 🛰️ DATA SOURCING, 🛠️ SWARMNET ETL
- `hack-wiki` · the institutional memory this feeds
- `swarmnet.eth` · the brand surface (ENS owned · gateway sub-domains forthcoming)
