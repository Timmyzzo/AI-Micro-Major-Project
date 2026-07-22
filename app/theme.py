"""Centralized PowerInsight design tokens and Streamlit theme styles."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

THEME_MARKER = "powerinsight-theme"

THEME_CSS = r"""
<style id="powerinsight-theme">
:root {
  --pi-bg: var(--background-color, #f5f5f7);
  --pi-surface-primary: color-mix(
    in srgb,
    var(--background-color, #f5f5f7) 96%,
    var(--text-color, #1d1d1f) 4%
  );
  --pi-surface-secondary: color-mix(
    in srgb,
    var(--background-color, #f5f5f7) 91%,
    var(--text-color, #1d1d1f) 9%
  );
  --pi-surface-floating: color-mix(
    in srgb,
    var(--background-color, #f5f5f7) 82%,
    transparent
  );
  --pi-sidebar: color-mix(
    in srgb,
    var(--background-color, #f5f5f7) 88%,
    var(--text-color, #1d1d1f) 12%
  );
  --pi-text-primary: var(--text-color, #1d1d1f);
  --pi-text-secondary: color-mix(in srgb, var(--text-color, #1d1d1f) 72%, transparent);
  --pi-text-tertiary: color-mix(in srgb, var(--text-color, #1d1d1f) 54%, transparent);
  --pi-accent: var(--primary-color, #0a84ff);
  --pi-accent-soft: color-mix(in srgb, var(--primary-color, #0a84ff) 14%, transparent);
  --pi-success: #2f9e5b;
  --pi-warning: #c77800;
  --pi-error: #d94b4b;
  --pi-information: #367fc0;
  --pi-divider: color-mix(in srgb, var(--text-color, #1d1d1f) 13%, transparent);
  --pi-border: color-mix(in srgb, var(--text-color, #1d1d1f) 18%, transparent);
  --pi-focus: color-mix(in srgb, var(--primary-color, #0a84ff) 72%, white 28%);
  --pi-radius-small: 0.55rem;
  --pi-radius-medium: 0.9rem;
  --pi-radius-large: 1.25rem;
  --pi-space-1: 0.25rem;
  --pi-space-2: 0.5rem;
  --pi-space-3: 0.75rem;
  --pi-space-4: 1rem;
  --pi-space-5: 1.5rem;
  --pi-space-6: 2rem;
  --pi-space-7: 3rem;
  --pi-type-caption: 0.78rem;
  --pi-type-body: 0.96rem;
  --pi-type-section: clamp(1.12rem, 1rem + 0.32vw, 1.35rem);
  --pi-type-title: clamp(2rem, 1.55rem + 1.5vw, 3rem);
  --pi-shadow-small: 0 0.35rem 1rem rgba(0, 0, 0, 0.07);
  --pi-shadow-medium: 0 1rem 2.8rem rgba(0, 0, 0, 0.11);
  --pi-blur-sidebar: 24px;
  --pi-blur-floating: 18px;
  --pi-press-duration: 90ms;
  --pi-hover-duration: 140ms;
  --pi-state-duration: 180ms;
  --pi-content-max: 82rem;
  --pi-table-row: 2.35rem;
  --pi-metric-gap: 0.8rem;
}

@media (prefers-color-scheme: dark) {
  :root {
    --pi-bg: #0f1115;
    --pi-surface-primary: #171a1f;
    --pi-surface-secondary: #22262d;
    --pi-surface-floating: rgba(15, 17, 21, 0.84);
    --pi-sidebar: rgba(25, 28, 34, 0.94);
    --pi-text-primary: #f5f5f7;
    --pi-text-secondary: rgba(245, 245, 247, 0.72);
    --pi-text-tertiary: rgba(245, 245, 247, 0.54);
    --pi-divider: rgba(245, 245, 247, 0.13);
    --pi-border: rgba(245, 245, 247, 0.2);
    --pi-shadow-small: 0 0.35rem 1rem rgba(0, 0, 0, 0.24);
    --pi-shadow-medium: 0 1rem 2.8rem rgba(0, 0, 0, 0.32);
  }
}

html,
body,
[data-testid="stAppViewContainer"] {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI Variable", "Segoe UI",
    "Microsoft YaHei UI", "Microsoft YaHei", system-ui, sans-serif;
  font-optical-sizing: auto;
}

body {
  color: var(--pi-text-primary);
  font-size: 100%;
  line-height: 1.55;
}

[data-testid="stAppViewContainer"] {
  background: var(--pi-bg);
}

[data-testid="stMainBlockContainer"] {
  max-width: var(--pi-content-max);
  padding-top: clamp(4rem, 4vw, 4.75rem);
  padding-right: clamp(1rem, 3vw, 3rem);
  padding-bottom: 4rem;
  padding-left: clamp(1rem, 3vw, 3rem);
}

[data-testid="stHeader"] {
  background: var(--pi-surface-floating);
  backdrop-filter: blur(var(--pi-blur-floating)) saturate(125%);
  -webkit-backdrop-filter: blur(var(--pi-blur-floating)) saturate(125%);
  box-shadow: 0 0.65rem 1.2rem -1.15rem rgba(0, 0, 0, 0.55);
}

[data-testid="stSidebar"] > div:first-child {
  background: var(--pi-sidebar);
  backdrop-filter: blur(var(--pi-blur-sidebar)) saturate(118%);
  -webkit-backdrop-filter: blur(var(--pi-blur-sidebar)) saturate(118%);
  border-right: 0;
  box-shadow: 0.75rem 0 2.4rem -2rem rgba(0, 0, 0, 0.6);
}

[data-testid="stSidebarContent"] {
  padding-top: 1rem;
}

[data-testid="stSidebarNav"] {
  padding-top: 0.45rem;
}

[data-testid="stSidebarNav"] a,
a[data-testid="stPageLink-NavLink"] {
  min-height: 2.65rem;
  border-radius: var(--pi-radius-small);
  color: var(--pi-text-secondary);
  transition:
    color var(--pi-hover-duration) ease-out,
    background-color var(--pi-hover-duration) ease-out,
    transform var(--pi-press-duration) ease-out;
}

[data-testid="stSidebarNav"] a:hover,
a[data-testid="stPageLink-NavLink"]:hover {
  color: var(--pi-text-primary);
  background: color-mix(in srgb, var(--pi-text-primary) 7%, transparent);
}

[data-testid="stSidebarNav"] a[aria-current="page"],
a[data-testid="stPageLink-NavLink"][aria-current="page"] {
  color: var(--pi-text-primary);
  background: var(--pi-accent-soft);
  box-shadow: inset 0.18rem 0 0 var(--pi-accent);
}

h1,
h2,
h3,
h4,
h5,
h6 {
  color: var(--pi-text-primary);
  font-optical-sizing: auto;
  text-wrap: balance;
}

h1 {
  letter-spacing: -0.035em;
  line-height: 1.06;
}

h2,
h3 {
  letter-spacing: -0.018em;
  line-height: 1.18;
}

p,
li,
label,
[data-testid="stCaptionContainer"] {
  line-height: 1.58;
}

[data-testid="stCaptionContainer"] {
  color: var(--pi-text-tertiary);
  font-size: var(--pi-type-caption);
  letter-spacing: 0.012em;
}

[data-testid="stButton"] button,
[data-testid="stDownloadButton"] button,
[data-testid="stFormSubmitButton"] button {
  min-height: 2.75rem;
  border-radius: var(--pi-radius-small);
  border-color: var(--pi-border);
  font-weight: 620;
  letter-spacing: -0.006em;
  transition:
    transform var(--pi-press-duration) ease-out,
    background-color var(--pi-hover-duration) ease-out,
    border-color var(--pi-hover-duration) ease-out,
    box-shadow var(--pi-hover-duration) ease-out;
}

[data-testid="stButton"] button:hover,
[data-testid="stDownloadButton"] button:hover,
[data-testid="stFormSubmitButton"] button:hover {
  border-color: color-mix(in srgb, var(--pi-accent) 58%, var(--pi-border));
  box-shadow: var(--pi-shadow-small);
}

button[data-testid="stBaseButton-primary"] {
  border-color: var(--pi-accent) !important;
  background: var(--pi-accent) !important;
  color: white !important;
}

button[data-testid="stBaseButton-primary"]:hover {
  border-color: color-mix(in srgb, var(--pi-accent) 82%, white 18%) !important;
  background: color-mix(in srgb, var(--pi-accent) 88%, black 12%) !important;
}

[data-testid="stButton"] button:active,
[data-testid="stDownloadButton"] button:active,
[data-testid="stFormSubmitButton"] button:active,
[data-testid="stSidebarNav"] a:active,
a[data-testid="stPageLink-NavLink"]:active {
  transform: scale(0.98);
  transition-duration: var(--pi-press-duration);
}

button:focus-visible,
a:focus-visible,
input:focus-visible,
textarea:focus-visible,
[role="button"]:focus-visible,
[tabindex]:focus-visible {
  outline: 0.2rem solid var(--pi-focus) !important;
  outline-offset: 0.15rem;
  box-shadow: none !important;
}

[data-testid="stMetric"] {
  min-height: 6rem;
  padding: 0.9rem 0.15rem 0.85rem;
  border-bottom: 1px solid var(--pi-divider);
}

[data-testid="stMetricLabel"] {
  color: var(--pi-text-secondary);
  font-size: var(--pi-type-caption);
  letter-spacing: 0.018em;
}

[data-testid="stMetricValue"] {
  color: var(--pi-text-primary);
  font-size: clamp(1.35rem, 1.1rem + 0.8vw, 2rem);
  font-weight: 660;
  letter-spacing: -0.03em;
  line-height: 1.12;
}

[data-testid="stDataFrame"],
[data-testid="stTable"] {
  overflow: hidden;
  border: 1px solid var(--pi-divider);
  border-radius: var(--pi-radius-medium);
  background: var(--pi-surface-primary);
}

[data-testid="stAlert"] {
  border-radius: var(--pi-radius-medium);
  border-width: 1px;
  box-shadow: none;
}

[data-testid="stExpander"] {
  border: 1px solid var(--pi-divider);
  border-radius: var(--pi-radius-medium);
  background: var(--pi-surface-primary);
  overflow: hidden;
}

[data-testid="stCode"] {
  border: 1px solid var(--pi-divider);
  border-radius: var(--pi-radius-medium);
}

.pi-brand {
  display: grid;
  grid-template-columns: 2.25rem 1fr;
  gap: 0.75rem;
  align-items: center;
  padding: 0.55rem 0.65rem 1.15rem;
}

.pi-brand-mark {
  display: grid;
  width: 2.25rem;
  height: 2.25rem;
  place-items: center;
  border-radius: 0.72rem;
  background: var(--pi-accent);
  color: white;
  font-size: 0.82rem;
  font-weight: 760;
  letter-spacing: -0.04em;
  box-shadow: 0 0.45rem 1.1rem color-mix(in srgb, var(--pi-accent) 24%, transparent);
}

.pi-brand-name {
  color: var(--pi-text-primary);
  font-size: 0.93rem;
  font-weight: 680;
  letter-spacing: -0.018em;
  line-height: 1.15;
}

.pi-brand-stage {
  margin-top: 0.18rem;
  color: var(--pi-text-tertiary);
  font-size: 0.72rem;
  letter-spacing: 0.02em;
}

.pi-page-header {
  display: grid;
  gap: 0.65rem;
  margin: 0 0 clamp(1.75rem, 3vw, 2.8rem);
  padding-bottom: 1.2rem;
  border-bottom: 1px solid var(--pi-divider);
}

.pi-page-header-row {
  display: flex;
  gap: 1rem;
  align-items: flex-start;
  justify-content: space-between;
}

.pi-eyebrow {
  color: var(--pi-accent);
  font-size: var(--pi-type-caption);
  font-weight: 720;
  letter-spacing: 0.075em;
  line-height: 1.2;
  text-transform: uppercase;
}

.pi-page-title {
  max-width: 16ch;
  margin: 0;
  color: var(--pi-text-primary) !important;
  font-size: var(--pi-type-title);
  font-weight: 720;
  letter-spacing: -0.042em;
  line-height: 1.04;
}

.pi-page-description {
  max-width: 48rem;
  margin: 0;
  color: var(--pi-text-secondary);
  font-size: clamp(0.98rem, 0.94rem + 0.16vw, 1.08rem);
  line-height: 1.62;
}

.pi-badge {
  flex: 0 0 auto;
  min-height: 2rem;
  padding: 0.42rem 0.7rem;
  border: 1px solid var(--pi-border);
  border-radius: 999px;
  background: var(--pi-surface-primary);
  color: var(--pi-text-secondary);
  font-size: var(--pi-type-caption);
  font-weight: 650;
  letter-spacing: 0.01em;
}

.pi-section-heading {
  margin: 0.55rem 0 1rem;
}

.pi-section-heading h2 {
  margin: 0;
  color: var(--pi-text-primary);
  font-size: var(--pi-type-section);
  font-weight: 690;
  letter-spacing: -0.024em;
  line-height: 1.18;
}

.pi-section-heading p {
  max-width: 44rem;
  margin: 0.35rem 0 0;
  color: var(--pi-text-secondary);
  font-size: var(--pi-type-body);
}

.pi-status {
  --pi-state-color: var(--pi-information);
  display: grid;
  gap: 0.8rem;
  padding: clamp(1rem, 2vw, 1.45rem);
  border: 1px solid color-mix(in srgb, var(--pi-state-color) 28%, var(--pi-divider));
  border-radius: var(--pi-radius-large);
  background: color-mix(in srgb, var(--pi-state-color) 5%, var(--pi-surface-primary));
}

.pi-status[data-tone="ready"],
.pi-status[data-tone="success"] {
  --pi-state-color: var(--pi-success);
}

.pi-status[data-tone="attention"] {
  --pi-state-color: var(--pi-warning);
}

.pi-status[data-tone="blocked"],
.pi-status[data-tone="failed"] {
  --pi-state-color: var(--pi-error);
}

.pi-status[data-tone="planned"],
.pi-status[data-tone="information"] {
  --pi-state-color: var(--pi-information);
}

.pi-status[data-tone="empty"],
.pi-status[data-tone="disabled"],
.pi-status[data-tone="unavailable"] {
  --pi-state-color: var(--pi-text-tertiary);
}

.pi-status[data-tone="loading"] {
  --pi-state-color: var(--pi-accent);
}

.pi-status-label {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  color: var(--pi-state-color);
  font-size: var(--pi-type-caption);
  font-weight: 740;
  letter-spacing: 0.055em;
  line-height: 1;
  text-transform: uppercase;
}

.pi-status-label::before {
  width: 0.52rem;
  height: 0.52rem;
  border-radius: 50%;
  background: currentColor;
  content: "";
  box-shadow: 0 0 0 0.22rem color-mix(in srgb, currentColor 13%, transparent);
}

.pi-status h3 {
  margin: 0;
  color: var(--pi-text-primary);
  font-size: clamp(1.15rem, 1.08rem + 0.28vw, 1.38rem);
  font-weight: 690;
  letter-spacing: -0.022em;
}

.pi-status p {
  max-width: 52rem;
  margin: 0;
  color: var(--pi-text-secondary);
  font-size: var(--pi-type-body);
}

.pi-evidence {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem 0.55rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.pi-evidence li {
  padding: 0.32rem 0.55rem;
  border-radius: 999px;
  background: var(--pi-surface-secondary);
  color: var(--pi-text-secondary);
  font-size: var(--pi-type-caption);
  font-weight: 610;
  line-height: 1.35;
}

.pi-next-step {
  padding-top: 0.7rem;
  border-top: 1px solid var(--pi-divider);
  color: var(--pi-text-secondary);
  font-size: var(--pi-type-caption);
}

.pi-next-step strong {
  color: var(--pi-text-primary);
}

.pi-facts {
  margin: 0;
  border-top: 1px solid var(--pi-divider);
}

.pi-fact {
  display: grid;
  grid-template-columns: minmax(7.5rem, 0.55fr) minmax(0, 1fr);
  gap: 1rem;
  padding: 0.85rem 0;
  border-bottom: 1px solid var(--pi-divider);
}

.pi-fact dt {
  color: var(--pi-text-tertiary);
  font-size: var(--pi-type-caption);
  font-weight: 630;
}

.pi-fact dd {
  margin: 0;
  color: var(--pi-text-primary);
  font-size: var(--pi-type-body);
  font-weight: 570;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.pi-connection {
  --pi-connection-color: var(--pi-text-tertiary);
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 1.5rem;
  align-items: center;
  padding: clamp(1rem, 2vw, 1.4rem);
  border: 1px solid color-mix(in srgb, var(--pi-connection-color) 32%, var(--pi-divider));
  border-radius: var(--pi-radius-large);
  background: color-mix(in srgb, var(--pi-connection-color) 5%, var(--pi-surface-primary));
}

.pi-connection[data-tone="pending"] {
  --pi-connection-color: var(--pi-accent);
}

.pi-connection[data-tone="success"] {
  --pi-connection-color: #69d53b;
}

.pi-connection[data-tone="failed"] {
  --pi-connection-color: var(--pi-error);
}

.pi-connection-copy {
  min-width: 0;
}

.pi-connection-kicker {
  color: var(--pi-text-tertiary);
  font-size: var(--pi-type-caption);
  font-weight: 700;
  letter-spacing: 0.045em;
}

.pi-connection-title {
  margin-top: 0.3rem;
  color: var(--pi-text-primary);
  font-size: clamp(1.2rem, 1.05rem + 0.55vw, 1.55rem);
  font-weight: 720;
  letter-spacing: -0.025em;
}

.pi-connection-model {
  margin-top: 0.22rem;
  color: var(--pi-connection-color);
  font-size: var(--pi-type-body);
  font-weight: 650;
}

.pi-connection-detail {
  margin-top: 0.35rem;
  color: var(--pi-text-secondary);
  font-size: var(--pi-type-caption);
}

.pi-connection-bars {
  display: flex;
  gap: 0.34rem;
  align-items: center;
  justify-content: center;
  min-width: 6.5rem;
  min-height: 4.5rem;
  padding: 0.8rem 1rem;
  border-radius: var(--pi-radius-medium);
  background: #1b2a40;
}

.pi-connection-bar {
  display: block;
  width: 0.46rem;
  height: 2.05rem;
  border-radius: 999px;
  background: var(--pi-connection-color);
  box-shadow: 0 0 0.9rem color-mix(in srgb, var(--pi-connection-color) 24%, transparent);
}

.pi-connection[data-tone="pending"] .pi-connection-bar {
  animation: pi-connection-pulse 1.25s ease-in-out infinite alternate;
}

.pi-connection[data-tone="pending"] .pi-connection-bar:nth-child(2),
.pi-connection[data-tone="pending"] .pi-connection-bar:nth-child(4) {
  animation-delay: 120ms;
}

@keyframes pi-connection-pulse {
  from { opacity: 0.42; transform: scaleY(0.72); }
  to { opacity: 1; transform: scaleY(1); }
}

@media (max-width: 56rem) {
  [data-testid="stMainBlockContainer"] {
    padding-top: 4rem;
  }

  .pi-page-header-row {
    display: grid;
  }

  .pi-badge {
    width: fit-content;
  }

  .pi-fact {
    grid-template-columns: 1fr;
    gap: 0.25rem;
  }

  .pi-connection {
    grid-template-columns: 1fr;
  }

  .pi-connection-bars {
    width: 100%;
  }
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    scroll-behavior: auto !important;
    animation-duration: 1ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 80ms !important;
  }

  [data-testid="stButton"] button:active,
  [data-testid="stDownloadButton"] button:active,
  [data-testid="stFormSubmitButton"] button:active,
  [data-testid="stSidebarNav"] a:active,
  a[data-testid="stPageLink-NavLink"]:active {
    transform: none;
    opacity: 0.78;
  }
}

@media (prefers-reduced-transparency: reduce) {
  [data-testid="stHeader"],
  [data-testid="stSidebar"] > div:first-child {
    background: var(--pi-bg);
    backdrop-filter: none;
    -webkit-backdrop-filter: none;
  }

  .pi-badge,
  .pi-status {
    background: var(--pi-bg);
  }
}

@media (prefers-contrast: more) {
  :root {
    --pi-divider: color-mix(in srgb, var(--text-color, #1d1d1f) 36%, transparent);
    --pi-border: color-mix(in srgb, var(--text-color, #1d1d1f) 54%, transparent);
    --pi-text-secondary: color-mix(in srgb, var(--text-color, #1d1d1f) 88%, transparent);
    --pi-text-tertiary: color-mix(in srgb, var(--text-color, #1d1d1f) 76%, transparent);
  }

  [data-testid="stHeader"],
  [data-testid="stSidebar"] > div:first-child,
  .pi-status,
  .pi-badge {
    background: var(--pi-bg);
    backdrop-filter: none;
    -webkit-backdrop-filter: none;
    border-color: var(--pi-border);
  }
}
</style>
"""


def apply_theme() -> None:
    """Inject the centralized theme exactly once during one app script run."""
    st.markdown(THEME_CSS, unsafe_allow_html=True)


def style_plotly_figure(
    figure: go.Figure,
    *,
    title: str,
    xaxis_title: str | None = None,
    yaxis_title: str | None = None,
    height: int = 360,
) -> go.Figure:
    """Apply the shared transparent, low-chroma chart presentation."""
    figure.update_layout(
        title={"text": title, "x": 0.0, "xanchor": "left"},
        height=height,
        margin={"l": 24, "r": 18, "t": 58, "b": 30},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hoverlabel={"namelength": -1},
        legend={"orientation": "h", "y": 1.02, "x": 1, "xanchor": "right"},
        font={"family": "Segoe UI Variable, Microsoft YaHei UI, sans-serif"},
    )
    figure.update_xaxes(
        title=xaxis_title,
        showgrid=False,
        zeroline=False,
        automargin=True,
    )
    figure.update_yaxes(
        title=yaxis_title,
        gridcolor="rgba(128,128,128,0.18)",
        zeroline=False,
        automargin=True,
    )
    return figure
