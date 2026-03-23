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

from etl import clean_data, upsert, initial_load, get_engine

load_dotenv()

# ──────────────────────────────────────────────────────────────────────────────
# Page config & global styles
# ──────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Issue Tracking Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
/* ── Card ── */
.kpi-card {
    background: linear-gradient(135deg, #1a2f4a 0%, #0f1e30 100%);
    border: 1px solid #2a4a6e;
    border-radius: 14px;
    padding: 22px 16px 18px 16px;
    text-align: center;
    margin-bottom: 4px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.4);
}
.kpi-value {
    font-size: 2.4rem;
    font-weight: 700;
    margin: 0 0 4px 0;
    line-height: 1;
}
.kpi-label {
    font-size: 0.72rem;
    color: #8ab4d8;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    margin: 0;
}
.kpi-sub {
    font-size: 0.75rem;
    color: #607d8b;
    margin-top: 6px;
}

/* ── Section title ── */
.sec-title {
    font-size: 1.05rem;
    font-weight: 600;
    color: #cfd8dc;
    border-left: 3px solid #1e88e5;
    padding-left: 10px;
    margin: 24px 0 10px 0;
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] { gap: 6px; }
.stTabs [data-baseweb="tab"] {
    background: #1a2f4a;
    border-radius: 8px 8px 0 0;
    padding: 8px 18px;
    color: #8ab4d8;
    font-size: 0.88rem;
}
.stTabs [aria-selected="true"] {
    background: #1e88e5 !important;
    color: #fff !important;
}

/* ── Upload zone ── */
.upload-hint {
    background: #0d1b2a;
    border: 2px dashed #2a4a6e;
    border-radius: 12px;
    padding: 28px;
    text-align: center;
    color: #607d8b;
    font-size: 0.9rem;
}
</style>
""", unsafe_allow_html=True)

PRIORITY_COLORS = {
    "Critical": "#e53935",
    "High":     "#fb8c00",
    "Medium":   "#1e88e5",
    "Low":      "#43a047",
}

CHART_THEME = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#cfd8dc", size=12),
    margin=dict(t=10, b=10, l=10, r=10),
)


# ──────────────────────────────────────────────────────────────────────────────
# Data loading
# ──────────────────────────────────────────────────────────────────────────────

@st.cache_resource
def _engine():
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

def kpi_card(label: str, value, color: str = "#4fc3f7", sub: str = ""):
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

    22.1.25.1 / 22.1.25.2 / 22.1.25 ADDS / 22.1.25.2 ADDSc  →  R25
    TMA 22.1.19 / TMA 22.1.19 ADDS                            →  TMA R19
    DATAFIX 24 / SP 7.1001 / RC W30 / …                       →  kept as-is
    """
    import re
    if pd.isna(s) or str(s).strip().lower() in ("", "none"):
        return None
    s = str(s).strip()
    # TMA prefix
    m = re.match(r"^TMA\s+\d+\.\d+\.(\d+)", s, re.IGNORECASE)
    if m:
        return f"TMA R{m.group(1)}"
    # Main pattern: {major}.{minor}.{sprint_num} …
    m = re.match(r"^\d+\.\d+\.(\d+)", s)
    if m:
        return f"R{m.group(1)}"
    return s


def chart(fig, **kwargs):
    fig.update_layout(**CHART_THEME)
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
    st.markdown("## 📊 Report System")
    st.markdown("---")

    df_all = load_data()
    has_data = not df_all.empty

    if has_data:
        st.markdown("### Filters")

        min_d = df_all["created"].min().date() if "created" in df_all else None
        max_d = df_all["created"].max().date() if "created" in df_all else None

        date_range = st.date_input("Date Range (Created)", value=(min_d, max_d),
                                   min_value=min_d, max_value=max_d)

        all_types = sorted(df_all["issue_type"].dropna().unique())
        sel_types = st.multiselect("Issue Type", all_types, default=all_types)

        pri_order = [p for p in ["Critical", "High", "Medium", "Low"]
                     if p in df_all["priority"].values]
        sel_pri = st.multiselect("Priority", pri_order, default=pri_order)

        all_proj = sorted(df_all["project"].dropna().unique())
        sel_proj = st.multiselect("Project", all_proj, default=all_proj)

        all_env = sorted(df_all["environment_type"].dropna().unique())
        sel_env = st.multiselect("Environment", all_env, default=all_env)

        filters = dict(
            date_range=date_range,
            types=sel_types or all_types,
            priorities=sel_pri or pri_order,
            projects=sel_proj or all_proj,
            envs=sel_env or all_env,
        )

        st.markdown("---")
        st.caption(f"Total records in DB: **{len(df_all):,}**")
    else:
        filters = {}
        st.info("No data yet — use the **Upload** tab to load your first Extract file.")


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

st.title("📊 Issue Tracking Dashboard")

tab_overview, tab_trends, tab_analysis, tab_sla, tab_burndown, tab_upload = st.tabs([
    "📋 Overview", "📈 Trends", "🔍 Analysis", "⏱️ SLA & KPIs", "🔥 Burndown", "📤 Upload",
])

# ── TAB 5: UPLOAD (always accessible) ─────────────────────────────────────────
with tab_upload:
    st.markdown("### Upload a New Extract File")
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
        st.markdown("#### Current Database Snapshot")
        sc1, sc2, sc3, sc4 = st.columns(4)
        sc1.metric("Total Records", f"{len(df_all):,}")
        sc2.metric("Earliest", df_all["created"].min().strftime("%Y-%m-%d") if "created" in df_all else "—")
        sc3.metric("Latest",   df_all["created"].max().strftime("%Y-%m-%d") if "created" in df_all else "—")
        sc4.metric("Projects", df_all["project"].nunique() if "project" in df_all else "—")

if not has_data:
    for t in [tab_overview, tab_trends, tab_analysis, tab_sla, tab_burndown]:
        with t:
            st.info("No data available. Go to the **Upload** tab to load your Extract file.")
    st.stop()

# Apply filters to a working copy
df = apply_filters(df_all, filters)

if df.empty:
    for t in [tab_overview, tab_trends, tab_analysis, tab_sla, tab_burndown]:
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
    with c2: kpi_card("Open",           f"{n_open:,}",           color="#fb8c00")
    with c3: kpi_card("Resolved",       f"{n_resolved:,}",       color="#43a047",
                      sub=f"{res_rate:.1f}% resolution rate")
    with c4: kpi_card("Critical",       f"{n_critical:,}",       color="#e53935")
    with c5: kpi_card("SLA Met",        f"{sla_pct:.1f}%",
                      color="#43a047" if sla_pct >= 80 else "#e53935",
                      sub=f"from {len(sla_df):,} evaluated")
    with c6: kpi_card("Avg Resolution", f"{avg_days:.1f}d",      color="#4fc3f7")

    st.markdown("---")

    r1c1, r1c2 = st.columns(2)

    with r1c1:
        sec("Issues by Type")
        counts = df["issue_type"].value_counts().reset_index()
        counts.columns = ["Type", "Count"]
        fig = px.pie(counts, values="Count", names="Type", hole=0.42,
                     color_discrete_sequence=px.colors.qualitative.Set2)
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
        fig.update_layout(showlegend=False,
                          xaxis=dict(gridcolor="#1e3a5f"),
                          yaxis=dict(gridcolor="#1e3a5f"))
        chart(fig)

    r2c1, r2c2 = st.columns(2)

    with r2c1:
        sec("Top 10 Statuses")
        stat = df["status"].value_counts().head(10).reset_index()
        stat.columns = ["Status", "Count"]
        fig = px.bar(stat, x="Count", y="Status", orientation="h",
                     color="Count", color_continuous_scale="Blues",
                     text="Count")
        fig.update_traces(textposition="outside")
        fig.update_layout(yaxis=dict(autorange="reversed"),
                          xaxis=dict(gridcolor="#1e3a5f"),
                          coloraxis_showscale=False)
        chart(fig)

    with r2c2:
        sec("Issues by Project")
        proj = df["project"].value_counts().reset_index()
        proj.columns = ["Project", "Count"]
        proj["Project"] = proj["Project"].apply(lambda s: shorten(s, 45))
        fig = px.bar(proj, x="Count", y="Project", orientation="h",
                     color="Count", color_continuous_scale="Teal",
                     text="Count")
        fig.update_traces(textposition="outside")
        fig.update_layout(yaxis=dict(autorange="reversed"),
                          xaxis=dict(gridcolor="#1e3a5f"),
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
                  color_discrete_sequence=["#1e88e5"],
                  markers=True)
    fig.update_layout(xaxis=dict(title="Month", gridcolor="#1e3a5f"),
                      yaxis=dict(title="Issues", gridcolor="#1e3a5f"))
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
                   marker_color="#1e88e5"),
            go.Bar(name="Resolved", x=merged["created_yearmonth"], y=merged["Resolved"],
                   marker_color="#43a047"),
        ])
        fig.update_layout(barmode="group",
                          xaxis=dict(gridcolor="#1e3a5f"),
                          yaxis=dict(gridcolor="#1e3a5f"),
                          legend=dict(bgcolor="rgba(0,0,0,0)"),
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
                     color="Count", color_continuous_scale="Blues",
                     text="Count")
        fig.update_traces(textposition="outside")
        fig.update_layout(xaxis=dict(gridcolor="#1e3a5f"),
                          yaxis=dict(gridcolor="#1e3a5f"),
                          coloraxis_showscale=False)
        chart(fig)

    sec("Issue Type Mix Over Time")
    type_m = (df_d.groupby(["created_yearmonth", "issue_type"])
              .size().reset_index(name="Count")
              .sort_values("created_yearmonth"))
    fig = px.area(type_m, x="created_yearmonth", y="Count", color="issue_type",
                  color_discrete_sequence=px.colors.qualitative.Set2)
    fig.update_layout(xaxis=dict(gridcolor="#1e3a5f"),
                      yaxis=dict(gridcolor="#1e3a5f"),
                      legend=dict(bgcolor="rgba(0,0,0,0)", title="Type"))
    chart(fig)


# ── TAB 3: ANALYSIS ───────────────────────────────────────────────────────────
with tab_analysis:
    c1, c2 = st.columns(2)

    with c1:
        sec("Top 15 Assignees by Volume")
        top_a = df["assignee"].value_counts().head(15).reset_index()
        top_a.columns = ["Assignee", "Count"]
        fig = px.bar(top_a, x="Count", y="Assignee", orientation="h",
                     color="Count", color_continuous_scale="Blues", text="Count")
        fig.update_traces(textposition="outside")
        fig.update_layout(yaxis=dict(autorange="reversed"),
                          xaxis=dict(gridcolor="#1e3a5f"),
                          coloraxis_showscale=False)
        chart(fig)

    with c2:
        if "root_cause_origin" in df.columns:
            sec("Root Cause Origin")
            rco = df["root_cause_origin"].dropna().value_counts().reset_index()
            rco.columns = ["Root Cause", "Count"]
            fig = px.pie(rco, values="Count", names="Root Cause", hole=0.38,
                         color_discrete_sequence=px.colors.qualitative.Pastel)
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
                         color_discrete_sequence=["#1e88e5", "#fb8c00"],
                         text="Count")
            fig.update_traces(textposition="outside")
            fig.update_layout(showlegend=False,
                              xaxis=dict(gridcolor="#1e3a5f"),
                              yaxis=dict(gridcolor="#1e3a5f"))
            chart(fig)

    with c4:
        if "product_line" in df.columns:
            sec("Product Line Distribution")
            pl = df["product_line"].dropna().value_counts().reset_index()
            pl.columns = ["Product Line", "Count"]
            fig = px.pie(pl, values="Count", names="Product Line", hole=0.4,
                         color_discrete_sequence=["#1e88e5", "#fb8c00", "#43a047"])
            fig.update_traces(textposition="inside", textinfo="percent+label")
            fig.update_layout(showlegend=True,
                              legend=dict(bgcolor="rgba(0,0,0,0)"))
            chart(fig)

    sec("Priority × Issue Type Matrix")
    pivot = (df.groupby(["priority", "issue_type"]).size()
               .unstack(fill_value=0)
               .reindex([p for p in ["Critical", "High", "Medium", "Low"]
                         if p in df["priority"].values]))
    fig = px.imshow(pivot, color_continuous_scale="Blues",
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
                     color_discrete_sequence=["#1e88e5", "#43a047"],
                     text="Count")
        fig.update_traces(textposition="outside")
        fig.update_layout(showlegend=False,
                          xaxis=dict(gridcolor="#1e3a5f"),
                          yaxis=dict(gridcolor="#1e3a5f"))
        chart(fig)


# ── TAB 4: SLA & KPIs ─────────────────────────────────────────────────────────
with tab_sla:
    sla_yes = int((df["sla_justified"] == "Yes").sum()) if "sla_justified" in df else 0
    sla_no  = int((df["sla_justified"] == "No").sum())  if "sla_justified" in df else 0
    sla_tot = sla_yes + sla_no
    sla_pct = sla_yes / sla_tot * 100 if sla_tot > 0 else 0

    kc1, kc2, kc3, kc4 = st.columns(4)
    with kc1: kpi_card("SLA Met",      f"{sla_yes:,}",   color="#43a047")
    with kc2: kpi_card("SLA Breached", f"{sla_no:,}",    color="#e53935")
    with kc3: kpi_card("Compliance",   f"{sla_pct:.1f}%",
                       color="#43a047" if sla_pct >= 80 else "#e53935",
                       sub=f"based on {sla_tot:,} evaluated")
    with kc4:
        avg_r = pd.to_numeric(df["resolution_days"], errors="coerce").median() if "resolution_days" in df else 0
        kpi_card("Median Resolution", f"{avg_r:.1f}d", color="#4fc3f7")

    st.markdown("---")
    c1, c2 = st.columns(2)

    with c1:
        sec("SLA Compliance by Issue Type")
        if "sla_justified" in df.columns:
            sla_t = (df[df["sla_justified"].isin(["Yes", "No"])]
                     .groupby(["issue_type", "sla_justified"])
                     .size().reset_index(name="Count"))
            fig = px.bar(sla_t, x="issue_type", y="Count", color="sla_justified",
                         color_discrete_map={"Yes": "#43a047", "No": "#e53935"},
                         barmode="stack")
            fig.update_layout(xaxis=dict(gridcolor="#1e3a5f", title=""),
                              yaxis=dict(gridcolor="#1e3a5f"),
                              legend=dict(bgcolor="rgba(0,0,0,0)", title="SLA Met"))
            chart(fig)

    with c2:
        sec("SLA Compliance by Priority")
        if "sla_justified" in df.columns:
            sla_p = (df[df["sla_justified"].isin(["Yes", "No"])]
                     .groupby(["priority", "sla_justified"])
                     .size().reset_index(name="Count"))
            fig = px.bar(sla_p, x="priority", y="Count", color="sla_justified",
                         color_discrete_map={"Yes": "#43a047", "No": "#e53935"},
                         barmode="group",
                         category_orders={"priority": ["Critical", "High", "Medium", "Low"]})
            fig.update_layout(xaxis=dict(gridcolor="#1e3a5f", title=""),
                              yaxis=dict(gridcolor="#1e3a5f"),
                              legend=dict(bgcolor="rgba(0,0,0,0)", title="SLA Met"))
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
            fig.update_layout(xaxis=dict(title="Days to Resolve", gridcolor="#1e3a5f"),
                              yaxis=dict(gridcolor="#1e3a5f"),
                              legend=dict(bgcolor="rgba(0,0,0,0)"),
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
                number={"suffix": "%", "font": {"color": "#4fc3f7", "size": 48}},
                gauge=dict(
                    axis=dict(range=[0, 100], tickfont=dict(color="#cfd8dc")),
                    bar=dict(color="#1e88e5"),
                    steps=[
                        dict(range=[0, 60],  color="#2a1a1a"),
                        dict(range=[60, 80], color="#2a2a1a"),
                        dict(range=[80, 100],color="#1a2a1a"),
                    ],
                    threshold=dict(line=dict(color="#43a047", width=3), value=80),
                ),
            ))
            fig.update_layout(height=280, **CHART_THEME)
            st.plotly_chart(fig, use_container_width=True)

# ── TAB 5: BURNDOWN ───────────────────────────────────────────────────────────
with tab_burndown:
    st.markdown("### Sprint Burndown Chart")

    # ── Sprint selector ───────────────────────────────────────────────────────
    if "expected_sprint" not in df_all.columns:
        st.warning("No sprint data found.")
        st.stop()

    # Build group → [raw values] map
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
        st.stop()

    col_sel, col_metric = st.columns([2, 1])
    with col_sel:
        selected_group = st.selectbox(
            "Select Sprint",
            sprint_groups,
            help="Variants like R25.1, R25.2, R25 ADDS are merged into R25",
        )
    with col_metric:
        burn_metric = st.radio("Measure by", ["Issue Count", "Story Points"], horizontal=True)

    # Show which raw values are included
    raw_values = group_map[selected_group]
    with st.expander(f"Includes {len(raw_values)} raw sprint value(s)", expanded=False):
        st.write(", ".join(sorted(raw_values)))

    # ── Date range ────────────────────────────────────────────────────────────
    dc1, dc2 = st.columns(2)
    with dc1:
        sprint_start = st.date_input("Sprint Start Date", value=None, key="burn_start")
    with dc2:
        sprint_end = st.date_input("Sprint End Date", value=None, key="burn_end")

    if not sprint_start or not sprint_end:
        st.info("Pick a start and end date for the sprint to generate the chart.")
        st.stop()

    if sprint_end <= sprint_start:
        st.error("End date must be after start date.")
        st.stop()

    # ── Filter issues for this sprint group ───────────────────────────────────
    df_sprint = df_all[df_all["expected_sprint"].isin(raw_values)].copy()

    if df_sprint.empty:
        st.warning(f"No issues found for sprint **{selected_group}**.")
        st.stop()

    # Determine resolution date (use resolved, fallback to closure_date)
    df_sprint["_resolved_at"] = df_sprint["resolved"].fillna(df_sprint["closure_date"]) \
        if "closure_date" in df_sprint.columns else df_sprint["resolved"]

    # Story points: fall back to 1 per issue if missing
    use_points = burn_metric == "Story Points" and "story_points" in df_sprint.columns
    if use_points:
        df_sprint["_weight"] = pd.to_numeric(df_sprint["story_points"], errors="coerce").fillna(1)
    else:
        df_sprint["_weight"] = 1.0

    total_work = df_sprint["_weight"].sum()

    # ── Build daily remaining series ──────────────────────────────────────────
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

    # Ideal straight-line burndown
    n_days = len(days)
    ideal = [total_work * (1 - i / (n_days - 1)) for i in range(n_days)] if n_days > 1 else [0]
    burn_df["Ideal"] = ideal

    # ── KPI cards ─────────────────────────────────────────────────────────────
    resolved_in_sprint = df_sprint[
        df_sprint["_resolved_at"].notna() &
        (df_sprint["_resolved_at"] >= pd.Timestamp(sprint_start)) &
        (df_sprint["_resolved_at"] <= pd.Timestamp(sprint_end) + pd.Timedelta(hours=23, minutes=59))
    ]["_weight"].sum()

    pct_done = resolved_in_sprint / total_work * 100 if total_work > 0 else 0
    unit = "pts" if use_points else "issues"

    bk1, bk2, bk3, bk4 = st.columns(4)
    with bk1: kpi_card("Sprint",        selected_group[:30])
    with bk2: kpi_card("Total Work",    f"{total_work:.0f} {unit}")
    with bk3: kpi_card("Completed",     f"{resolved_in_sprint:.0f} {unit}",
                       color="#43a047" if pct_done >= 80 else "#fb8c00")
    with bk4: kpi_card("Done",          f"{pct_done:.1f}%",
                       color="#43a047" if pct_done >= 80 else "#e53935")

    st.markdown("---")

    # ── Burndown chart ────────────────────────────────────────────────────────
    sec(f"Burndown — {selected_group}")

    fig = go.Figure()

    # Ideal line
    fig.add_trace(go.Scatter(
        x=burn_df["Date"], y=burn_df["Ideal"],
        mode="lines",
        name="Ideal",
        line=dict(color="#607d8b", width=2, dash="dash"),
    ))

    # Actual burn
    fig.add_trace(go.Scatter(
        x=burn_df["Date"], y=burn_df["Remaining"],
        mode="lines+markers",
        name="Actual Remaining",
        line=dict(color="#1e88e5", width=3),
        marker=dict(size=6),
        fill="tozeroy",
        fillcolor="rgba(30,136,229,0.10)",
    ))

    # Shade the area between actual and ideal
    fig.add_trace(go.Scatter(
        x=pd.concat([burn_df["Date"], burn_df["Date"][::-1]]).tolist(),
        y=pd.concat([burn_df["Ideal"], burn_df["Remaining"][::-1]]).tolist(),
        fill="toself",
        fillcolor="rgba(229,57,53,0.08)",
        line=dict(color="rgba(0,0,0,0)"),
        hoverinfo="skip",
        name="Deviation",
        showlegend=True,
    ))

    fig.update_layout(
        xaxis=dict(title="Date", gridcolor="#1e3a5f", tickformat="%b %d"),
        yaxis=dict(title=f"Remaining ({unit})", gridcolor="#1e3a5f"),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        hovermode="x unified",
        **CHART_THEME,
    )
    chart(fig)

    # ── Daily completion table ────────────────────────────────────────────────
    with st.expander("Daily breakdown"):
        burn_df["Burned Today"] = burn_df["Remaining"].shift(1).fillna(total_work) - burn_df["Remaining"]
        burn_df["% Done"] = ((total_work - burn_df["Remaining"]) / total_work * 100).round(1)
        burn_df["Date"] = burn_df["Date"].dt.strftime("%Y-%m-%d")
        burn_df["Remaining"] = burn_df["Remaining"].round(1)
        burn_df["Ideal"] = burn_df["Ideal"].round(1)
        burn_df["Burned Today"] = burn_df["Burned Today"].round(1)
        st.dataframe(burn_df[["Date", "Remaining", "Ideal", "Burned Today", "% Done"]],
                     use_container_width=True, hide_index=True)

    # ── Issues in sprint ──────────────────────────────────────────────────────
    with st.expander(f"Issues in this sprint ({len(df_sprint)})"):
        show_cols = [c for c in ["key", "summary", "issue_type", "priority",
                                  "status", "story_points", "_resolved_at"]
                     if c in df_sprint.columns]
        st.dataframe(df_sprint[show_cols].rename(columns={"_resolved_at": "resolved_at"}),
                     use_container_width=True, hide_index=True)
