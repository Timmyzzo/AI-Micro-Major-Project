"""Presentation component safety and state-language tests."""

from __future__ import annotations

import pytest
from app.components import layout


def test_status_panel_escapes_dynamic_text(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[str] = []

    def capture(body: str, *, unsafe_allow_html: bool) -> None:
        assert unsafe_allow_html is True
        captured.append(body)

    monkeypatch.setattr(layout.st, "markdown", capture)

    layout.render_status_panel(
        tone="failed",
        label="<状态>",
        title="<script>alert(1)</script>",
        description='失败原因包含 "<路径>"',
        evidence=("<证据>",),
        next_step="<重试>",
    )

    markup = captured[0]
    assert "<script>" not in markup
    assert "&lt;script&gt;" in markup
    assert "&lt;证据&gt;" in markup
    assert 'data-tone="failed"' in markup


def test_fact_list_preserves_order_and_escapes_values(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[str] = []

    def capture(body: str, *, unsafe_allow_html: bool) -> None:
        assert unsafe_allow_html is True
        captured.append(body)

    monkeypatch.setattr(layout.st, "markdown", capture)

    layout.render_fact_list((("第一项", "正常"), ("第二项", "<未知>")))

    markup = captured[0]
    assert markup.index("第一项") < markup.index("第二项")
    assert "&lt;未知&gt;" in markup
