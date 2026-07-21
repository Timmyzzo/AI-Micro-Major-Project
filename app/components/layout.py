"""Reusable presentation-only layout and status components."""

from __future__ import annotations

from collections.abc import Sequence
from html import escape
from typing import Literal

import streamlit as st

StatusTone = Literal[
    "empty",
    "ready",
    "loading",
    "success",
    "attention",
    "blocked",
    "failed",
    "disabled",
    "planned",
    "unavailable",
    "information",
]


def render_sidebar_brand(*, stage: str) -> None:
    """Render a stable app identity above Streamlit navigation."""
    st.sidebar.markdown(
        (
            '<div class="pi-brand">'
            '<div class="pi-brand-mark" aria-hidden="true">PI</div>'
            '<div><div class="pi-brand-name">智电洞察</div>'
            f'<div class="pi-brand-stage">{escape(stage)}</div></div>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_page_header(
    *,
    eyebrow: str,
    title: str,
    description: str,
    badge: str | None = None,
) -> None:
    """Render a compact page identity region with one clear hierarchy."""
    badge_html = f'<div class="pi-badge">{escape(badge)}</div>' if badge else ""
    st.markdown(
        (
            '<header class="pi-page-header">'
            f'<div class="pi-eyebrow">{escape(eyebrow)}</div>'
            '<div class="pi-page-header-row"><div>'
            f'<h1 class="pi-page-title">{escape(title)}</h1>'
            f"</div>{badge_html}</div>"
            f'<p class="pi-page-description">{escape(description)}</p>'
            "</header>"
        ),
        unsafe_allow_html=True,
    )


def render_section_heading(*, title: str, description: str | None = None) -> None:
    """Render a consistent section heading without creating another card."""
    description_html = f"<p>{escape(description)}</p>" if description else ""
    st.markdown(
        (f'<div class="pi-section-heading"><h2>{escape(title)}</h2>{description_html}</div>'),
        unsafe_allow_html=True,
    )


def render_status_panel(
    *,
    tone: StatusTone,
    label: str,
    title: str,
    description: str,
    evidence: Sequence[str] = (),
    next_step: str | None = None,
) -> None:
    """Render a factual state with text, evidence, and an actionable next step."""
    evidence_html = ""
    if evidence:
        items = "".join(f"<li>{escape(item)}</li>" for item in evidence)
        evidence_html = f'<ul class="pi-evidence">{items}</ul>'
    next_step_html = ""
    if next_step:
        next_step_html = (
            f'<div class="pi-next-step"><strong>下一步</strong> · {escape(next_step)}</div>'
        )
    st.markdown(
        (
            f'<section class="pi-status" data-tone="{tone}">'
            f'<div class="pi-status-label">{escape(label)}</div>'
            f"<h3>{escape(title)}</h3>"
            f"<p>{escape(description)}</p>"
            f"{evidence_html}{next_step_html}</section>"
        ),
        unsafe_allow_html=True,
    )


def render_fact_list(items: Sequence[tuple[str, str]]) -> None:
    """Render dense, readable key-value facts for diagnostics and summaries."""
    facts = "".join(
        (f'<div class="pi-fact"><dt>{escape(label)}</dt><dd>{escape(value)}</dd></div>')
        for label, value in items
    )
    st.markdown(f'<dl class="pi-facts">{facts}</dl>', unsafe_allow_html=True)
