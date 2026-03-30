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

from etl import clean_data, upsert, initial_load, build_engine, get_engine, load_release_lifecycle
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

# ── DXC colour tokens (light theme) ───────────────────────────────────────────
DXC_PURPLE      = "#6D2077"
DXC_PURPLE_LITE = "#9B26AF"
DXC_PURPLE_DIM  = "#EDE0F0"
DXC_BLACK       = "#FFFFFF"       # main background
DXC_SURFACE     = "#F5F4F7"       # sidebar / card background
DXC_SURFACE2    = "#FFFFFF"       # input / widget background
DXC_BORDER      = "#E0D9E6"       # borders
DXC_GREY        = "#5A5A6A"       # muted text
DXC_GREY_LIGHT  = "#8A8A9A"       # very muted text
DXC_TEXT        = "#1A1A2E"       # primary text
DXC_TEXT_DIM    = "#6D6D80"       # secondary text
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
    color: {DXC_PURPLE} !important;
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
    background-color: {DXC_SURFACE};
    border: 1px solid {DXC_BORDER};
    border-top: 3px solid {DXC_PURPLE};
    border-radius: 6px;
    padding: 20px 16px 16px 16px;
    text-align: center;
    margin-bottom: 4px;
}}
.kpi-value {{
    font-size: 2.2rem;
    font-weight: 700;
    margin: 0 0 6px 0;
    line-height: 1;
    color: {DXC_TEXT};
}}
.kpi-label {{
    font-size: 0.68rem;
    color: {DXC_GREY};
    text-transform: uppercase;
    letter-spacing: 1.4px;
    margin: 0;
}}
.kpi-sub {{
    font-size: 0.72rem;
    color: {DXC_GREY_LIGHT};
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
    border-bottom: 2px solid {DXC_BORDER};
    padding: 0 4px;
}}
.stTabs [data-baseweb="tab"] {{
    background: transparent;
    border-radius: 0;
    padding: 10px 20px;
    color: {DXC_GREY};
    font-size: 0.82rem;
    font-weight: 500;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    border-bottom: 2px solid transparent;
}}
.stTabs [aria-selected="true"] {{
    background: transparent !important;
    color: {DXC_PURPLE} !important;
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
    border-radius: 6px !important;
    background-color: {DXC_SURFACE} !important;
}}

/* ── Dataframe ── */
[data-testid="stDataFrame"] {{
    border: 1px solid {DXC_BORDER};
    border-radius: 6px;
}}

/* ── Page title ── */
.page-title {{
    font-size: 1.5rem;
    font-weight: 700;
    color: {DXC_PURPLE};
    letter-spacing: 0.5px;
    margin-bottom: 0;
    padding-bottom: 12px;
    border-bottom: 2px solid {DXC_PURPLE};
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
# Light-mode grid colour used in per-chart xaxis/yaxis overrides
_GRID = "#E8E2EE"


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


def _rl_table_exists(engine) -> bool:
    return inspect(engine).has_table("r25_scope")


@st.cache_data(ttl=3600, show_spinner=False)
def load_r25_scope() -> pd.DataFrame:
    """Load scope from DB (r25_scope table), fall back to local Excel."""
    try:
        eng = _engine()
        if _rl_table_exists(eng):
            scope = pd.read_sql("SELECT * FROM r25_scope", con=eng)
            return scope
    except Exception:
        pass

    # ── Local file fallback ───────────────────────────────────────────────────
    _raw = pd.read_excel("data/Release_lifecycle_R25.xlsx", sheet_name="Scope UPDATE", header=0)
    _raw.columns = [str(c).strip() for c in _raw.columns]
    scope = _raw[["Key", "expected sprint", "Story point", "statut",
                  "expected sprint Jira", "Committed (Yes/No)"]].copy()
    scope.columns = ["key", "scope_sprint", "scope_points",
                     "scope_status", "jira_sprint", "committed"]
    scope["key"] = scope["key"].astype(str).str.strip()
    scope = scope[
        scope["key"].notna() & (scope["key"] != "nan") & (scope["key"] != "")
    ].reset_index(drop=True)

    null_idx = scope[scope["scope_sprint"].isna()].index.tolist()
    if null_idx:
        try:
            _ext = pd.read_excel("data/extract_new.xlsx", sheet_name=0)
            _ext.columns = [str(c).strip() for c in _ext.columns]
            null_keys = scope.loc[null_idx, "key"].tolist()
            ext_map = (
                _ext[_ext["Key"].isin(null_keys)]
                .set_index("Key")["Expected Sprint"]
                .to_dict()
            )
            for idx in null_idx:
                k = scope.at[idx, "key"]
                ext_val = ext_map.get(k)
                jira_val = str(scope.at[idx, "jira_sprint"]).strip()
                if pd.notna(ext_val) and str(ext_val).strip() not in ("", "nan"):
                    scope.at[idx, "scope_sprint"] = ext_val
                elif jira_val not in ("0", "", "nan"):
                    scope.at[idx, "scope_sprint"] = jira_val
        except Exception:
            pass
    return scope


@st.cache_data(ttl=3600, show_spinner=False)
def load_team_availability():
    """Load team availability + sprint metadata from DB, fall back to local Excel."""
    import datetime as _dt

    try:
        eng = _engine()
        if inspect(eng).has_table("r25_team_avail") and inspect(eng).has_table("r25_sprint_meta"):
            team = pd.read_sql("SELECT squad, name, cap_prod FROM r25_team_avail", con=eng)
            meta = pd.read_sql("SELECT * FROM r25_sprint_meta WHERE sprint_name='R25'", con=eng)
            if not meta.empty:
                row = meta.iloc[0]
                sprint_info = {
                    "duration_days":  float(row["duration_days"]) if pd.notna(row["duration_days"]) else 15.0,
                    "start":          pd.Timestamp(row["sprint_start"]).date() if pd.notna(row["sprint_start"]) else None,
                    "end":            pd.Timestamp(row["sprint_end"]).date()   if pd.notna(row["sprint_end"])   else None,
                    "cap_planifiee":  float(row["cap_planifiee"])  if pd.notna(row["cap_planifiee"])  else None,
                    "velocite_reele": float(row["velocite_reele"]) if pd.notna(row["velocite_reele"]) else None,
                    "sp_vs_jh":       float(row["sp_vs_jh"])       if pd.notna(row["sp_vs_jh"])       else None,
                }
                return team, sprint_info
    except Exception:
        pass

    # ── Local file fallback ───────────────────────────────────────────────────
    raw = pd.read_excel(
        "data/Release_lifecycle_R25.xlsx",
        sheet_name="Team availibility", header=None
    )

    sprint_duration = float(raw.iloc[0, 13]) if pd.notna(raw.iloc[0, 13]) else 15.0
    cap_planifiee   = float(raw.iloc[0, 19]) if pd.notna(raw.iloc[0, 19]) else None
    velocite_reele  = float(raw.iloc[1, 19]) if pd.notna(raw.iloc[1, 19]) else None
    sp_vs_jh        = float(raw.iloc[23, 13]) if pd.notna(raw.iloc[23, 13]) else None

    try:
        start_dt = pd.to_datetime(raw.iloc[0, 16])
        end_dt   = pd.to_datetime(str(raw.iloc[1, 16]), dayfirst=True)
        if start_dt > end_dt:
            start_dt = pd.Timestamp(start_dt.year, start_dt.day, start_dt.month)
        sprint_start = start_dt.date()
        sprint_end   = end_dt.date()
    except Exception:
        sprint_start = _dt.date(2026, 3, 8)
        sprint_end   = _dt.date(2026, 3, 27)

    team = raw.iloc[1:22, [0, 1, 6, 7]].copy()
    team.columns = ["squad", "name", "contingence", "cap_prod"]
    team = team[team["name"].notna() & (team["name"].astype(str).str.strip() != "nan")].copy()
    team["name"]    = team["name"].astype(str).str.strip()
    team["squad"]   = team["squad"].astype(str).str.strip().replace({"nan": "—"})
    team["cap_prod"]= pd.to_numeric(team["cap_prod"], errors="coerce").fillna(0)
    team = team[["squad", "name", "cap_prod"]].reset_index(drop=True)

    sprint_info = {
        "duration_days":  sprint_duration,
        "start":          sprint_start,
        "end":            sprint_end,
        "cap_planifiee":  cap_planifiee,
        "velocite_reele": velocite_reele,
        "sp_vs_jh":       sp_vs_jh,
    }
    return team, sprint_info


def _norm(s: str) -> str:
    """Normalize a person name for fuzzy matching."""
    import re as _re
    s = str(s).lower()
    s = _re.sub(r"\(.*?\)", "", s)          # remove (BA), (ba), etc.
    s = _re.sub(r"[@\.,\-_]", " ", s)      # punctuation → space
    s = _re.sub(r"\s+", " ", s).strip()
    return s


def _name_score(a: str, b: str) -> float:
    """Token-overlap + sequence similarity between two person names."""
    import difflib as _dl
    na, nb = _norm(a), _norm(b)
    ta = {t for t in na.split() if len(t) > 2}
    tb = {t for t in nb.split() if len(t) > 2}
    if not ta or not tb:
        return 0.0
    tok  = len(ta & tb) / max(len(ta), len(tb))
    seq  = _dl.SequenceMatcher(None, na, nb).ratio() * 0.75
    return max(tok, seq)


def _match_names(avail_name: str, jira_names) -> tuple[str | None, float]:
    """Return (best_jira_name, score) for an availability sheet name."""
    best, best_s = None, 0.0
    for jn in jira_names:
        s = _name_score(avail_name, jn)
        if s > best_s:
            best, best_s = jn, s
    return (best if best_s >= 0.30 else None), best_s


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
    _axis = dict(gridcolor=_GRID, linecolor=DXC_BORDER,
                 zerolinecolor=DXC_BORDER, tickfont=dict(color=DXC_GREY))
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

tab_overview, tab_trends, tab_analysis, tab_sla, tab_burndown, tab_backlog, tab_team, tab_chat, tab_upload = st.tabs([
    "Overview", "Trends", "Analysis", "SLA & KPIs", "Burndown", "Backlog Burndown", "Team", "AI Assistant", "Upload",
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
    st.markdown("#### Upload Release Lifecycle File")
    st.markdown(
        "Upload the **Release_lifecycle_R25.xlsx** file to load sprint scope and team "
        "availability into the database. This enables the **Burndown** and **Team** tabs "
        "to work without a local file."
    )

    uploaded_rl = st.file_uploader(
        "Drag & drop Release_lifecycle_R25.xlsx",
        type=["xlsx", "xls"],
        key="rl_uploader",
        label_visibility="collapsed",
    )

    if uploaded_rl:
        st.info(f"**{uploaded_rl.name}** — {uploaded_rl.size / 1024:.1f} KB")
        if st.button("⚡ Load Scope & Team Availability into Database", type="primary", key="rl_load_btn"):
            with st.spinner("Parsing Release Lifecycle file…"):
                try:
                    result = load_release_lifecycle(uploaded_rl.read(), _engine())
                    st.success(
                        f"✅ Loaded **{result['scope_rows']} scope tickets** and "
                        f"**{result['team_rows']} team members** into the database."
                    )
                    load_r25_scope.clear()
                    load_team_availability.clear()
                except Exception as exc:
                    st.error(f"Failed to load Release Lifecycle file: {exc}")

    rl_loaded = _rl_table_exists(_engine())
    if rl_loaded:
        st.caption("✅ Release Lifecycle data is loaded in the database.")
    else:
        st.caption("⚠️ Release Lifecycle data not yet in database — upload the file above.")

    st.markdown("---")
    if has_data:
        st.markdown("**Database Snapshot**")
        sc1, sc2, sc3, sc4 = st.columns(4)
        sc1.metric("Total Records", f"{len(df_all):,}")
        sc2.metric("Earliest", df_all["created"].min().strftime("%Y-%m-%d") if "created" in df_all else "—")
        sc3.metric("Latest",   df_all["created"].max().strftime("%Y-%m-%d") if "created" in df_all else "—")
        sc4.metric("Projects", df_all["project"].nunique() if "project" in df_all else "—")

if not has_data:
    for t in [tab_overview, tab_trends, tab_analysis, tab_sla, tab_burndown, tab_backlog, tab_team, tab_chat]:
        with t:
            st.info("No data available. Go to the **Upload** tab to load your Extract file.")
    st.stop()

# Apply filters to a working copy
df = apply_filters(df_all, filters)

if df.empty:
    for t in [tab_overview, tab_trends, tab_analysis, tab_sla, tab_burndown, tab_backlog, tab_team, tab_chat]:
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
                      yaxis=dict(title="Issues", gridcolor=_GRID))
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
    st.markdown("#### Sprint Burndown — R25 Committed Scope")

    QUICK_START = datetime.date(2026, 3, 8)
    QUICK_END   = datetime.date(2026, 3, 27)

    # ── Load scope (cached) ────────────────────────────────────────────────────
    try:
        scope_df  = load_r25_scope()
        scope_keys = scope_df["key"].tolist()
    except Exception as e:
        st.error(f"Could not load scope file: {e}")
        st.stop()

    # ── Merge scope with live DB data ──────────────────────────────────────────
    db_cols = ["key", "summary", "issue_type", "priority", "status",
               "story_points", "is_resolved", "resolved", "closure_date",
               "qualification_date", "assignee"]
    df_db = df_all[[c for c in db_cols if c in df_all.columns]].copy()
    df_db = df_db[df_db["key"].isin(scope_keys)]

    df_merged = scope_df.merge(df_db, on="key", how="left")
    # Use DB story_points where available, fall back to scope file points
    df_merged["_points"] = pd.to_numeric(df_merged["story_points"], errors="coerce")
    df_merged["_points"] = df_merged["_points"].fillna(
        pd.to_numeric(df_merged["scope_points"], errors="coerce")
    )
    # Completion date: qualification_date first, then resolved, then closure_date
    df_merged["_resolved_at"] = pd.NaT
    for _col in ["qualification_date", "resolved", "closure_date"]:
        if _col in df_merged.columns:
            df_merged["_resolved_at"] = df_merged["_resolved_at"].fillna(df_merged[_col])

    # ── Sprint date selector ───────────────────────────────────────────────────
    if st.button("Load R25  (08 Mar → 26 Mar 2026)", key="load_r25"):
        st.session_state["burn_start"] = QUICK_START
        st.session_state["burn_end"]   = QUICK_END

    dc1, dc2 = st.columns(2)
    with dc1:
        sprint_start = st.date_input("Sprint Start Date",
                                     value=st.session_state.get("burn_start", QUICK_START),
                                     key="burn_start")
    with dc2:
        sprint_end = st.date_input("Sprint End Date",
                                   value=st.session_state.get("burn_end", QUICK_END),
                                   key="burn_end")

    if sprint_end <= sprint_start:
        st.error("End date must be after start date.")
    else:
        # ── Burndown mode ──────────────────────────────────────────────────────
        burn_mode = st.radio("Burndown metric", ["Story Points", "Ticket Count"],
                             horizontal=True, key="burn_mode")

        if burn_mode == "Story Points":
            df_merged["_weight"] = df_merged["_points"].fillna(0)
            n_unpointed = (df_merged["_weight"] == 0).sum()
            if n_unpointed > 0:
                st.caption(f"⚠️ {n_unpointed} issue(s) have no story points and contribute 0 to the burn.")
            unit = "pts"
        else:
            df_merged["_weight"] = 1.0
            unit = "tickets"

        total_work = df_merged["_weight"].sum()

        # ── Build daily remaining ──────────────────────────────────────────────
        days = pd.date_range(start=sprint_start, end=sprint_end, freq="D")
        remaining = []
        for day in days:
            day_ts = pd.Timestamp(day)
            resolved_by_day = df_merged[
                df_merged["_resolved_at"].notna() &
                (df_merged["_resolved_at"] <= day_ts + pd.Timedelta(hours=23, minutes=59))
            ]["_weight"].sum()
            remaining.append(total_work - resolved_by_day)

        burn_df = pd.DataFrame({"Date": days, "Remaining": remaining})
        n_days = len(days)
        burn_df["Ideal"] = [
            total_work * (1 - i / (n_days - 1)) for i in range(n_days)
        ] if n_days > 1 else [0]

        resolved_in_sprint = df_merged[
            df_merged["_resolved_at"].notna() &
            (df_merged["_resolved_at"] >= pd.Timestamp(sprint_start)) &
            (df_merged["_resolved_at"] <= pd.Timestamp(sprint_end) + pd.Timedelta(hours=23, minutes=59))
        ]["_weight"].sum()

        pct_done = resolved_in_sprint / total_work * 100 if total_work > 0 else 0

        # ── KPI cards ──────────────────────────────────────────────────────────
        bk1, bk2, bk3, bk4 = st.columns(4)
        with bk1: kpi_card("Sprint", "R25 Scope")
        with bk2: kpi_card("Total Work", f"{total_work:.0f} {unit}")
        with bk3: kpi_card("Completed", f"{resolved_in_sprint:.0f} {unit}",
                            color=DXC_PURPLE_LITE if pct_done >= 80 else "#E65100")
        with bk4: kpi_card("Done", f"{pct_done:.1f}%",
                            color=DXC_PURPLE_LITE if pct_done >= 80 else DXC_GREY_LIGHT)

        st.markdown("---")
        sec("Burndown — R25 Committed Scope")

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
            yaxis=dict(title=f"Remaining ({unit})", gridcolor=_GRID),
            hovermode="x unified", **CHART_THEME,
        )
        chart(fig)

        with st.expander("Daily breakdown"):
            _bdf = burn_df.copy()
            _bdf["Burned Today"] = _bdf["Remaining"].shift(1).fillna(total_work) - _bdf["Remaining"]
            _bdf["% Done"] = ((total_work - _bdf["Remaining"]) / total_work * 100).round(1)
            _bdf["Date"] = _bdf["Date"].dt.strftime("%Y-%m-%d")
            for col in ["Remaining", "Ideal", "Burned Today"]:
                _bdf[col] = _bdf[col].round(1)
            st.dataframe(_bdf[["Date", "Remaining", "Ideal", "Burned Today", "% Done"]],
                         use_container_width=True, hide_index=True)

        # ── Scope issues table ─────────────────────────────────────────────────
        st.markdown("---")
        sec(f"Committed Scope Issues ({len(df_merged)})")
        show_cols = [c for c in ["key", "summary", "issue_type", "priority",
                                  "status", "_points", "scope_sprint", "_resolved_at", "assignee"]
                     if c in df_merged.columns]
        st.dataframe(
            df_merged[show_cols]
            .rename(columns={"_points": "story_points", "scope_sprint": "sprint",
                             "_resolved_at": "resolved_at"})
            .sort_values("priority", key=lambda s: s.map(
                {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}).fillna(4)),
            use_container_width=True, hide_index=True,
        )

        # ── Out of scope R25 issues ────────────────────────────────────────────
        st.markdown("---")
        sec("R25 Issues NOT in Committed Scope")
        st.caption(
            "Issues found in Jira with an R25 sprint assignment that are **not** in the "
            "committed scope file. These are not tracked in the burndown above."
        )

        r25_in_db = df_all[
            df_all["expected_sprint"].astype(str).str.contains(r"\.25\.", na=False, regex=True) |
            df_all["expected_sprint"].astype(str).str.upper().str.contains("DATAFIX 25", na=False)
        ].copy()
        df_out_of_scope = r25_in_db[~r25_in_db["key"].isin(scope_keys)].copy()

        oos1, oos2, oos3 = st.columns(3)
        with oos1: kpi_card("Out of Scope", f"{len(df_out_of_scope)}", color="#E65100")
        with oos2:
            oos_open = int((df_out_of_scope["is_resolved"] == False).sum()) \
                if "is_resolved" in df_out_of_scope.columns else len(df_out_of_scope)
            kpi_card("Still Open", f"{oos_open}", color="#C62828")
        with oos3:
            oos_pts = pd.to_numeric(df_out_of_scope.get("story_points", pd.Series(dtype=float)),
                                    errors="coerce").sum()
            kpi_card("Untracked Points", f"{oos_pts:.0f}", color="#E65100")

        if df_out_of_scope.empty:
            st.success("All R25 Jira issues are within the committed scope.")
        else:
            oos_cols = [c for c in ["key", "summary", "issue_type", "priority",
                                     "status", "expected_sprint", "story_points", "assignee"]
                        if c in df_out_of_scope.columns]
            st.dataframe(
                df_out_of_scope[oos_cols].sort_values(
                    "priority", key=lambda s: s.map(
                        {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}).fillna(4)
                ),
                use_container_width=True, hide_index=True,
            )


# ── TAB: BACKLOG BURNDOWN ─────────────────────────────────────────────────────
with tab_backlog:
    import datetime as _dt
    import numpy as _np

    st.markdown("#### Production Incident Backlog Burndown")
    st.markdown(
        "Tracks daily resolution progress across **all production incidents**. "
        "New tickets created each day increase the remaining count; resolved tickets decrease it."
    )

    # ── Controls ───────────────────────────────────────────────────────────────
    _bc1, _bc2, _bc3 = st.columns(3)
    with _bc1:
        _bl_start = st.date_input("Track from", value=_dt.date(2026, 1, 1), key="bl_start")
    with _bc2:
        _bl_end = st.date_input("Track to", value=_dt.date(2026, 4, 30), key="bl_end")
    with _bc3:
        _bl_target = st.number_input(
            "Target open tickets", min_value=0, max_value=10000,
            value=261, step=10, key="bl_target",
        )

    if _bl_end <= _bl_start:
        st.error("End date must be after start date.")
    else:
        # ── Filter: prod incidents only ────────────────────────────────────────
        _bl_df = df_all[
            (df_all["issue_type"] == "Incident") &
            (df_all["environment_type"] == "Production")
        ].copy()

        # Closure date: use closure_date then resolved (NOT qualification_date —
        # that field reflects a workflow step, not actual ticket closure).
        _closed_statuses = {"Closed", "Cancelled"}
        _bl_df["_resolved_at"] = pd.NaT
        for _c in ["closure_date", "resolved"]:
            if _c in _bl_df.columns:
                _bl_df["_resolved_at"] = _bl_df["_resolved_at"].fillna(_bl_df[_c])

        # A ticket is closed only when its Jira status is terminal.
        # We use _resolved_at only to know WHEN it closed (for daily tracking).
        # For tickets with no closure date, fall back to created date as a proxy
        # so the daily loop can correctly attribute the closure day.
        _bl_df["_is_closed"] = _bl_df["status"].isin(_closed_statuses)

        _start_ts = pd.Timestamp(_bl_start)
        _end_ts   = pd.Timestamp(_bl_end) + pd.Timedelta(hours=23, minutes=59)
        _today_ts = pd.Timestamp(_dt.date.today())

        # ── Build daily net remaining ──────────────────────────────────────────
        _days = pd.date_range(start=_bl_start, end=_bl_end, freq="D")
        _remaining, _opened_pd, _closed_pd = [], [], []

        for _day in _days:
            _d_end = _day + pd.Timedelta(hours=23, minutes=59)
            # Open on this day = created on or before day AND not yet closed by end of day
            _open = _bl_df[
                (_bl_df["created"] <= _d_end) &
                (~_bl_df["_is_closed"] | (_bl_df["_resolved_at"] > _d_end))
            ]
            _remaining.append(len(_open))
            _opened_pd.append(int((_bl_df["created"] >= _day) & (_bl_df["created"] <= _d_end)).sum() if False else
                              len(_bl_df[(_bl_df["created"] >= _day) & (_bl_df["created"] <= _d_end)]))
            _closed_pd.append(
                len(_bl_df[_bl_df["_resolved_at"].notna() &
                           (_bl_df["_resolved_at"] >= _day) &
                           (_bl_df["_resolved_at"] <= _d_end)])
            )

        _burn_df = pd.DataFrame({
            "Date": _days, "Remaining": _remaining,
            "Opened": _opened_pd, "Closed": _closed_pd,
        })
        _actual = _burn_df[_burn_df["Date"] <= _today_ts].copy()

        # ── Trend / forecast ──────────────────────────────────────────────────
        _forecast_date, _daily_rate, _forecast_df = None, None, pd.DataFrame(columns=["Date", "Forecast"])
        if len(_actual) >= 7:
            _recent = _actual.tail(14)
            _x = _np.arange(len(_recent))
            _y = _recent["Remaining"].values.astype(float)
            _slope, _intercept = _np.polyfit(_x, _y, 1)
            _daily_rate = -_slope
            if _slope < 0:
                _days_needed = (_recent["Remaining"].iloc[-1] - _bl_target) / (-_slope)
                if _days_needed > 0:
                    _forecast_date = (_recent["Date"].iloc[-1] + pd.Timedelta(days=int(_days_needed))).date()
            _fc_days = pd.date_range(_actual["Date"].iloc[-1], _days[-1], freq="D")
            _fc_vals = [max(0, float(_actual["Remaining"].iloc[-1]) + _slope * i) for i in range(len(_fc_days))]
            _forecast_df = pd.DataFrame({"Date": _fc_days, "Forecast": _fc_vals})

        # ── KPI cards ─────────────────────────────────────────────────────────
        _current_open = int(_actual["Remaining"].iloc[-1]) if len(_actual) else 0
        _gap          = _current_open - _bl_target
        _net_progress = int(_actual["Closed"].sum() - _actual["Opened"].sum()) if len(_actual) else 0

        _bk1, _bk2, _bk3, _bk4, _bk5 = st.columns(5)
        with _bk1: kpi_card("Currently Open", f"{_current_open:,}",
                             color="#C62828" if _current_open > _bl_target else "#4CAF50")
        with _bk2: kpi_card("Target", f"{_bl_target:,} by {_bl_end.strftime('%d %b')}")
        with _bk3: kpi_card("Gap to Target", f"{_gap:+,}",
                             color="#C62828" if _gap > 0 else "#4CAF50")
        with _bk4: kpi_card("Net Resolved (period)", f"{_net_progress:+,}",
                             color="#4CAF50" if _net_progress > 0 else "#C62828")
        with _bk5:
            if _forecast_date:
                kpi_card("Projected Date", _forecast_date.strftime("%d %b %Y"),
                         color="#4CAF50" if _forecast_date <= _bl_end else "#C62828")
            elif _daily_rate is not None and _daily_rate <= 0:
                kpi_card("Projected Date", "Not improving", color="#C62828")
            else:
                kpi_card("Projected Date", "—")

        st.markdown("---")

        # ── Main burndown chart ────────────────────────────────────────────────
        sec("Daily Open Incidents — Net Remaining")

        _fig_bl = go.Figure()
        # Target line
        _fig_bl.add_trace(go.Scatter(
            x=[_days[0], _days[-1]],
            y=[_actual["Remaining"].iloc[0] if len(_actual) else _bl_target, _bl_target],
            mode="lines", name=f"Target ({_bl_target:,})",
            line=dict(color="#4CAF50", width=2, dash="dot"),
        ))
        # Trend forecast
        if len(_forecast_df) > 1:
            _fig_bl.add_trace(go.Scatter(
                x=_forecast_df["Date"], y=_forecast_df["Forecast"],
                mode="lines", name="Trend (14-day)",
                line=dict(color=DXC_GREY_LIGHT, width=2, dash="dash"),
            ))
        # Actual
        _fig_bl.add_trace(go.Scatter(
            x=_actual["Date"], y=_actual["Remaining"],
            mode="lines+markers", name="Actual Open",
            line=dict(color=DXC_PURPLE_LITE, width=3),
            marker=dict(size=4),
            fill="tozeroy", fillcolor="rgba(109,32,119,0.10)",
            hovertemplate="%{x|%d %b}<br>Open: %{y:,}<extra></extra>",
        ))
        # Today marker
        if len(_actual):
            _today_x = str(_actual["Date"].iloc[-1].date())
            _fig_bl.add_shape(type="line", x0=_today_x, x1=_today_x,
                              y0=0, y1=1, yref="paper",
                              line=dict(color=DXC_GREY, width=1, dash="dash"))
            _fig_bl.add_annotation(x=_today_x, y=1, yref="paper",
                                   text="Today", showarrow=False,
                                   font=dict(color=DXC_GREY_LIGHT, size=11),
                                   xanchor="left", yanchor="top")
        _fig_bl.update_layout(**{
            **CHART_THEME, "height": 420,
            "yaxis": dict(title="Open Incidents", gridcolor=_GRID),
            "hovermode": "x unified",
            "legend": dict(orientation="h", y=1.05, x=0),
        })
        chart(_fig_bl)

        st.markdown("---")

        # ── Daily opened vs closed ─────────────────────────────────────────────
        sec("Daily Opened vs Closed")
        _fig_oc = go.Figure()
        _fig_oc.add_trace(go.Bar(
            x=_actual["Date"], y=_actual["Opened"],
            name="Opened", marker_color="#C62828", opacity=0.85,
        ))
        _fig_oc.add_trace(go.Bar(
            x=_actual["Date"], y=-_actual["Closed"],
            name="Closed", marker_color="#4CAF50", opacity=0.85,
        ))
        _fig_oc.update_layout(**{
            **CHART_THEME, "barmode": "relative", "height": 280,
            "yaxis": dict(title="Tickets", gridcolor=_GRID),
            "hovermode": "x unified",
            "legend": dict(orientation="h", y=1.05, x=0),
        })
        chart(_fig_oc)

        st.markdown("---")

        # ── Assignee breakdown ─────────────────────────────────────────────────
        sec("By Assignee")
        _bl_open_now = _bl_df[
            (_bl_df["created"] <= _today_ts) &
            (~_bl_df["_is_closed"] | (_bl_df["_resolved_at"] > _today_ts))
        ].copy()
        _bl_closed_period = _bl_df[
            _bl_df["_resolved_at"].notna() &
            (_bl_df["_resolved_at"] >= _start_ts) &
            (_bl_df["_resolved_at"] <= _today_ts)
        ].copy()

        _col_open, _col_closed = st.columns(2)
        with _col_open:
            st.caption(f"Currently open — {len(_bl_open_now):,} incidents")
            _open_by = (_bl_open_now.groupby("assignee", dropna=True).size()
                        .reset_index(name="open").sort_values("open", ascending=False).head(15))
            _fig_op = go.Figure(go.Bar(
                x=_open_by["open"], y=_open_by["assignee"], orientation="h",
                marker_color=DXC_PURPLE_LITE,
                text=_open_by["open"], textposition="outside",
            ))
            _fig_op.update_layout(**{**CHART_THEME, "height": 440,
                                    "xaxis": dict(gridcolor=_GRID),
                                    "yaxis": dict(autorange="reversed"),
                                    "margin": dict(t=10, b=10, l=10, r=60)})
            chart(_fig_op)

        with _col_closed:
            st.caption(f"Closed in period — {len(_bl_closed_period):,} incidents")
            _closed_by = (_bl_closed_period.groupby("assignee", dropna=True).size()
                          .reset_index(name="closed").sort_values("closed", ascending=False).head(15))
            _fig_cl = go.Figure(go.Bar(
                x=_closed_by["closed"], y=_closed_by["assignee"], orientation="h",
                marker_color="#4CAF50",
                text=_closed_by["closed"], textposition="outside",
            ))
            _fig_cl.update_layout(**{**CHART_THEME, "height": 440,
                                    "xaxis": dict(gridcolor=_GRID),
                                    "yaxis": dict(autorange="reversed"),
                                    "margin": dict(t=10, b=10, l=10, r=60)})
            chart(_fig_cl)

        st.markdown("---")

        # ── Age + Priority ─────────────────────────────────────────────────────
        _col_age, _col_prio = st.columns(2)

        with _col_age:
            sec("Age of Open Tickets")
            _bl_open_now["_age_days"] = (_today_ts - _bl_open_now["created"]).dt.days
            _bins   = [0, 7, 30, 60, 90, 180, 9999]
            _lbls   = ["< 1 week", "1–4 weeks", "1–2 months", "2–3 months", "3–6 months", "> 6 months"]
            _bl_open_now["_age_bucket"] = pd.cut(_bl_open_now["_age_days"], bins=_bins, labels=_lbls, right=False)
            _age_c = _bl_open_now.groupby("_age_bucket", observed=True).size().reset_index(name="count")
            _age_colors = ["#4CAF50", DXC_PURPLE_LITE, "#E65100", "#C62828", "#7B1FA2", "#37474F"]
            _fig_age = go.Figure(go.Bar(
                x=_age_c["_age_bucket"].astype(str), y=_age_c["count"],
                marker_color=_age_colors[:len(_age_c)],
                text=_age_c["count"], textposition="outside",
            ))
            _fig_age.update_layout(**{**CHART_THEME, "height": 300,
                                     "yaxis": dict(gridcolor=_GRID)})
            chart(_fig_age)

        with _col_prio:
            sec("Open Tickets by Priority")
            _prio_c = (_bl_open_now.groupby("priority", dropna=True).size()
                       .reset_index(name="count").sort_values("count", ascending=True))
            _pcmap  = {"Critical": "#C62828", "High": "#E65100",
                       "Medium": DXC_PURPLE_LITE, "Low": DXC_GREY}
            _fig_pr = go.Figure(go.Bar(
                x=_prio_c["count"], y=_prio_c["priority"], orientation="h",
                marker_color=[_pcmap.get(p, DXC_GREY) for p in _prio_c["priority"]],
                text=_prio_c["count"], textposition="outside",
            ))
            _fig_pr.update_layout(**{**CHART_THEME, "height": 300,
                                    "xaxis": dict(gridcolor=_GRID),
                                    "margin": dict(t=10, b=10, l=10, r=60)})
            chart(_fig_pr)

        # ── Daily detail table ─────────────────────────────────────────────────
        with st.expander("Daily breakdown table"):
            _tbl_df = _actual[["Date", "Remaining", "Opened", "Closed"]].copy()
            _tbl_df["Net"] = _tbl_df["Closed"] - _tbl_df["Opened"]
            _tbl_df["Date"] = _tbl_df["Date"].dt.strftime("%Y-%m-%d")
            st.dataframe(_tbl_df.sort_values("Date", ascending=False),
                         use_container_width=True, hide_index=True)


# ── TAB: TEAM PRODUCTIVITY ────────────────────────────────────────────────────
with tab_team:
    st.markdown("#### Team Productivity — R25")

    # ── Load data (both cached) ────────────────────────────────────────────────
    try:
        avail_df, sprint_info = load_team_availability()
        scope_df_t = load_r25_scope()
        scope_keys_t = scope_df_t["key"].tolist()
    except Exception as _e:
        st.error(f"Could not load Release Lifecycle file: {_e}")
        st.stop()

    # ── Build merged scope × DB ────────────────────────────────────────────────
    _db_cols = ["key", "story_points", "resolved", "closure_date",
                "qualification_date", "assignee"]
    _df_db_t = df_all[[c for c in _db_cols if c in df_all.columns]].copy()
    _df_db_t = _df_db_t[_df_db_t["key"].isin(scope_keys_t)]
    _df_m = scope_df_t.merge(_df_db_t, on="key", how="left")

    # Effective points: DB first, scope file fallback
    _df_m["_pts"] = (
        pd.to_numeric(_df_m["story_points"], errors="coerce")
        .fillna(pd.to_numeric(_df_m["scope_points"], errors="coerce"))
        .fillna(0)
    )

    # Completion date: qualification_date → resolved → closure_date
    _df_m["_done_at"] = pd.NaT
    for _c in ["qualification_date", "resolved", "closure_date"]:
        if _c in _df_m.columns:
            _df_m["_done_at"] = _df_m["_done_at"].fillna(_df_m[_c])

    # Ticket counts as delivered only if completed WITHIN the sprint window
    _sp_start = pd.Timestamp(sprint_info["start"]) if sprint_info.get("start") else None
    _sp_end   = (pd.Timestamp(sprint_info["end"]) + pd.Timedelta(hours=23, minutes=59)) \
                if sprint_info.get("end") else None
    if _sp_start and _sp_end:
        _df_m["_delivered"] = (
            _df_m["_done_at"].notna() &
            (_df_m["_done_at"] >= _sp_start) &
            (_df_m["_done_at"] <= _sp_end)
        )
    else:
        _df_m["_delivered"] = _df_m["_done_at"].notna()

    # ── Sprint banner ──────────────────────────────────────────────────────────
    _s = sprint_info
    _sb1, _sb2, _sb3, _sb4, _sb5 = st.columns(5)
    with _sb1: kpi_card("Sprint", "R25")
    with _sb2: kpi_card("Duration", f"{int(_s['duration_days'])} days")
    with _sb3:
        kpi_card("Dates",
                 f"{_s['start'].strftime('%d %b') if _s['start'] else '—'} → "
                 f"{_s['end'].strftime('%d %b %Y') if _s['end'] else '—'}")
    with _sb4: kpi_card("Planned Capacity", f"{_s['cap_planifiee']:.0f} JH" if _s['cap_planifiee'] else "—")
    with _sb5: kpi_card("Actual Velocity", f"{_s['velocite_reele']:.0f} SP" if _s['velocite_reele'] else "—")

    st.markdown("---")

    # SP ceiling: all delivered scope tickets (includes unassigned / unmatched)
    _total_delivered_scope = float(_df_m[_df_m["_delivered"]]["_pts"].sum())

    # ── Exclusive one-to-one matching against ALL scope assignees ──────────────
    # Critical fix: match against ALL assignees in scope (delivered or not).
    # If we only match against delivered assignees, people with no delivered
    # tickets are absent from the pool → their avail name matches a wrong person.
    _all_scope_assignees = _df_m["assignee"].dropna().unique().tolist()
    _unique_avail_names  = avail_df["name"].drop_duplicates().tolist()

    _pair_scores = []
    for _jn in _all_scope_assignees:
        for _an in _unique_avail_names:
            _s = _name_score(_jn, _an)
            if _s >= 0.35:
                _pair_scores.append({"jira": _jn, "avail": _an, "score": _s})

    # Greedy exclusive: each Jira name → its single best-matching avail person
    _jira_to_avail: dict = {}
    for _p in sorted(_pair_scores, key=lambda x: -x["score"]):
        if _p["jira"] not in _jira_to_avail:
            _jira_to_avail[_p["jira"]] = _p["avail"]

    # Invert: avail person → list of their matched Jira names
    _avail_to_jiras: dict = {}
    for _jn, _an in _jira_to_avail.items():
        _avail_to_jiras.setdefault(_an, []).append(_jn)

    # Delivered SP per avail person = sum of delivered tickets by their jira names
    _delivered_tickets = _df_m[_df_m["_delivered"]].copy()
    _avail_sp_map: dict = {}
    _avail_jira_map: dict = _avail_to_jiras  # for display
    for _an, _jiras in _avail_to_jiras.items():
        _sp = float(_delivered_tickets[_delivered_tickets["assignee"].isin(_jiras)]["_pts"].sum())
        _avail_sp_map[_an] = _sp

    # ── Build raw person rows from availability sheet ──────────────────────────
    _raw_rows = []
    for _, _ar in avail_df.iterrows():
        _an = _ar["name"]
        _sp = _avail_sp_map.get(_an, 0.0)
        _jn_list = _avail_jira_map.get(_an, [])
        _raw_rows.append({
            "name":         _an,
            "squad":        _ar["squad"],
            "cap_prod":     float(_ar["cap_prod"]),
            "delivered_sp": _sp,
            "jira_name":    ", ".join(_jn_list) if _jn_list else None,
        })
    _raw = pd.DataFrame(_raw_rows)

    # ── Deduplicate: same person listed in multiple squads ─────────────────────
    # - identical cap_prod across rows → true duplicate → keep MAX (one of them)
    # - differing cap_prod → real multi-squad allocation → SUM the JH
    # - delivered_sp is always MAX (never double-count SP for the same person)
    def _dedup_cap(grp):
        vals = grp["cap_prod"].values
        return vals[0] if len(set(vals)) == 1 else float(vals.sum())

    _team_list = []
    for _name, _grp in _raw.groupby("name", sort=False):
        _cap     = _dedup_cap(_grp)
        _sp      = _grp["delivered_sp"].max()
        _primary = _grp.loc[_grp["cap_prod"].idxmax()]
        _team_list.append({
            "name":         _name,
            "squad":        _primary["squad"],
            "cap_prod":     _cap,
            "delivered_sp": _sp,
            "jira_name":    _primary["jira_name"],
        })
    _team = pd.DataFrame(_team_list)

    # ── Separate: cap_prod=0 people who nevertheless delivered ────────────────
    # These are people whose entire sprint time was officially allocated to
    # transverse/vacation (cap_prod=0), yet they have assigned scope tickets.
    _unplanned = _team[(_team["cap_prod"] == 0) & (_team["delivered_sp"] > 0)].copy()

    # Main chart: only people with cap_prod > 0
    _team_main = _team[_team["cap_prod"] > 0].copy()

    # Productivity % = delivered_sp / cap_prod × 100
    _team_main["productivity"] = (
        _team_main["delivered_sp"] / _team_main["cap_prod"] * 100
    ).round(1)

    # Tier classification
    def _tier(p):
        if p >= 100: return ("#4CAF50", "🏆 Overperformer")
        if p >= 80:  return (DXC_PURPLE_LITE, "✅ On Track")
        if p >= 50:  return ("#E65100", "⚠️ Below Target")
        return ("#C62828", "🔴 Needs Attention")

    _team_main["color"], _team_main["tier"] = zip(*_team_main["productivity"].map(_tier))

    # ── Team-level KPI cards ───────────────────────────────────────────────────
    _total_jh  = _team_main["cap_prod"].sum()
    _total_sp  = _team_main["delivered_sp"].sum()
    _team_pct  = (_total_sp / _total_jh * 100) if _total_jh > 0 else 0
    _main_with_sp = _team_main[_team_main["productivity"] > 0]
    _top = _team_main.loc[_team_main["productivity"].idxmax()] if not _team_main.empty else None
    _bot = _team_main.loc[_team_main["productivity"].idxmin()] if not _team_main.empty else None

    _k1, _k2, _k3, _k4, _k5 = st.columns(5)
    with _k1: kpi_card("Total Planned", f"{_total_jh:.1f} JH")
    with _k2: kpi_card("Total Delivered", f"{_total_sp:.0f} SP")
    with _k3: kpi_card("Team Productivity",
                        f"{_team_pct:.1f}%",
                        color=DXC_PURPLE_LITE if _team_pct >= 80 else "#E65100")
    with _k4:
        if _top is not None:
            kpi_card("Top Performer",
                     f"{_top['name'].split()[0]} ({_top['productivity']:.0f}%)",
                     color="#4CAF50")
    with _k5:
        if _bot is not None:
            kpi_card("Lowest Productivity",
                     f"{_bot['name'].split()[0]} ({_bot['productivity']:.0f}%)",
                     color="#C62828")

    # ── SP reconciliation note (helps verify vs burndown tab) ─────────────────
    _unplanned_sp   = float(_unplanned["delivered_sp"].sum()) if not _unplanned.empty else 0.0
    _unmatched_sp   = _total_delivered_scope - _total_sp - _unplanned_sp
    st.caption(
        f"SP breakdown — Scope delivered: **{_total_delivered_scope:.0f} pts** total  |  "
        f"Credited to team: **{_total_sp:.0f} pts**  |  "
        f"Unplanned (0-cap): **{_unplanned_sp:.0f} pts**  |  "
        f"Unmatched/unassigned: **{_unmatched_sp:.0f} pts** "
        f"*(Credited + Unplanned + Unmatched = {_total_sp + _unplanned_sp + _unmatched_sp:.0f} pts)*"
    )

    st.markdown("---")

    # ── Bullet Chart: Individual Productivity ─────────────────────────────────
    sec("Individual Productivity — Planned JH vs Delivered SP")

    _sorted = _team_main.sort_values("productivity", ascending=True).copy()
    _labels = [
        f"  {row['delivered_sp']:.0f} SP / {row['cap_prod']:.0f} JH = {row['productivity']:.0f}%"
        for _, row in _sorted.iterrows()
    ]

    _fig = go.Figure()
    # Background bars = planned cap_prod JH (wide, grey)
    _fig.add_trace(go.Bar(
        x=_sorted["cap_prod"],
        y=_sorted["name"],
        orientation="h",
        marker=dict(color="rgba(109,114,120,0.22)", line=dict(width=0)),
        name="Planned (JH)",
        width=0.75,
        hovertemplate="%{y}<br>Planned: %{x:.1f} JH<extra></extra>",
    ))
    # Foreground bars = delivered SP (narrower, colored by tier)
    _fig.add_trace(go.Bar(
        x=_sorted["delivered_sp"],
        y=_sorted["name"],
        orientation="h",
        marker=dict(color=_sorted["color"].tolist(), line=dict(width=0)),
        name="Delivered (SP)",
        width=0.38,
        text=_labels,
        textposition="outside",
        textfont=dict(size=11, color=DXC_TEXT),
        hovertemplate="%{y}<br>Delivered: %{x:.1f} SP<extra></extra>",
    ))
    _fig.update_layout(**{
        **CHART_THEME,
        "barmode": "overlay",
        "height": max(380, len(_sorted) * 42),
        "xaxis": dict(title="JH / Story Points", gridcolor=_GRID),
        "yaxis": dict(tickfont=dict(size=12)),
        "legend": dict(orientation="h", y=1.04, x=0),
        "margin": dict(t=10, b=10, l=10, r=220),
    })
    chart(_fig)

    st.markdown("---")

    # ── Two-column: squad breakdown + tier distribution ───────────────────────
    _col_a, _col_b = st.columns(2)

    with _col_a:
        sec("By Squad")
        _squad_g = (
            _team_main.groupby("squad", sort=False)
            .agg(cap_prod=("cap_prod", "sum"), delivered_sp=("delivered_sp", "sum"))
            .reset_index()
        )
        _squad_g["productivity"] = (
            _squad_g["delivered_sp"] / _squad_g["cap_prod"] * 100
        ).round(1)
        _squad_g = _squad_g[_squad_g["cap_prod"] > 0].sort_values("productivity", ascending=True)

        _sf = go.Figure()
        _sf.add_trace(go.Bar(
            x=_squad_g["cap_prod"], y=_squad_g["squad"],
            orientation="h", name="Planned JH",
            marker_color="rgba(109,114,120,0.3)", width=0.7,
        ))
        _sf.add_trace(go.Bar(
            x=_squad_g["delivered_sp"], y=_squad_g["squad"],
            orientation="h", name="Delivered SP",
            marker_color=DXC_PURPLE_LITE, width=0.35,
            text=[f"{p:.0f}%" for p in _squad_g["productivity"]],
            textposition="outside",
        ))
        _sf.update_layout(**{**CHART_THEME, "barmode": "overlay", "height": 320,
                             "xaxis": dict(gridcolor=_GRID)})
        chart(_sf)

    with _col_b:
        sec("Productivity Tier Distribution")
        _tiers = _team_main.groupby("tier").size().reset_index(name="count")
        _tier_order  = ["🏆 Overperformer", "✅ On Track", "⚠️ Below Target", "🔴 Needs Attention"]
        _tier_colors = ["#4CAF50", DXC_PURPLE_LITE, "#E65100", "#C62828"]
        _tiers["tier"] = pd.Categorical(_tiers["tier"], categories=_tier_order, ordered=True)
        _tiers = _tiers.sort_values("tier")
        _df_pie = go.Figure(go.Pie(
            labels=_tiers["tier"], values=_tiers["count"],
            hole=0.55,
            marker=dict(colors=_tier_colors[:len(_tiers)]),
            textinfo="label+percent", textfont=dict(size=12),
        ))
        _df_pie.update_layout(**{
            **CHART_THEME, "height": 320, "showlegend": False,
            "annotations": [dict(
                text=f"{_team_pct:.0f}%<br><span style='font-size:10px'>team</span>",
                font=dict(size=18, color=DXC_TEXT), showarrow=False,
            )],
        })
        chart(_df_pie)

    st.markdown("---")

    # ── Unplanned Delivery section ─────────────────────────────────────────────
    # People with cap_prod=0 (fully on transverse/vacation) who still delivered scope tickets.
    if not _unplanned.empty:
        sec("Unplanned Delivery — cap_prod = 0 but tickets completed")
        st.caption(
            "These team members had zero planned capacity (fully allocated to "
            "transverse tasks or vacation), yet completed scope tickets during the sprint. "
            "Their output is not counted in team productivity % to avoid distorting the metric."
        )
        _up_tbl = _unplanned[["name", "squad", "delivered_sp"]].copy()
        _up_tbl.columns = ["Name", "Squad", "Delivered (SP)"]
        st.dataframe(_up_tbl.sort_values("Delivered (SP)", ascending=False),
                     use_container_width=True, hide_index=True)
        st.markdown("---")

    # ── Detailed table ────────────────────────────────────────────────────────
    sec("Full Team Breakdown")
    _tbl = _team_main[["name", "squad", "cap_prod", "delivered_sp", "productivity", "tier"]].copy()
    _tbl.columns = ["Name", "Squad", "Planned (JH)", "Delivered (SP)", "Productivity %", "Tier"]
    _tbl = _tbl.sort_values("Productivity %", ascending=False)
    st.dataframe(
        _tbl.style.background_gradient(
            subset=["Productivity %"], cmap="RdYlGn", vmin=0, vmax=100
        ),
        use_container_width=True, hide_index=True,
    )

    # ── Unmatched warning ─────────────────────────────────────────────────────
    _unmatched = _team_main[_team_main["jira_name"].isna()]
    if not _unmatched.empty:
        with st.expander(f"⚠️ {len(_unmatched)} person(s) not matched to any Jira assignee"):
            st.caption(
                "These people have cap_prod > 0 but no scope ticket was found under their name. "
                "Their JH counts toward planned total; delivered SP = 0."
            )
            st.dataframe(_unmatched[["name", "squad", "cap_prod"]], hide_index=True)


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
