"""SwarmNet HITL review UI · Gradio · senior-broker-grade gate.

Per dmack doctrine (Donovan, 2026-05-07):
  "A human in the loop is mission critical · and we will 100% do that."

This UI is the gate · pending /staging/ entries land here · the senior
broker reviews the candidate JSON + raw source link · approves · edits ·
or rejects with rationale. Approval promotes to /ingested/ + hack-wiki.
"""
from __future__ import annotations
import json
from pathlib import Path

import gradio as gr

from swarmnet.config import REVIEW_UI_PORT, REVIEW_UI_HOST
from swarmnet.storage import Ledger, list_pending_staging, promote_to_ingested, archive_rejected


def _list_pending() -> list[str]:
    """All pending staging paths · most recent first."""
    paths = list(list_pending_staging())
    paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [str(p) for p in paths]


def _load(path_str: str) -> tuple[str, str]:
    """Return (rendered summary, full JSON string) for a given staging path."""
    if not path_str or not Path(path_str).exists():
        return "(no record selected)", "{}"
    rec = json.loads(Path(path_str).read_text())

    # render summary based on record type
    rec_type = Path(path_str).parent.name
    summary_lines = [f"## {rec_type} · `{Path(path_str).stem}`"]

    if rec_type == "tenants":
        summary_lines.append(f"**Name:** {rec.get('tenant_name', 'unknown')}")
        summary_lines.append(f"**Ticker:** {rec.get('ticker', '?')} · **CIK:** {rec.get('cik', '?')}")
        ratings = rec.get("ratings", [])
        if ratings:
            summary_lines.append("**Ratings:**")
            for r in ratings:
                ig = "✅ IG" if r.get("investment_grade") else "❌ non-IG"
                summary_lines.append(
                    f"  · {r['agency']} · **{r['rating']}** · "
                    f"as_of {r['as_of']} · {ig}"
                )
        else:
            summary_lines.append("**Ratings:** ⚠ none captured · needs review")
        gm = rec.get("guarantor_model", {})
        summary_lines.append(
            f"**Guarantor model:** {gm.get('type', '?')} · "
            f"franchisee_pct {gm.get('franchisee_pct', '?')}"
        )
        if gm.get("notes"):
            summary_lines.append(f"  · {gm['notes']}")

    elif rec_type == "comps":
        s = rec.get("subject", {})
        t = rec.get("transaction", {})
        summary_lines.append(f"**Tenant:** {s.get('tenant_slug', '?')}")
        summary_lines.append(f"**Address:** {s.get('address', '?')} · {s.get('city', '?')}, {s.get('state', '?')}")
        summary_lines.append(f"**Price:** ${t.get('price_usd', 0):,.0f}")
        summary_lines.append(f"**NOI:** ${t.get('noi_usd', 0):,.0f}")
        summary_lines.append(f"**Cap rate:** {t.get('cap_rate_pct', 0):.2f}%")
        summary_lines.append(f"**Term remaining:** {t.get('lease_term_years_remaining', '?')} years")

    elif rec_type == "markets":
        m = rec.get("metrics", {})
        summary_lines.append(f"**Period:** {rec.get('period', '?')}")
        if m.get("stnl_retail_cap_median_pct"):
            summary_lines.append(f"**STNL cap median:** {m['stnl_retail_cap_median_pct']:.2f}%")
        if m.get("treasury_10yr_pct"):
            summary_lines.append(f"**10yr Treasury:** {m['treasury_10yr_pct']:.2f}%")

    return "\n".join(summary_lines), json.dumps(rec, indent=2, default=str)


def _approve(path_str: str, reviewer: str, notes: str):
    if not path_str or not Path(path_str).exists():
        return "no record selected", _list_pending()
    p = Path(path_str)
    rec_type = p.parent.name
    slug = p.stem
    promoted = promote_to_ingested(p, reviewer=reviewer or "donovan", notes=notes or "")
    Ledger().log_review(rec_type, slug, "approved", reviewer=reviewer or "donovan", notes=notes or "")
    msg = f"✅ APPROVED · promoted to {promoted}"
    return msg, _list_pending()


def _reject(path_str: str, reviewer: str, reason: str):
    if not path_str or not Path(path_str).exists():
        return "no record selected", _list_pending()
    p = Path(path_str)
    rec_type = p.parent.name
    slug = p.stem
    archived = archive_rejected(p, reviewer=reviewer or "donovan", reason=reason or "")
    Ledger().log_review(rec_type, slug, "rejected", reviewer=reviewer or "donovan", notes=reason or "")
    msg = f"❌ REJECTED · archived to {archived}"
    return msg, _list_pending()


def launch_ui():
    """Spin Gradio UI on REVIEW_UI_HOST:REVIEW_UI_PORT."""
    with gr.Blocks(title="🛰️ SwarmNet · HITL Review") as demo:
        gr.Markdown("# 🛰️ SwarmNet · Human-In-The-Loop Review")
        gr.Markdown(
            "*Senior-broker review gate · per `/dmack` doctrine: "
            "a human in the loop is mission critical.*"
        )

        with gr.Row():
            with gr.Column(scale=1):
                pending_dropdown = gr.Dropdown(
                    label="Pending records",
                    choices=_list_pending(),
                    interactive=True,
                )
                refresh_btn = gr.Button("🔄 Refresh queue")
                status_box = gr.Markdown("(no action yet)")

            with gr.Column(scale=2):
                summary = gr.Markdown(label="Summary")
                json_view = gr.Code(label="Full record JSON", language="json", lines=25)

        with gr.Row():
            reviewer = gr.Textbox(label="Reviewer", value="donovan", scale=1)
            notes = gr.Textbox(label="Notes / Reason", lines=2, scale=3)

        with gr.Row():
            approve_btn = gr.Button("✅ Approve · promote to SwarmNet", variant="primary")
            reject_btn = gr.Button("❌ Reject · archive with rationale", variant="stop")

        # wire events
        pending_dropdown.change(_load, inputs=pending_dropdown, outputs=[summary, json_view])
        refresh_btn.click(
            lambda: gr.update(choices=_list_pending()), outputs=pending_dropdown,
        )
        approve_btn.click(
            _approve,
            inputs=[pending_dropdown, reviewer, notes],
            outputs=[status_box, pending_dropdown],
        )
        reject_btn.click(
            _reject,
            inputs=[pending_dropdown, reviewer, notes],
            outputs=[status_box, pending_dropdown],
        )

    demo.launch(
        server_name=REVIEW_UI_HOST,
        server_port=REVIEW_UI_PORT,
        share=False,
    )
