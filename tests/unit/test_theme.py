"""Centralized Streamlit theme contract tests."""

from __future__ import annotations

from app.theme import THEME_CSS, THEME_MARKER

from powerinsight.paths import PROJECT_ROOT


def test_theme_contains_required_tokens_and_accessibility_modes() -> None:
    required_tokens = (
        "--pi-bg",
        "--pi-surface-primary",
        "--pi-sidebar",
        "--pi-text-primary",
        "--pi-accent",
        "--pi-success",
        "--pi-warning",
        "--pi-error",
        "--pi-focus",
        "--pi-radius-small",
        "--pi-space-4",
        "--pi-shadow-medium",
        "--pi-blur-sidebar",
        "--pi-press-duration",
        "--pi-content-max",
        "--pi-table-row",
    )

    assert all(token in THEME_CSS for token in required_tokens)
    assert f'id="{THEME_MARKER}"' in THEME_CSS
    assert "prefers-reduced-motion: reduce" in THEME_CSS
    assert "prefers-reduced-transparency: reduce" in THEME_CSS
    assert "prefers-contrast: more" in THEME_CSS
    assert ":focus-visible" in THEME_CSS
    assert "transform: scale(0.98)" in THEME_CSS
    assert '[data-testid="stAppViewContainer"]' in THEME_CSS
    assert '[data-testid="stSidebarNav"]' in THEME_CSS
    assert '[data-testid="stMetric"]' in THEME_CSS
    assert '[data-testid="stDataFrame"]' in THEME_CSS


def test_theme_is_initialized_only_from_the_streamlit_entrypoint() -> None:
    entrypoint = (PROJECT_ROOT / "app" / "streamlit_app.py").read_text(encoding="utf-8")
    page_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((PROJECT_ROOT / "app" / "pages").glob("*.py"))
    )

    assert entrypoint.count("apply_theme()") == 1
    assert "apply_theme" not in page_sources


def test_pages_do_not_define_scattered_style_blocks() -> None:
    page_paths = sorted((PROJECT_ROOT / "app" / "pages").glob("*.py"))

    for path in page_paths:
        source = path.read_text(encoding="utf-8")
        assert "<style" not in source, path.name
