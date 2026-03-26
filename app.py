"""
Streamlit Reporting Dashboard
Run:  streamlit run app.py
"""
import io
import os
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine, text, inspect

from etl import clean_data, upsert, initial_load, build_engine, get_engine
from agent import run_agent, check_api_key

load_dotenv()

# ──────────────────────────────────────────────────────────────────────────────
# Page config & global styles
# ──────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="DXC — Service Desk Analytics",
    page_icon="assets/favicon.png" if os.path.exists("assets/favicon.png") else None,
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── DXC colour tokens ──────────────────────────────────────────────────────────
DXC_PURPLE      = "#6D2077"
DXC_PURPLE_LITE = "#9B26AF"
DXC_PURPLE_DIM  = "#3D1142"
DXC_BLACK       = "#0D0D0D"
DXC_SURFACE     = "#161616"
DXC_SURFACE2    = "#1F1F1F"
DXC_BORDER      = "#2E2E2E"
DXC_GREY        = "#6D7278"
DXC_GREY_LIGHT  = "#A0A4A8"
DXC_TEXT        = "#E8E8E8"
DXC_TEXT_DIM    = "#8A8A8A"
DXC_WHITE       = "#FFFFFF"

st.markdown(f"""
<style>
/* ── Base ── */
html, body, [data-testid="stAppViewContainer"],
[data-testid="stAppViewBlockContainer"],
.main, .block-container {{
    background-color: {DXC_BLACK} !important;
    color: {DXC_TEXT} !important;
    font-family: 'Segoe UI', sans-serif;
}}
[data-testid="stHeader"] {{ background: transparent !important; }}

/* ── Sidebar ── */
[data-testid="stSidebar"],
[data-testid="stSidebar"] > div,
section[data-testid="stSidebar"] > div {{
    background-color: {DXC_SURFACE} !important;
    border-right: 1px solid {DXC_BORDER} !important;
}}
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] div {{
    color: {DXC_TEXT} !important;
}}
[data-testid="stSidebar"] [data-baseweb="select"] > div,
[data-testid="stSidebar"] [data-baseweb="input"] > div,
[data-testid="stSidebar"] [data-testid="stDateInput"] input {{
    background-color: {DXC_SURFACE2} !important;
    border-color: {DXC_BORDER} !important;
    color: {DXC_TEXT} !important;
    border-radius: 4px !important;
}}
[data-testid="stSidebar"] hr {{
    border-color: {DXC_BORDER} !important;
}}
.sidebar-brand {{
    font-size: 0.75rem;
    font-weight: 700;
    color: {DXC_PURPLE_LITE} !important;
    text-transform: uppercase;
    letter-spacing: 1.6px;
    padding-bottom: 12px;
}}
.sidebar-section {{
    font-size: 0.65rem;
    font-weight: 600;
    color: {DXC_GREY} !important;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    margin: 18px 0 6px 0;
}}

/* ── KPI card ── */
.kpi-card {{
    background-color: {DXC_SURFACE2};
    border: 1px solid {DXC_BORDER};
    border-top: 3px solid {DXC_PURPLE};
    border-radius: 4px;
    padding: 20px 16px 16px 16px;
    text-align: center;
    margin-bottom: 4px;
}}
.kpi-value {{
    font-size: 2.2rem;
    font-weight: 700;
    margin: 0 0 6px 0;
    line-height: 1;
    color: {DXC_WHITE};
}}
.kpi-label {{
    font-size: 0.68rem;
    color: {DXC_GREY_LIGHT};
    text-transform: uppercase;
    letter-spacing: 1.4px;
    margin: 0;
}}
.kpi-sub {{
    font-size: 0.72rem;
    color: {DXC_GREY};
    margin-top: 6px;
}}

/* ── Section title ── */
.sec-title {{
    font-size: 0.95rem;
    font-weight: 600;
    color: {DXC_TEXT};
    text-transform: uppercase;
    letter-spacing: 0.8px;
    border-left: 3px solid {DXC_PURPLE};
    padding-left: 10px;
    margin: 28px 0 12px 0;
}}

/* ── Divider ── */
hr {{ border-color: {DXC_BORDER} !important; }}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {{
    gap: 2px;
    background-color: {DXC_SURFACE};
    border-bottom: 1px solid {DXC_BORDER};
    padding: 0 4px;
}}
.stTabs [data-baseweb="tab"] {{
    background: transparent;
    border-radius: 0;
    padding: 10px 20px;
    color: {DXC_GREY_LIGHT};
    font-size: 0.82rem;
    font-weight: 500;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    border-bottom: 2px solid transparent;
}}
.stTabs [aria-selected="true"] {{
    background: transparent !important;
    color: {DXC_WHITE} !important;
    border-bottom: 2px solid {DXC_PURPLE} !important;
}}

/* ── Inputs ── */
[data-testid="stSelectbox"] > div,
[data-testid="stMultiSelect"] > div,
[data-testid="stDateInput"] > div {{
    background-color: {DXC_SURFACE2} !important;
    border-color: {DXC_BORDER} !important;
    border-radius: 4px !important;
}}
.stButton > button {{
    background-color: {DXC_PURPLE} !important;
    color: {DXC_WHITE} !important;
    border: none !important;
    border-radius: 4px !important;
    font-weight: 600 !important;
    letter-spacing: 0.5px;
}}
.stButton > button:hover {{
    background-color: {DXC_PURPLE_LITE} !important;
}}

/* ── Expander ── */
[data-testid="stExpander"] {{
    border: 1px solid {DXC_BORDER} !important;
    border-radius: 4px !important;
    background-color: {DXC_SURFACE2} !important;
}}

/* ── Dataframe ── */
[data-testid="stDataFrame"] {{
    border: 1px solid {DXC_BORDER};
    border-radius: 4px;
}}

/* ── Page title ── */
.page-title {{
    font-size: 1.5rem;
    font-weight: 700;
    color: {DXC_WHITE};
    letter-spacing: 0.5px;
    margin-bottom: 0;
    padding-bottom: 12px;
    border-bottom: 1px solid {DXC_BORDER};
}}
.page-subtitle {{
    font-size: 0.8rem;
    color: {DXC_GREY};
    margin-top: 4px;
    letter-spacing: 0.3px;
}}
</style>
""", unsafe_allow_html=True)

PRIORITY_COLORS = {
    "Critical": "#C62828",
    "High":     "#E65100",
    "Medium":   "#6D2077",
    "Low":      "#4A4A4A",
}

DXC_PALETTE = [DXC_PURPLE, "#9B26AF", "#B04FC0", "#4A1557",
               "#6D7278", "#A0A4A8", "#3D3D3D", "#D0D0D0"]

CHART_THEME = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color=DXC_TEXT, size=11, family="Segoe UI, sans-serif"),
    margin=dict(t=10, b=10, l=10, r=10),
)


# ──────────────────────────────────────────────────────────────────────────────
# Data loading
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_resource
def _engine():
    try:
        s = st.secrets["database"]
        return build_engine(s["host"], int(s["port"]), s["name"], s["user"], s["password"])
    except KeyError:
        # Local dev fallback — reads from .env
        return get_engine()


def _table_exists(engine) -> bool:
    return inspect(engine).has_table("issues")


@st.cache_data(ttl=30, show_spinner="Loading data…")
def load_data() -> pd.DataFrame:
    engine = _engine()
    if not _table_exists(engine):
        return pd.DataFrame()
    df = pd.read_sql("SELECT * FROM issues", con=engine)
    for col in ["created", "resolved", "closure_date", "sending_date",
                "qualification_date", "last_comment_datetime",
                "start_date_time", "due_date"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    for col in ["resolution_days", "occurrences", "story_points",
                "nombre_uo", "count_ready_acceptance", "count_ready_staging"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def kpi_card(label: str, value, color: str = "#FFFFFF", sub: str = ""):
    sub_html = f'<p class="kpi-sub">{sub}</p>' if sub else ""
    st.markdown(f"""
    <div class="kpi-card">
        <p class="kpi-value" style="color:{color}">{value}</p>
        <p class="kpi-label">{label}</p>
        {sub_html}
    </div>""", unsafe_allow_html=True)


def sec(title: str):
    st.markdown(f'<p class="sec-title">{title}</p>', unsafe_allow_html=True)


def sprint_group(s) -> str | None:
    """
    Normalise raw sprint strings into a canonical group name.

    22.1.25.1 / 22.1.25.2 / 22.1.25 ADDS / 22.1.25.2 ADDSc  →  v22 R25
    20.1.23.1 / 20.1.23.2                                     →  v20 R23
    TMA 22.1.19 / TMA 22.1.19 ADDS                            →  TMA v22 R19
    DATAFIX 24 / SP 7.1001 / RC W30 / …                       →  kept as-is
    """
    import re
    if pd.isna(s) or str(s).strip().lower() in ("", "none"):
        return None
    s = str(s).strip()
    # TMA prefix: TMA {major}.{minor}.{sprint_num}
    m = re.match(r"^TMA\s+(\d+)\.\d+\.(\d+)", s, re.IGNORECASE)
    if m:
        return f"TMA v{m.group(1)} R{m.group(2)}"
    # Main pattern: {major}.{minor}.{sprint_num} …
    m = re.match(r"^(\d+)\.\d+\.(\d+)", s)
    if m:
        return f"v{m.group(1)} R{m.group(2)}"
    return s


def chart(fig, **kwargs):
    _axis = dict(gridcolor=DXC_BORDER, linecolor=DXC_BORDER,
                 zerolinecolor=DXC_BORDER, tickfont=dict(color=DXC_GREY_LIGHT))
    fig.update_layout(
        **CHART_THEME,
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=DXC_TEXT)),
    )
    fig.update_xaxes(**_axis)
    fig.update_yaxes(**_axis)
    st.plotly_chart(fig, use_container_width=True, **kwargs)


def apply_filters(df: pd.DataFrame, f: dict) -> pd.DataFrame:
    if "created" in df.columns and f.get("date_range") and len(f["date_range"]) == 2:
        s, e = f["date_range"]
        df = df[df["created"].between(pd.Timestamp(s), pd.Timestamp(e))]
    for col, key in [("issue_type", "types"), ("priority", "priorities"),
                     ("project", "projects"), ("environment_type", "envs")]:
        if col in df.columns and f.get(key):
            df = df[df[col].isin(f[key])]
    return df


def shorten(s: str, n: int = 40) -> str:
    return s[:n] + "…" if len(s) > n else s


# ──────────────────────────────────────────────────────────────────────────────
# Sidebar
# ──────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown('<p class="sidebar-brand">DXC — Service Desk Analytics</p>',
                unsafe_allow_html=True)

    df_all = load_data()
    has_data = not df_all.empty

    if has_data:
        min_d = df_all["created"].min().date() if "created" in df_all else None
        max_d = df_all["created"].max().date() if "created" in df_all else None

        st.markdown('<p class="sidebar-section">Date Range</p>', unsafe_allow_html=True)
        date_range = st.date_input("Created between", value=(min_d, max_d),
                                   min_value=min_d, max_value=max_d,
                                   label_visibility="collapsed")

        st.markdown('<p class="sidebar-section">Issue Type</p>', unsafe_allow_html=True)
        all_types = sorted(df_all["issue_type"].dropna().unique())
        sel_types = st.multiselect("Issue Type", all_types, default=all_types,
                                   label_visibility="collapsed")

        st.markdown('<p class="sidebar-section">Priority</p>', unsafe_allow_html=True)
        pri_order = [p for p in ["Critical", "High", "Medium", "Low"]
                     if p in df_all["priority"].values]
        sel_pri = st.multiselect("Priority", pri_order, default=pri_order,
                                 label_visibility="collapsed")

        st.markdown('<p class="sidebar-section">Project</p>', unsafe_allow_html=True)
        all_proj = sorted(df_all["project"].dropna().unique())
        sel_proj = st.multiselect("Project", all_proj, default=all_proj,
                                  label_visibility="collapsed")

        st.markdown('<p class="sidebar-section">Environment</p>', unsafe_allow_html=True)
        all_env = sorted(df_all["environment_type"].dropna().unique())
        sel_env = st.multiselect("Environment", all_env, default=all_env,
                                 label_visibility="collapsed")

        filters = dict(
            date_range=date_range,
            types=sel_types or all_types,
            priorities=sel_pri or pri_order,
            projects=sel_proj or all_proj,
            envs=sel_env or all_env,
        )

        st.markdown("---")
        n_filtered = len(apply_filters(df_all, filters))
        st.caption(f"{n_filtered:,} of {len(df_all):,} records match filters")
    else:
        filters = {}
        st.info("No data — use the Upload tab.")


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

st.markdown('<p class="page-title">Service Desk Analytics</p>', unsafe_allow_html=True)
st.markdown('<p class="page-subtitle">Issue tracking · Performance monitoring · Sprint planning</p>', unsafe_allow_html=True)

tab_overview, tab_trends, tab_analysis, tab_sla, tab_burndown, tab_chat, tab_upload = st.tabs([
    "Overview", "Trends", "Analysis", "SLA & KPIs", "Burndown", "AI Assistant", "Upload",
])

# ── TAB 5: UPLOAD (always accessible) ─────────────────────────────────────────
with tab_upload:
    st.markdown("#### Upload Extract File")
    st.markdown(
        "Drop an Extract `.xlsx` file below. "
        "**New records** will be inserted; **existing records** (matched by Key) will be updated."
    )

    uploaded = st.file_uploader(
        "Drag & drop or click to browse",
        type=["xlsx", "xls"],
        label_visibility="collapsed",
    )

    if uploaded:
        c1, c2 = st.columns([3, 1])
        c1.info(f"**{uploaded.name}** — {uploaded.size / 1024:.1f} KB")

        mode = c2.radio("Load mode", ["Upsert (update)", "Replace all"],
                        horizontal=False, label_visibility="collapsed")

        if st.button("⚡ Process & Load into Database", type="primary"):
            with st.spinner("Reading and cleaning data…"):
                try:
                    raw = pd.read_excel(io.BytesIO(uploaded.read()), sheet_name=0)
                    cleaned = clean_data(raw)
                    st.success(f"Cleaned: **{len(cleaned):,} rows**, {len(cleaned.columns)} columns")
                except Exception as exc:
                    st.error(f"Could not read file: {exc}")
                    st.stop()

            with st.spinner("Writing to database…"):
                try:
                    eng = _engine()
                    if mode.startswith("Replace") or not _table_exists(eng):
                        n = initial_load(cleaned, eng)
                    else:
                        n = upsert(cleaned, eng)
                    st.success(f"✅ {n:,} records loaded successfully!")
                    load_data.clear()
                    st.rerun()
                except Exception as exc:
                    st.error(f"Database error: {exc}")

    st.markdown("---")
    if has_data:
        st.markdown("**Database Snapshot**")
        sc1, sc2, sc3, sc4 = st.columns(4)
        sc1.metric("Total Records", f"{len(df_all):,}")
        sc2.metric("Earliest", df_all["created"].min().strftime("%Y-%m-%d") if "created" in df_all else "—")
        sc3.metric("Latest",   df_all["created"].max().strftime("%Y-%m-%d") if "created" in df_all else "—")
        sc4.metric("Projects", df_all["project"].nunique() if "project" in df_all else "—")

if not has_data:
    for t in [tab_overview, tab_trends, tab_analysis, tab_sla, tab_burndown, tab_chat]:
        with t:
            st.info("No data available. Go to the **Upload** tab to load your Extract file.")
    st.stop()

# Apply filters to a working copy
df = apply_filters(df_all, filters)

if df.empty:
    for t in [tab_overview, tab_trends, tab_analysis, tab_sla, tab_burndown, tab_chat]:
        with t:
            st.warning("No records match the current filters.")
    st.stop()

# ── TAB 1: OVERVIEW ───────────────────────────────────────────────────────────
with tab_overview:
    total      = len(df)
    n_resolved = int(df["is_resolved"].sum()) if "is_resolved" in df else 0
    n_open     = total - n_resolved
    n_critical = int((df["priority"] == "Critical").sum())
    avg_days   = pd.to_numeric(df["resolution_days"], errors="coerce").mean() if "resolution_days" in df else 0

    sla_df   = df[df.get("sla_justified", pd.Series()).isin(["Yes", "No"])] \
               if "sla_justified" in df.columns else pd.DataFrame()
    sla_pct  = (sla_df["sla_justified"] == "Yes").sum() / len(sla_df) * 100 \
               if len(sla_df) > 0 else 0
    res_rate = n_resolved / total * 100

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1: kpi_card("Total Issues",   f"{total:,}")
    with c2: kpi_card("Open",           f"{n_open:,}",           color="#E65100")
    with c3: kpi_card("Resolved",       f"{n_resolved:,}",       color=DXC_PURPLE_LITE,
                      sub=f"{res_rate:.1f}% resolution rate")
    with c4: kpi_card("Critical",       f"{n_critical:,}",       color="#C62828")
    with c5: kpi_card("SLA Met",        f"{sla_pct:.1f}%",
                      color=DXC_PURPLE_LITE if sla_pct >= 80 else DXC_GREY_LIGHT,
                      sub=f"from {len(sla_df):,} evaluated")
    with c6: kpi_card("Avg Resolution", f"{avg_days:.1f}d",      color=DXC_PURPLE_LITE)

    st.markdown("---")

    r1c1, r1c2 = st.columns(2)

    with r1c1:
        sec("Issues by Type")
        counts = df["issue_type"].value_counts().reset_index()
        counts.columns = ["Type", "Count"]
        fig = px.pie(counts, values="Count", names="Type", hole=0.42,
                     color_discrete_sequence=DXC_PALETTE)
        fig.update_traces(textposition="inside", textinfo="percent+label")
        fig.update_layout(showlegend=False)
        chart(fig)

    with r1c2:
        sec("Issues by Priority")
        pri = (df["priority"].value_counts()
               .reindex(["Critical", "High", "Medium", "Low"]).dropna()
               .reset_index())
        pri.columns = ["Priority", "Count"]
        fig = px.bar(pri, x="Priority", y="Count", color="Priority",
                     color_discrete_map=PRIORITY_COLORS, text="Count")
        fig.update_traces(textposition="outside")
        fig.update_layout(showlegend=False)
        chart(fig)

    r2c1, r2c2 = st.columns(2)

    with r2c1:
        sec("Top 10 Statuses")
        stat = df["status"].value_counts().head(10).reset_index()
        stat.columns = ["Status", "Count"]
        fig = px.bar(stat, x="Count", y="Status", orientation="h",
                     color="Count", color_continuous_scale=[[0,"#1F1F1F"],[1,"#6D2077"]],
                     text="Count")
        fig.update_traces(textposition="outside")
        fig.update_layout(yaxis=dict(autorange="reversed"),
                          coloraxis_showscale=False)
        chart(fig)

    with r2c2:
        sec("Issues by Project")
        proj = df["project"].value_counts().reset_index()
        proj.columns = ["Project", "Count"]
        proj["Project"] = proj["Project"].apply(lambda s: shorten(s, 45))
        fig = px.bar(proj, x="Count", y="Project", orientation="h",
                     color="Count", color_continuous_scale=[[0,"#1F1F1F"],[1,"#9B26AF"]],
                     text="Count")
        fig.update_traces(textposition="outside")
        fig.update_layout(yaxis=dict(autorange="reversed"),
                          coloraxis_showscale=False)
        chart(fig)


# ── TAB 2: TRENDS ─────────────────────────────────────────────────────────────
with tab_trends:
    df_d = df[df["created"].notna()].copy() if "created" in df.columns else df.copy()

    sec("Issues Created per Month")
    monthly = (df_d.groupby("created_yearmonth").size()
               .reset_index(name="Count")
               .sort_values("created_yearmonth"))
    fig = px.area(monthly, x="created_yearmonth", y="Count",
                  color_discrete_sequence=[DXC_PURPLE],
                  markers=True)
    fig.update_layout(
                      yaxis=dict(title="Issues", gridcolor=DXC_BORDER))
    chart(fig)

    c1, c2 = st.columns(2)

    with c1:
        sec("Created vs Resolved per Month")
        cr_m = df_d.groupby("created_yearmonth").size().reset_index(name="Created")

        if "resolved" in df.columns:
            df_r = df[df["resolved"].notna()].copy()
            df_r["ym"] = df_r["resolved"].dt.to_period("M").astype(str)
            res_m = df_r.groupby("ym").size().reset_index(name="Resolved")
            res_m.rename(columns={"ym": "created_yearmonth"}, inplace=True)
            merged = (cr_m.merge(res_m, on="created_yearmonth", how="outer")
                         .fillna(0).sort_values("created_yearmonth"))
        else:
            merged = cr_m.rename(columns={"Created": "Created"})
            merged["Resolved"] = 0

        fig = go.Figure([
            go.Bar(name="Created",  x=merged["created_yearmonth"], y=merged["Created"],
                   marker_color=DXC_PURPLE),
            go.Bar(name="Resolved", x=merged["created_yearmonth"], y=merged["Resolved"],
                   marker_color="#4A7C59"),
        ])
        fig.update_layout(barmode="group",
                          **CHART_THEME)
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        sec("Issues by Day of Week")
        dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday",
                     "Friday", "Saturday", "Sunday"]
        df_d["dow"] = df_d["created"].dt.day_name()
        dow = (df_d["dow"].value_counts()
               .reindex(dow_order).fillna(0)
               .reset_index())
        dow.columns = ["Day", "Count"]
        fig = px.bar(dow, x="Day", y="Count",
                     color="Count", color_continuous_scale=[[0,"#1F1F1F"],[1,"#6D2077"]],
                     text="Count")
        fig.update_traces(textposition="outside")
        fig.update_layout(
                          coloraxis_showscale=False)
        chart(fig)

    sec("Issue Type Mix Over Time")
    type_m = (df_d.groupby(["created_yearmonth", "issue_type"])
              .size().reset_index(name="Count")
              .sort_values("created_yearmonth"))
    fig = px.area(type_m, x="created_yearmonth", y="Count", color="issue_type",
                  color_discrete_sequence=DXC_PALETTE)
    chart(fig)


# ── TAB 3: ANALYSIS ───────────────────────────────────────────────────────────
with tab_analysis:
    c1, c2 = st.columns(2)

    with c1:
        sec("Top 15 Assignees by Volume")
        top_a = df["assignee"].value_counts().head(15).reset_index()
        top_a.columns = ["Assignee", "Count"]
        fig = px.bar(top_a, x="Count", y="Assignee", orientation="h",
                     color="Count", color_continuous_scale=[[0,"#1F1F1F"],[1,"#6D2077"]], text="Count")
        fig.update_traces(textposition="outside")
        fig.update_layout(yaxis=dict(autorange="reversed"),
                          coloraxis_showscale=False)
        chart(fig)

    with c2:
        if "root_cause_origin" in df.columns:
            sec("Root Cause Origin")
            rco = df["root_cause_origin"].dropna().value_counts().reset_index()
            rco.columns = ["Root Cause", "Count"]
            fig = px.pie(rco, values="Count", names="Root Cause", hole=0.38,
                         color_discrete_sequence=DXC_PALETTE)
            fig.update_traces(textposition="inside", textinfo="percent+label")
            fig.update_layout(showlegend=False)
            chart(fig)

    c3, c4 = st.columns(2)

    with c3:
        if "environment_type" in df.columns:
            sec("Production vs Non-Production")
            env = df["environment_type"].value_counts().reset_index()
            env.columns = ["Environment", "Count"]
            fig = px.bar(env, x="Environment", y="Count",
                         color="Environment",
                         color_discrete_sequence=[DXC_PURPLE, "#6D7278"],
                         text="Count")
            fig.update_traces(textposition="outside")
            fig.update_layout(showlegend=False)
            chart(fig)

    with c4:
        if "product_line" in df.columns:
            sec("Product Line Distribution")
            pl = df["product_line"].dropna().value_counts().reset_index()
            pl.columns = ["Product Line", "Count"]
            fig = px.pie(pl, values="Count", names="Product Line", hole=0.4,
                         color_discrete_sequence=DXC_PALETTE)
            fig.update_traces(textposition="inside", textinfo="percent+label")
            fig.update_layout(showlegend=True)
            chart(fig)

    sec("Priority × Issue Type Matrix")
    pivot = (df.groupby(["priority", "issue_type"]).size()
               .unstack(fill_value=0)
               .reindex([p for p in ["Critical", "High", "Medium", "Low"]
                         if p in df["priority"].values]))
    fig = px.imshow(pivot, color_continuous_scale=[[0,"#1F1F1F"],[1,"#6D2077"]],
                    aspect="auto", text_auto=True)
    fig.update_layout(xaxis=dict(title="Issue Type"),
                      yaxis=dict(title="Priority"))
    chart(fig)

    if "resolution_owner" in df.columns:
        sec("Resolution Owner Split")
        ro = df["resolution_owner"].dropna().value_counts().reset_index()
        ro.columns = ["Owner", "Count"]
        fig = px.bar(ro, x="Owner", y="Count",
                     color="Owner",
                     color_discrete_sequence=[DXC_PURPLE, "#6D7278"],
                     text="Count")
        fig.update_traces(textposition="outside")
        fig.update_layout(showlegend=False)
        chart(fig)


# ── TAB 4: SLA & KPIs ─────────────────────────────────────────────────────────
with tab_sla:
    sla_yes = int((df["sla_justified"] == "Yes").sum()) if "sla_justified" in df else 0
    sla_no  = int((df["sla_justified"] == "No").sum())  if "sla_justified" in df else 0
    sla_tot = sla_yes + sla_no
    sla_pct = sla_yes / sla_tot * 100 if sla_tot > 0 else 0

    kc1, kc2, kc3, kc4 = st.columns(4)
    with kc1: kpi_card("SLA Met",      f"{sla_yes:,}",   color=DXC_PURPLE_LITE)
    with kc2: kpi_card("SLA Breached", f"{sla_no:,}",    color="#C62828")
    with kc3: kpi_card("Compliance",   f"{sla_pct:.1f}%",
                       color=DXC_PURPLE_LITE if sla_pct >= 80 else DXC_GREY_LIGHT,
                       sub=f"based on {sla_tot:,} evaluated")
    with kc4:
        avg_r = pd.to_numeric(df["resolution_days"], errors="coerce").median() if "resolution_days" in df else 0
        kpi_card("Median Resolution", f"{avg_r:.1f}d", color=DXC_PURPLE_LITE)

    st.markdown("---")
    c1, c2 = st.columns(2)

    with c1:
        sec("SLA Compliance by Issue Type")
        if "sla_justified" in df.columns:
            sla_t = (df[df["sla_justified"].isin(["Yes", "No"])]
                     .groupby(["issue_type", "sla_justified"])
                     .size().reset_index(name="Count"))
            fig = px.bar(sla_t, x="issue_type", y="Count", color="sla_justified",
                         color_discrete_map={"Yes": "#6D2077", "No": "#A0A4A8"},
                         barmode="stack")
            chart(fig)

    with c2:
        sec("SLA Compliance by Priority")
        if "sla_justified" in df.columns:
            sla_p = (df[df["sla_justified"].isin(["Yes", "No"])]
                     .groupby(["priority", "sla_justified"])
                     .size().reset_index(name="Count"))
            fig = px.bar(sla_p, x="priority", y="Count", color="sla_justified",
                         color_discrete_map={"Yes": "#6D2077", "No": "#A0A4A8"},
                         barmode="group",
                         category_orders={"priority": ["Critical", "High", "Medium", "Low"]})
            chart(fig)

    sec("Resolution Time Distribution (days)")
    if "resolution_days" in df.columns:
        df["resolution_days"] = pd.to_numeric(df["resolution_days"], errors="coerce")
        res_d = df[df["resolution_days"].between(0, 365, inclusive="right")].copy()
        if not res_d.empty:
            fig = px.histogram(res_d, x="resolution_days", nbins=60,
                               color="priority",
                               color_discrete_map=PRIORITY_COLORS,
                               marginal="box", opacity=0.85)
            fig.update_layout(
                              bargap=0.05)
            chart(fig)

    # KPI numeric columns (parsed from strings in ETL)
    kpi_minute_cols = [c for c in df.columns if c.endswith("_minutes") and "kpi" in c]
    if kpi_minute_cols:
        sec("KPI Time Summary")
        rows = []
        for col in kpi_minute_cols:
            label = (col.replace("kpi_", "")
                        .replace("_minutes", "")
                        .replace("_", " ")
                        .title())
            vals = df[col].dropna()
            on_time  = int((vals >= 0).sum())
            breached = int((vals < 0).sum())
            ok_vals  = vals[vals >= 0]
            avg_h    = f"{ok_vals.mean() / 60:.1f}h" if len(ok_vals) > 0 else "—"
            med_h    = f"{ok_vals.median() / 60:.1f}h" if len(ok_vals) > 0 else "—"
            rows.append({"KPI": label, "On Time": on_time, "Breached": breached,
                         "Avg (On Time)": avg_h, "Median (On Time)": med_h})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        # Gauge: KPI time to solve
        solve_col = "kpi_time_to_solve_minutes"
        if solve_col in df.columns:
            sec("KPI Time to Solve — On-time Rate")
            vals = df[solve_col].dropna()
            on  = int((vals >= 0).sum())
            tot = len(vals)
            pct = on / tot * 100 if tot > 0 else 0
            fig = go.Figure(go.Indicator(
                mode="gauge+number",
                value=pct,
                number={"suffix": "%", "font": {"color": DXC_PURPLE_LITE, "size": 48}},
                gauge=dict(
                    axis=dict(range=[0, 100], tickfont=dict(color="#cfd8dc")),
                    bar=dict(color=DXC_PURPLE),
                    steps=[
                        dict(range=[0, 60],  color="#1F1F1F"),
                        dict(range=[60, 80], color="#2A1A2E"),
                        dict(range=[80, 100],color="#3D1142"),
                    ],
                    threshold=dict(line=dict(color=DXC_PURPLE_LITE, width=3), value=80),
                ),
            ))
            fig.update_layout(height=280, **CHART_THEME)
            st.plotly_chart(fig, use_container_width=True)

# ── TAB 5: BURNDOWN ───────────────────────────────────────────────────────────
with tab_burndown:
    import datetime
    st.markdown("#### Sprint Burndown")

    if "expected_sprint" not in df_all.columns:
        st.warning("No sprint data found.")
    else:
        raw_sprints = df_all["expected_sprint"].dropna().unique().tolist()
        raw_sprints = [s for s in raw_sprints if str(s).strip().lower() not in ("", "none")]

        group_map: dict[str, list[str]] = {}
        for raw in raw_sprints:
            g = sprint_group(raw)
            if g:
                group_map.setdefault(g, []).append(raw)

        sprint_groups = sorted(group_map.keys())

        if not sprint_groups:
            st.warning("No sprint data found. The `Expected Sprint` column appears to be empty for all issues.")
        else:
            QUICK_SPRINT = "v22 R25"
            QUICK_START  = datetime.date(2026, 3, 8)
            QUICK_END    = datetime.date(2026, 3, 26)

            if st.button("Load current sprint  —  v22 R25  (08 Mar → 26 Mar 2026)"):
                st.session_state["burn_sprint"] = QUICK_SPRINT
                st.session_state["burn_start"]  = QUICK_START
                st.session_state["burn_end"]    = QUICK_END

            default_sprint_idx = sprint_groups.index(st.session_state.get("burn_sprint", sprint_groups[0])) \
                if st.session_state.get("burn_sprint") in sprint_groups else 0

            selected_group = st.selectbox(
                "Select Sprint",
                sprint_groups,
                index=default_sprint_idx,
                key="burn_sprint",
                help="Variants like v22 R25.1, v22 R25.2, v22 R25 ADDS are merged into v22 R25",
            )

            raw_values = group_map[selected_group]
            with st.expander(f"Includes {len(raw_values)} raw sprint value(s)", expanded=False):
                st.write(", ".join(sorted(raw_values)))

            dc1, dc2 = st.columns(2)
            with dc1:
                sprint_start = st.date_input("Sprint Start Date",
                                             value=st.session_state.get("burn_start", None),
                                             key="burn_start")
            with dc2:
                sprint_end = st.date_input("Sprint End Date",
                                           value=st.session_state.get("burn_end", None),
                                           key="burn_end")

            if not sprint_start or not sprint_end:
                st.info("Pick a start and end date for the sprint to generate the chart.")
            elif sprint_end <= sprint_start:
                st.error("End date must be after start date.")
            else:
                df_sprint = df_all[df_all["expected_sprint"].isin(raw_values)].copy()

                if df_sprint.empty:
                    st.warning(f"No issues found for sprint **{selected_group}**.")
                else:
                    # ── Burndown mode selector ─────────────────────────────────────
                    burn_mode = st.radio(
                        "Burndown metric",
                        ["Story Points", "Ticket Count"],
                        horizontal=True,
                        key="burn_mode",
                    )

                    if burn_mode == "Ticket Count":
                        st.caption(
                            "**Ticket Count mode** — each issue counts as 1 unit of work, "
                            "regardless of story points. Total work = number of issues in the sprint. "
                            "An issue is 'burned' on the day it was resolved. "
                            "Useful when story points are missing or unreliable, or when you want "
                            "to track delivery pace purely by issue throughput."
                        )

                    df_sprint["_resolved_at"] = df_sprint["resolved"].fillna(df_sprint["closure_date"]) \
                        if "closure_date" in df_sprint.columns else df_sprint["resolved"]

                    if burn_mode == "Story Points":
                        df_sprint["_weight"] = pd.to_numeric(df_sprint["story_points"], errors="coerce").fillna(0) \
                            if "story_points" in df_sprint.columns else 0.0
                        n_unpointed = (df_sprint["_weight"] == 0).sum()
                        if n_unpointed > 0:
                            st.caption(f"⚠️ {n_unpointed} issue(s) have no story points and contribute 0 to the burn.")
                        unit = "pts"
                    else:
                        df_sprint["_weight"] = 1.0
                        unit = "tickets"

                    total_work = df_sprint["_weight"].sum()

                    days = pd.date_range(start=sprint_start, end=sprint_end, freq="D")
                    remaining = []
                    for day in days:
                        day_ts = pd.Timestamp(day)
                        resolved_by_day = df_sprint[
                            df_sprint["_resolved_at"].notna() &
                            (df_sprint["_resolved_at"] <= day_ts + pd.Timedelta(hours=23, minutes=59))
                        ]["_weight"].sum()
                        remaining.append(total_work - resolved_by_day)

                    burn_df = pd.DataFrame({"Date": days, "Remaining": remaining})
                    n_days = len(days)
                    ideal = [total_work * (1 - i / (n_days - 1)) for i in range(n_days)] if n_days > 1 else [0]
                    burn_df["Ideal"] = ideal

                    resolved_in_sprint = df_sprint[
                        df_sprint["_resolved_at"].notna() &
                        (df_sprint["_resolved_at"] >= pd.Timestamp(sprint_start)) &
                        (df_sprint["_resolved_at"] <= pd.Timestamp(sprint_end) + pd.Timedelta(hours=23, minutes=59))
                    ]["_weight"].sum()

                    pct_done = resolved_in_sprint / total_work * 100 if total_work > 0 else 0

                    bk1, bk2, bk3, bk4 = st.columns(4)
                    with bk1: kpi_card("Sprint",     selected_group[:30])
                    with bk2: kpi_card("Total Work", f"{total_work:.0f} {unit}")
                    with bk3: kpi_card("Completed",  f"{resolved_in_sprint:.0f} {unit}",
                                       color=DXC_PURPLE_LITE if pct_done >= 80 else "#E65100")
                    with bk4: kpi_card("Done",       f"{pct_done:.1f}%",
                                       color=DXC_PURPLE_LITE if pct_done >= 80 else DXC_GREY_LIGHT)

                    st.markdown("---")
                    sec(f"Burndown — {selected_group}")

                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=burn_df["Date"], y=burn_df["Ideal"],
                        mode="lines", name="Ideal",
                        line=dict(color=DXC_GREY, width=2, dash="dash"),
                    ))
                    fig.add_trace(go.Scatter(
                        x=burn_df["Date"], y=burn_df["Remaining"],
                        mode="lines+markers+text", name="Actual Remaining",
                        line=dict(color=DXC_PURPLE_LITE, width=3),
                        marker=dict(size=6),
                        fill="tozeroy", fillcolor="rgba(109,32,119,0.12)",
                        text=[f"{v:.1f}" for v in burn_df["Remaining"]],
                        textposition="top center",
                        textfont=dict(color=DXC_PURPLE_LITE, size=11),
                    ))
                    fig.add_trace(go.Scatter(
                        x=pd.concat([burn_df["Date"], burn_df["Date"][::-1]]).tolist(),
                        y=pd.concat([burn_df["Ideal"], burn_df["Remaining"][::-1]]).tolist(),
                        fill="toself", fillcolor="rgba(255,255,255,0.04)",
                        line=dict(color="rgba(0,0,0,0)"),
                        hoverinfo="skip", name="Deviation", showlegend=True,
                    ))
                    fig.update_layout(
                        yaxis=dict(title=f"Remaining ({unit})", gridcolor=DXC_BORDER),
                        hovermode="x unified", **CHART_THEME,
                    )
                    chart(fig)

                    with st.expander("Daily breakdown"):
                        burn_df["Burned Today"] = burn_df["Remaining"].shift(1).fillna(total_work) - burn_df["Remaining"]
                        burn_df["% Done"] = ((total_work - burn_df["Remaining"]) / total_work * 100).round(1)
                        burn_df["Date"] = burn_df["Date"].dt.strftime("%Y-%m-%d")
                        burn_df["Remaining"] = burn_df["Remaining"].round(1)
                        burn_df["Ideal"] = burn_df["Ideal"].round(1)
                        burn_df["Burned Today"] = burn_df["Burned Today"].round(1)
                        st.dataframe(burn_df[["Date", "Remaining", "Ideal", "Burned Today", "% Done"]],
                                     use_container_width=True, hide_index=True)

                    with st.expander(f"Issues in this sprint ({len(df_sprint)})"):
                        show_cols = [c for c in ["key", "summary", "issue_type", "priority",
                                                  "status", "story_points", "_resolved_at"]
                                     if c in df_sprint.columns]
                        st.dataframe(df_sprint[show_cols].rename(columns={"_resolved_at": "resolved_at"}),
                                     use_container_width=True, hide_index=True)

                    # ── Carried-over issues ────────────────────────────────────────────
                    st.markdown("---")
                    sec("Carried-Over Issues")
                    st.caption(
                        "Issues currently assigned to this sprint whose **Original Expected Sprint** "
                        "was a different sprint — meaning they slipped from a previous delivery."
                    )

                    if "original_expected_sprint" not in df_sprint.columns:
                        st.info(
                            "The `Original Expected Sprint` column is not in the database. "
                            "Re-upload your extract using **Replace all** to capture it."
                        )
                    else:
                        # Normalise original sprint and compare to current sprint group
                        df_sprint["_orig_group"] = df_sprint["original_expected_sprint"].apply(sprint_group)
                        carried = df_sprint[
                            df_sprint["_orig_group"].notna() &
                            (df_sprint["_orig_group"] != selected_group)
                        ].copy()

                        co1, co2, co3, co4 = st.columns(4)
                        with co1: kpi_card("Carried Over", f"{len(carried)}", color="#E65100")
                        with co2: kpi_card("Of Sprint Total", f"{len(carried)/len(df_sprint)*100:.1f}%", color="#E65100")
                        with co3:
                            co_pts = carried["_weight"].sum()
                            co_label = "Carried Points" if unit == "pts" else "Carried Tickets"
                            kpi_card(co_label, f"{co_pts:.0f} {unit}", color="#E65100")
                        with co4:
                            co_open = int((carried["is_resolved"] == 0).sum()) if "is_resolved" in carried.columns else "—"
                            kpi_card("Still Open", f"{co_open}", color="#C62828")

                        if carried.empty:
                            st.success("No carried-over issues — all tickets in this sprint were originally planned here.")
                        else:
                            # Group by original sprint for a summary
                            origin_summary = (
                                carried.groupby("_orig_group")
                                .agg(
                                    Issues=("key", "count"),
                                    Story_Points=("_weight", "sum"),
                                    Open=("is_resolved", lambda x: (x == 0).sum() if "is_resolved" in carried.columns else 0),
                                )
                                .reset_index()
                                .rename(columns={"_orig_group": "Original Sprint", "Story_Points": "Story Points"})
                                .sort_values("Issues", ascending=False)
                            )
                            origin_summary["Story Points"] = origin_summary["Story Points"].round(1)

                            sec("Where Did They Come From?")
                            fig = px.bar(
                                origin_summary,
                                x="Issues", y="Original Sprint",
                                orientation="h",
                                color="Issues",
                                color_continuous_scale=[[0, "#2A1A1A"], [1, "#C62828"]],
                                text="Issues",
                            )
                            fig.update_traces(textposition="outside")
                            fig.update_layout(
                                yaxis=dict(autorange="reversed"),
                                coloraxis_showscale=False,
                            )
                            chart(fig)

                            sec("Carried-Over Issue Details")
                            detail_cols = [c for c in [
                                "key", "summary", "priority", "status",
                                "_orig_group", "story_points", "_resolved_at", "assignee"
                            ] if c in carried.columns]
                            st.dataframe(
                                carried[detail_cols]
                                .rename(columns={"_orig_group": "original_sprint", "_resolved_at": "resolved_at"})
                                .sort_values("priority", key=lambda s: s.map(
                                    {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
                                ).fillna(4)),
                                use_container_width=True,
                                hide_index=True,
                            )


# ── TAB: AI ASSISTANT ─────────────────────────────────────────────────────────
with tab_chat:
    st.markdown("#### AI Analytics Assistant")
    st.caption("Ask questions about your data in plain English. The assistant queries the live database to answer.")

    # ── API key status banner ─────────────────────────────────────────────────
    api_ready = check_api_key()
    if not api_ready:
        st.warning(
            "**API key not configured.** The assistant is ready but inactive.\n\n"
            "To activate:\n"
            "1. Get a key at [console.anthropic.com](https://console.anthropic.com)\n"
            "2. Add to your `.env` file:  `ANTHROPIC_API_KEY=sk-ant-...`\n"
            "3. Restart the app",
            icon="🔑",
        )

    # ── Preview panel (shown only when no API key) ────────────────────────────
    if not api_ready:
        st.markdown('<p class="sec-title">Preview — Example Conversation</p>', unsafe_allow_html=True)
        st.caption("This is how the assistant will respond once your API key is configured.")

        DEMO = [
            ("user",      "Give me an overall summary of the current state of the service desk."),
            ("assistant", (
                "Here's the current snapshot of your service desk:\n\n"
                "| Metric | Value |\n"
                "|---|---|\n"
                "| Total Issues | 7,750 |\n"
                "| Open | 3,214 |\n"
                "| Resolved | 4,536 |\n"
                "| Resolution Rate | 58.5% |\n"
                "| Critical Open | 47 |\n"
                "| SLA Compliance | 72.3% |\n"
                "| Avg Resolution Time | 8.4 days |\n\n"
                "**Key observations:**\n"
                "- SLA compliance is below the 80% target — worth investigating which issue types are driving breaches.\n"
                "- 47 critical issues remain open. I'd recommend prioritising those immediately.\n"
                "- Resolution rate has improved 4.2% compared to last month.\n\n"
                "Would you like me to drill into SLA breaches by priority, or show you who owns the open critical issues?"
            )),
            ("user",      "Who owns the open critical issues?"),
            ("assistant", (
                "Here are the assignees with the most open critical issues:\n\n"
                "| Assignee | Open Critical | Total Open | Avg Days Open |\n"
                "|---|---|---|---|\n"
                "| Alice Martin | 9 | 34 | 12.1 |\n"
                "| Bob Nguyen | 7 | 28 | 9.4 |\n"
                "| Sara Dupont | 6 | 19 | 15.7 |\n"
                "| Unassigned | 11 | 52 | — |\n\n"
                "**Note:** 11 critical issues are currently unassigned — these should be triaged immediately as they have no owner."
            )),
        ]
        for role, content in DEMO:
            with st.chat_message(role):
                st.markdown(content)

        st.markdown("---")

    # ── Suggested prompts ────────────────────────────────────────────────────
    st.markdown('<p class="sec-title">Suggested Questions</p>', unsafe_allow_html=True)
    suggestions = [
        "Give me an overall summary of the current state of the service desk.",
        "What is our SLA compliance rate and how has it trended over the last 6 months?",
        "Which assignees have the highest and lowest resolution rates?",
        "How many critical issues are currently open and who owns them?",
        "Is sprint v22 R25 on track to complete on time?",
        "Which projects have the most unresolved issues right now?",
        "Show me the monthly trend of issues created vs resolved for this year.",
        "What are the most common root cause origins for our bugs?",
    ]

    cols = st.columns(2)
    for i, s in enumerate(suggestions):
        if cols[i % 2].button(s, key=f"suggestion_{i}", use_container_width=True):
            st.session_state["chat_prefill"] = s

    st.markdown("---")

    # ── Conversation history ──────────────────────────────────────────────────
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []      # Claude message format
    if "chat_display" not in st.session_state:
        st.session_state.chat_display = []      # {"role", "content"} for display

    # Render prior messages
    for msg in st.session_state.chat_display:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Handle suggestion button prefill
    prefill = st.session_state.pop("chat_prefill", None)

    # ── Input ─────────────────────────────────────────────────────────────────
    prompt = st.chat_input("Ask anything about your service desk data…")
    if not prompt and prefill:
        prompt = prefill

    if prompt:
        # Show user message immediately
        st.session_state.chat_display.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Run agent
        with st.chat_message("assistant"):
            with st.spinner("Querying database…"):
                reply = run_agent(
                    user_message=prompt,
                    engine=_engine(),
                    history=st.session_state.chat_history,
                )
            st.markdown(reply)

        # Update histories
        st.session_state.chat_display.append({"role": "assistant", "content": reply})
        st.session_state.chat_history.append({"role": "user",      "content": prompt})
        st.session_state.chat_history.append({"role": "assistant", "content": reply})

    # ── Clear conversation ────────────────────────────────────────────────────
    if st.session_state.chat_display:
        if st.button("Clear conversation", key="clear_chat"):
            st.session_state.chat_history = []
            st.session_state.chat_display = []
            st.rerun()
