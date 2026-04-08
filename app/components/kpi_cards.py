"""
Reusable UI primitives — KPI cards, section titles, chart wrapper.
"""
import re

import pandas as pd
import streamlit as st

from app.components.styles import (
    CHART_THEME, _GRID, DXC_BORDER, DXC_GREY, DXC_TEXT,
)

_chart_counter = [0]


def kpi_card(label: str, value, color: str = "#1A1A2E", sub: str = ""):
    sub_html = f'<p class="kpi-sub">{sub}</p>' if sub else ""
    st.markdown(f"""
    <div class="kpi-card">
        <p class="kpi-value" style="color:{color}">{value}</p>
        <p class="kpi-label">{label}</p>
        {sub_html}
    </div>""", unsafe_allow_html=True)


def sec(title: str):
    st.markdown(f'<p class="sec-title">{title}</p>', unsafe_allow_html=True)


def chart(fig, **kwargs):
    _axis = dict(gridcolor=_GRID, linecolor=DXC_BORDER,
                 zerolinecolor=DXC_BORDER, tickfont=dict(color=DXC_GREY))
    fig.update_layout(
        **CHART_THEME,
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=DXC_TEXT)),
    )
    fig.update_xaxes(**_axis)
    fig.update_yaxes(**_axis)
    _chart_counter[0] += 1
    kwargs.setdefault("key", f"chart_{_chart_counter[0]}")
    st.plotly_chart(fig, use_container_width=True, **kwargs)


def shorten(s: str, n: int = 40) -> str:
    return s[:n] + "…" if len(s) > n else s


def sprint_group(s) -> str | None:
    """
    Normalise raw sprint strings into a canonical group name.

    22.1.25.1 / 22.1.25.2 / 22.1.25 ADDS / 22.1.25.2 ADDSc  →  v22 R25
    20.1.23.1 / 20.1.23.2                                     →  v20 R23
    TMA 22.1.19 / TMA 22.1.19 ADDS                            →  TMA v22 R19
    DATAFIX 24 / SP 7.1001 / RC W30 / …                       →  kept as-is
    """
    if pd.isna(s) or str(s).strip().lower() in ("", "none"):
        return None
    s = str(s).strip()
    m = re.match(r"^TMA\s+(\d+)\.\d+\.(\d+)", s, re.IGNORECASE)
    if m:
        return f"TMA v{m.group(1)} R{m.group(2)}"
    m = re.match(r"^(\d+)\.\d+\.(\d+)", s)
    if m:
        return f"v{m.group(1)} R{m.group(2)}"
    return s
