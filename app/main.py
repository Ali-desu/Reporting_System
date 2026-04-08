"""
Streamlit Reporting Dashboard
Run:  streamlit run app/main.py
"""
import os
import warnings
warnings.filterwarnings("ignore")

import streamlit as st
from dotenv import load_dotenv

from app.components import CSS, DXC_PURPLE, DXC_GREY_LIGHT
from app.loaders import load_data, apply_filters
from app.tabs import (
    tab_overview, tab_trends, tab_analysis, tab_sla,
    tab_burndown, tab_backlog, tab_team, tab_ai, tab_upload,
)

load_dotenv()

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="DXC — Service Desk Analytics",
    page_icon="assets/favicon.png" if os.path.exists("assets/favicon.png") else None,
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(CSS, unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<p class="sidebar-brand">DXC — Service Desk Analytics</p>',
                unsafe_allow_html=True)

    df_all   = load_data()
    has_data = not df_all.empty

    if has_data:
        min_d = df_all["created"].min().date() if "created" in df_all else None
        max_d = df_all["created"].max().date() if "created" in df_all else None

        st.markdown('<p class="sidebar-section">Date Range</p>', unsafe_allow_html=True)
        date_range = st.date_input("Created between", value=(min_d, max_d),
                                   min_value=min_d, max_value=max_d,
                                   label_visibility="collapsed")

        def _checkbox_group(label, options, prefix):
            st.markdown(f'<p class="sidebar-section">{label}</p>', unsafe_allow_html=True)
            _all_key    = f"{prefix}_all"
            _select_all = st.checkbox("Select all", value=True, key=_all_key)
            selected = []
            for opt in options:
                _checked = st.checkbox(str(opt), value=_select_all,
                                       key=f"{prefix}_{opt}", disabled=_select_all)
                selected.append(opt if (_select_all or _checked) else None)
            return [o for o in selected if o is not None]

        all_orgs  = sorted(df_all["organizations"].dropna().unique()) if "organizations" in df_all.columns else []
        all_types = sorted(df_all["issue_type"].dropna().unique())
        all_env   = sorted(df_all["environment_type"].dropna().unique())
        pri_order = [p for p in ["Critical", "High", "Medium", "Low"] if p in df_all["priority"].values]
        all_proj  = sorted(df_all["project"].dropna().unique())

        sel_orgs  = _checkbox_group("Organisation", all_orgs,  "org")
        sel_types = _checkbox_group("Issue Type",   all_types, "typ")
        sel_env   = _checkbox_group("Environment",  all_env,   "env")
        sel_pri   = _checkbox_group("Priority",     pri_order, "pri")
        sel_proj  = _checkbox_group("Project",      all_proj,  "prj")

        filters = dict(
            date_range=date_range,
            orgs=sel_orgs or all_orgs,
            types=sel_types or all_types,
            envs=sel_env or all_env,
            priorities=sel_pri or pri_order,
            projects=sel_proj or all_proj,
        )

        st.markdown("---")
        n_filtered = len(apply_filters(df_all, filters))
        st.caption(f"{n_filtered:,} of {len(df_all):,} records match filters")
    else:
        filters = {}
        st.info("No data — use the Upload tab.")

# ── Page header ───────────────────────────────────────────────────────────────
st.markdown('<p class="page-title">Service Desk Analytics</p>', unsafe_allow_html=True)
st.markdown('<p class="page-subtitle">Issue tracking · Performance monitoring · Sprint planning</p>',
            unsafe_allow_html=True)

# ── Tabs ──────────────────────────────────────────────────────────────────────
(tab_ov, tab_tr, tab_an, tab_sl,
 tab_bd, tab_bk, tab_tm, tab_ch, tab_up) = st.tabs([
    "Overview", "Trends", "Analysis", "SLA & KPIs",
    "Burndown", "Backlog Burndown", "Team", "AI Assistant", "Upload",
])

with tab_up:
    tab_upload.render(df_all, has_data)

if not has_data:
    for t in [tab_ov, tab_tr, tab_an, tab_sl, tab_bd, tab_bk, tab_tm, tab_ch]:
        with t:
            st.info("No data available. Go to the **Upload** tab to load your Extract file.")
    st.stop()

df = apply_filters(df_all, filters)

if df.empty:
    for t in [tab_ov, tab_tr, tab_an, tab_sl, tab_bd, tab_bk, tab_tm, tab_ch]:
        with t:
            st.warning("No records match the current filters.")
    st.stop()

with tab_ov: tab_overview.render(df)
with tab_tr: tab_trends.render(df)
with tab_an: tab_analysis.render(df)
with tab_sl: tab_sla.render(df)
with tab_bd: tab_burndown.render(df_all, df)
with tab_bk: tab_backlog.render(df_all)
with tab_tm: tab_team.render(df)
with tab_ch: tab_ai.render()
