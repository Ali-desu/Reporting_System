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

from etl import (clean_data, upsert, initial_load, build_engine, get_engine,
                 load_release_lifecycle, materialise_r25_burndown, materialise_backlog_burndown,
                 fetch_jira_issues, materialise_r25_team_commitment, append_r25_full_burndown)
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
def load_r25_assignee_squad() -> pd.DataFrame:
    """Load the authoritative assignee→squad mapping from r25_assignee_squad table."""
    try:
        eng = _engine()
        if inspect(eng).has_table("r25_assignee_squad"):
            return pd.read_sql("SELECT assignee_name, squad FROM r25_assignee_squad", con=eng)
    except Exception:
        pass
    return pd.DataFrame(columns=["assignee_name", "squad"])


@st.cache_data(ttl=3600, show_spinner=False)
def load_team_availability():
    """Load team availability + sprint metadata from DB, fall back to local Excel."""
    import datetime as _dt

    try:
        eng = _engine()
        if inspect(eng).has_table("r25_team_avail") and inspect(eng).has_table("r25_sprint_meta"):
            team = pd.read_sql("SELECT squad, name, cap_prod, transverse FROM r25_team_avail", con=eng)
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
        sprint_end   = _dt.date(2026, 4, 4)

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
    # Email: keep only the part before @, strip domain
    if "@" in s:
        s = s.split("@")[0]
    s = _re.sub(r"\(.*?\)", "", s)        # remove (BA), (SAAS_FR), etc.
    s = _re.sub(r"[,\.\-_@]", " ", s)    # punctuation → space
    s = _re.sub(r"\s+", " ", s).strip()
    # Sort tokens so "GHAOUTI SOUFIANE" == "Soufiane Ghaouti"
    tokens = sorted(t for t in s.split() if len(t) > 1)
    return " ".join(tokens)


def _name_score(a: str, b: str) -> float:
    """Per-token matching: for each token in the shorter name, find its best
    matching token in the longer name. Exact token hits score 1.0;
    near-identical tokens (hamyouni/hamyoumi) score 0.8 if similarity >= 0.85.
    Common first-name collisions (Mohammed/Mohamed) are not enough alone."""
    import difflib as _dl
    na, nb = _norm(a), _norm(b)
    ta = list(set(na.split()))
    tb = list(set(nb.split()))
    if not ta or not tb:
        return 0.0
    shorter, longer = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    matched = 0.0
    for t in shorter:
        if t in set(longer):
            matched += 1.0
        else:
            best = max(_dl.SequenceMatcher(None, t, u).ratio() for u in longer)
            if best >= 0.85:
                matched += 0.8   # partial credit for near-identical spelling
    return matched / len(shorter)


def _match_names(avail_name: str, jira_names) -> tuple[str | None, float]:
    """Return (best_jira_name, score) for an availability sheet name."""
    best, best_s = None, 0.0
    for jn in jira_names:
        s = _name_score(avail_name, jn)
        if s > best_s:
            best, best_s = jn, s
    return (best if best_s >= 0.65 else None), best_s


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


_chart_counter = [0]

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


def apply_filters(df: pd.DataFrame, f: dict) -> pd.DataFrame:
    if "created" in df.columns and f.get("date_range") and len(f["date_range"]) == 2:
        s, e = f["date_range"]
        df = df[df["created"].between(pd.Timestamp(s), pd.Timestamp(e))]
    for col, key in [("organizations", "orgs"), ("issue_type", "types"),
                     ("environment_type", "envs"), ("priority", "priorities"),
                     ("project", "projects")]:
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

        def _checkbox_group(label, options, prefix):
            """Render a 'Select all' toggle + individual checkboxes. Returns selected list."""
            st.markdown(f'<p class="sidebar-section">{label}</p>', unsafe_allow_html=True)
            _all_key = f"{prefix}_all"
            _select_all = st.checkbox("Select all", value=True, key=_all_key)
            selected = []
            for opt in options:
                _checked = st.checkbox(str(opt), value=_select_all,
                                       key=f"{prefix}_{opt}",
                                       disabled=_select_all)
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
    # ── Jira Sync ──────────────────────────────────────────────────────────────
    st.markdown("#### Sync from Jira")
    st.markdown(
        "Pull all **IRPAUTO** issues directly from Jira — no Excel export needed. "
        "Credentials are read from your `.env` file."
    )

    _jira_url   = os.getenv("JIRA_URL",   "https://dxc-insurance-delivery.atlassian.net")
    _jira_email = os.getenv("JIRA_EMAIL", "")
    _jira_token = os.getenv("JIRA_API_TOKEN", "")

    _jc1, _jc2, _jc3 = st.columns([2, 1, 1])
    with _jc1:
        _jira_mode = st.radio(
            "Sync mode",
            ["Incremental (updated since date below)", "Replace all (full reload)"],
            horizontal=False, label_visibility="collapsed",
        )
    with _jc2:
        _jira_project = st.text_input("Project key", value="IRPAUTO")
    with _jc3:
        import datetime as _dt_ui
        _since_date = st.date_input(
            "Updated since",
            value=_dt_ui.date.today() - _dt_ui.timedelta(days=30),
            help="Only used in Incremental mode",
        )

    if not _jira_token:
        st.warning("Set `JIRA_API_TOKEN` and `JIRA_EMAIL` in your `.env` file to enable Jira sync.")
    else:
        _is_full = "Replace" in _jira_mode
        st.caption(
            f"⚠️ Full reload will fetch all ~55 000 issues (~10 min)." if _is_full else
            f"Incremental sync: issues updated on or after **{_since_date}**."
        )
        if st.button("⚡ Sync from Jira", type="primary", key="jira_sync_btn"):
            _mode_str    = "replace" if _is_full else "upsert"
            _since_str   = None if _is_full else str(_since_date)
            _progress_bar = st.progress(0, text="Connecting to Jira…")

            def _update_progress(done, total):
                pct = min(done / max(total, 1), 1.0)
                _progress_bar.progress(pct, text=f"Fetched {done:,} / {total:,} issues…")

            try:
                _result = fetch_jira_issues(
                    engine=_engine(),
                    jira_url=_jira_url,
                    email=_jira_email,
                    api_token=_jira_token,
                    project=_jira_project,
                    mode=_mode_str,
                    updated_since=_since_str,
                    progress_cb=_update_progress,
                )
                _progress_bar.progress(1.0, text="Done!")
                st.success(
                    f"✅ Jira sync complete — **{_result['fetched']:,} issues** fetched, "
                    f"**{_result['loaded']:,} records** written to database."
                )
                load_data.clear()
                st.rerun()
            except Exception as _ex:
                _progress_bar.empty()
                st.error(f"Jira sync failed: {_ex}")

    st.markdown("---")
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

            _upload_ok = False
            with st.spinner("Writing to database…"):
                try:
                    eng = _engine()
                    if mode.startswith("Replace") or not _table_exists(eng):
                        n = initial_load(cleaned, eng)
                    else:
                        n = upsert(cleaned, eng)
                    st.success(f"✅ {n:,} records loaded successfully!")
                    load_data.clear()
                    _upload_ok = True
                except Exception as exc:
                    st.error(f"Database error: {exc}")
            if _upload_ok:
                st.rerun()

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
                    load_r25_assignee_squad.clear()
                    load_team_availability.clear()
                except Exception as exc:
                    st.error(f"Failed to load Release Lifecycle file: {exc}")

    rl_loaded = _rl_table_exists(_engine())
    if rl_loaded:
        st.caption("✅ Release Lifecycle data is loaded in the database.")
    else:
        st.caption("⚠️ Release Lifecycle data not yet in database — upload the file above.")

    st.markdown("---")
    st.markdown("#### Refresh Power BI Burndown Tables")
    st.markdown(
        "Pre-compute the burndown series into the database so Power BI can read them directly. "
        "Run this after every Extract upload or when sprint data changes."
    )

    _rb1, _rb2 = st.columns(2)
    with _rb1:
        st.caption("**r25_burndown** — daily remaining SP for the R25 committed scope")
        if st.button("Refresh R25 Sprint Burndown", key="refresh_r25_bd"):
            try:
                with st.spinner("Computing R25 burndown…"):
                    _n = materialise_r25_burndown(_engine())
                st.success(f"✅ r25_burndown refreshed — {_n} daily rows written.")
            except Exception as _e:
                st.error(f"Error: {_e}")

    with _rb2:
        st.caption("**backlog_burndown** — daily open prod incident count (target = 261)")
        if st.button("Refresh Backlog Burndown", key="refresh_bl_bd"):
            try:
                with st.spinner("Computing backlog burndown…"):
                    _n = materialise_backlog_burndown(_engine())
                st.success(f"✅ backlog_burndown refreshed — {_n} daily rows written.")
            except Exception as _e:
                st.error(f"Error: {_e}")

    st.markdown("---")
    if has_data:
        st.markdown("**Database Snapshot**")
        sc1, sc2, sc3, sc4 = st.columns(4)
        sc1.metric("Total Records", f"{len(df_all):,}")
        sc2.metric("Earliest", df_all["created"].min().strftime("%Y-%m-%d") if "created" in df_all else "—")
        sc3.metric("Latest",   df_all["created"].max().strftime("%Y-%m-%d") if "created" in df_all else "—")
        sc4.metric("Projects", df_all["project"].nunique() if "project" in df_all else "—")

        st.markdown("---")
        st.markdown("#### Fetched Data — Issues Table")
        st.caption("All records from the database, sorted from earliest to most recent.")

        _disp_cols = [c for c in [
            "key", "summary", "issue_type", "assignee", "reporter", "priority",
            "status", "created", "resolved", "closure_date", "qualification_date",
            "story_points", "component", "environment_type", "product_line",
            "expected_sprint", "project",
        ] if c in df_all.columns]

        _db_view = df_all[_disp_cols].copy()
        if "created" in _db_view.columns:
            _db_view = _db_view.sort_values("created", ascending=True)
        for _dc in ["created", "resolved", "closure_date", "qualification_date"]:
            if _dc in _db_view.columns:
                _db_view[_dc] = pd.to_datetime(_db_view[_dc], errors="coerce").dt.strftime("%Y-%m-%d")

        _db_page_size = 50
        _db_total     = len(_db_view)
        _db_total_pages = max(1, -(-_db_total // _db_page_size))

        _db_col1, _db_col2 = st.columns([1, 3])
        with _db_col1:
            _db_page = st.number_input(
                f"Page (1 – {_db_total_pages:,})",
                min_value=1, max_value=_db_total_pages, value=1,
                step=1, key="db_data_page",
            )
        _db_start = (_db_page - 1) * _db_page_size
        st.dataframe(
            _db_view.iloc[_db_start: _db_start + _db_page_size],
            use_container_width=True, hide_index=True,
        )
        st.caption(
            f"Showing {_db_start + 1:,}–{min(_db_start + _db_page_size, _db_total):,} "
            f"of {_db_total:,} records"
        )

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
    QUICK_END   = datetime.date(2026, 4, 4)

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
    # Earliest date among qualification_date, resolved, closure_date
    # (computed here as raw; sprint filtering applied below after dates are known)
    _date_cols = [c for c in ["qualification_date", "resolved", "closure_date"] if c in df_merged.columns]
    df_merged["_resolved_at_raw"] = pd.concat(
        [pd.to_datetime(df_merged[c], errors="coerce") for c in _date_cols], axis=1
    ).min(axis=1)

    # ── Sprint date selector ───────────────────────────────────────────────────
    if st.button("Load R25  (08 Mar → 04 Apr 2026)", key="load_r25"):
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

    # A ticket counts in the burndown only if:
    #   1. status ∈ DELIVERED_STATUSES
    #   2. earliest date falls within [sprint_start, sprint_end]
    # Tickets delivered outside the sprint window are excluded entirely.
    _DELIVERED_STATUSES_BD = {
        "closed", "qualification test", "ready for staging",
        "ready for exceptions", "ready for qa", "ready for sprint",
        "cancelled", "canceled", "on hold", "plan investigation", "work approved",
        "ready for acceptance", "waiting for customer",
    }
    _sp_start_ts = pd.Timestamp(sprint_start)
    _sp_end_ts   = pd.Timestamp(sprint_end) + pd.Timedelta(hours=23, minutes=59)
    _is_done = df_merged["status"].str.lower().str.strip().isin(_DELIVERED_STATUSES_BD) \
               if "status" in df_merged.columns \
               else pd.Series(False, index=df_merged.index)
    # Per date column: keep only if within sprint
    for _dc in _date_cols:
        _ts = pd.to_datetime(df_merged[_dc], errors="coerce")
        df_merged[_dc + "_ts"] = _ts
        df_merged[_dc + "_in"] = _ts.where(_ts.notna() & (_ts >= _sp_start_ts) & (_ts <= _sp_end_ts))

    # Earliest date within sprint
    df_merged["_resolved_at"] = pd.concat(
        [df_merged[_dc + "_in"] for _dc in _date_cols], axis=1
    ).min(axis=1)

    # Earliest raw date (any) — for exclusion classification
    df_merged["_any_date"] = pd.concat(
        [df_merged[_dc + "_ts"] for _dc in _date_cols], axis=1
    ).min(axis=1)

    # Final gate: delivered status AND date within sprint
    df_merged["_resolved_at"] = df_merged["_resolved_at"].where(_is_done, pd.NaT)

    # NO_DATE tickets: delivered status but all dates are null → place at last day of sprint
    _no_date_mask = _is_done & df_merged["_resolved_at"].isna() & df_merged["_any_date"].isna()
    df_merged.loc[_no_date_mask, "_resolved_at"] = _sp_end_ts

    # Excluded tickets: delivered status but date exists and is outside sprint (DATE_OUTSIDE_SPRINT only)
    _bd_excluded = df_merged[_is_done & df_merged["_resolved_at"].isna()].copy()
    _bd_excluded["exclusion_reason"] = "DATE_OUTSIDE_SPRINT"

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

        # Count all delivered tickets (status-based) — no date filter needed
        # since delivery is determined by status, not by when the date falls
        resolved_in_sprint = df_merged[df_merged["_resolved_at"].notna()]["_weight"].sum()

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

        # ── Solved tickets table — all delivered tickets (status-based) ──────────
        st.markdown("---")
        _solved = df_merged[df_merged["_resolved_at"].notna()].copy()
        _solved = _solved.sort_values("_resolved_at")

        sec(f"Solved Tickets ({len(_solved)} / {len(df_merged)})")
        if _solved.empty:
            st.info("No tickets marked as solved within the sprint window.")
        else:
            _sol_cols = [c for c in ["key", "summary", "assignee", "status",
                                     "_points", "_resolved_at", "qualification_date",
                                     "resolved", "closure_date"]
                         if c in _solved.columns]
            _sol_display = _solved[_sol_cols].rename(columns={
                "_points": "story_points",
                "_resolved_at": "completed_at",
            })
            for _dc in ["completed_at", "qualification_date", "resolved", "closure_date"]:
                if _dc in _sol_display.columns:
                    _sol_display[_dc] = pd.to_datetime(
                        _sol_display[_dc], errors="coerce"
                    ).dt.strftime("%Y-%m-%d")

            # Pagination
            _sol_page_size = 15
            _sol_total_pages = max(1, -(-len(_sol_display) // _sol_page_size))
            _sol_page = st.number_input(
                f"Page (1 – {_sol_total_pages})",
                min_value=1, max_value=_sol_total_pages, value=1,
                step=1, key="sol_page",
            )
            _sol_start = (_sol_page - 1) * _sol_page_size
            st.dataframe(
                _sol_display.iloc[_sol_start: _sol_start + _sol_page_size],
                use_container_width=True, hide_index=True,
            )
            st.caption(f"Showing {min(_sol_start + 1, len(_sol_display))}–"
                       f"{min(_sol_start + _sol_page_size, len(_sol_display))} "
                       f"of {len(_sol_display)} solved tickets")

        # ── Excluded tickets warning ───────────────────────────────────────────
        if not _bd_excluded.empty:
            st.markdown("---")
            with st.expander(
                f"⚠️ {len(_bd_excluded)} delivered ticket(s) excluded from burndown "
                f"— all dates fall outside the sprint window",
                expanded=True,
            ):
                st.caption(
                    "These tickets have a delivered status but all their dates (qualification, "
                    "resolved, closure) fall outside the sprint window — they cannot be placed "
                    "on the burndown curve. Tickets with no date at all are counted on the last day. "
                    "Please update dates in Jira and re-sync."
                )
                _excl_show = _bd_excluded[[
                    c for c in ["key", "summary", "assignee", "status",
                                "qualification_date", "resolved", "closure_date",
                                "exclusion_reason"]
                    if c in _bd_excluded.columns
                ]].copy()
                for _dc in ["qualification_date", "resolved", "closure_date"]:
                    if _dc in _excl_show.columns:
                        _excl_show[_dc] = pd.to_datetime(_excl_show[_dc], errors="coerce").dt.strftime("%Y-%m-%d")
                st.dataframe(_excl_show, use_container_width=True, hide_index=True)

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

        # ── ALL TICKETS BURNDOWN ───────────────────────────────────────────────
        st.markdown("---")
        sec("Burndown — All Tickets Resolved During Sprint")
        st.caption(
            "Shows every Jira ticket with a delivered status whose **earliest date within "
            "the sprint** (qualification → resolved → closure) falls inside the sprint window. "
            "Not limited to committed scope."
        )

        if sprint_start and sprint_end:
            _DELIVERED_ALL = {
                "closed", "qualification test", "ready for staging",
                "ready for exceptions", "ready for qa", "ready for sprint",
                "cancelled", "canceled", "on hold", "plan investigation", "work approved",
                "ready for acceptance", "waiting for customer",
            }
            _all_db_cols = ["key", "summary", "issue_type", "priority", "status",
                            "story_points", "assignee", "qualification_date",
                            "resolved", "closure_date"]

            # ── Build pool: committed scope UNION team tickets resolved during sprint ──
            # Start with all DB tickets filtered by sidebar (project etc.)
            _all_df = df[[c for c in _all_db_cols if c in df.columns]].copy()

            # Filter to team members only
            _avail_df_bd, _ = load_team_availability()
            _avail_names_bd = _avail_df_bd["name"].drop_duplicates().tolist()
            _all_assignees  = _all_df["assignee"].dropna().unique().tolist()
            _team_jira_names = set()
            for _jn in _all_assignees:
                for _an in _avail_names_bd:
                    if _name_score(_jn, _an) >= 0.65:
                        _team_jira_names.add(_jn)
                        break
            # Team tickets (resolved by team members during sprint)
            _team_df = _all_df[_all_df["assignee"].isin(_team_jira_names)].copy()

            # Committed scope tickets (the 42) — include even if assignee not matched
            _scope_db_cols = ["key", "summary", "issue_type", "priority", "status",
                              "story_points", "assignee", "qualification_date",
                              "resolved", "closure_date"]
            _scope_from_db = df_all[df_all["key"].isin(scope_keys)][
                [c for c in _scope_db_cols if c in df_all.columns]
            ].copy()

            # Union: committed scope + team tickets (deduplicate by key)
            _combined = pd.concat([_scope_from_db, _team_df], ignore_index=True) \
                          .drop_duplicates(subset="key", keep="first")

            # Fall back to scope file points for committed tickets missing Jira points
            _combined = _combined.merge(scope_df[["key", "scope_points"]], on="key", how="left")
            _combined["story_points"] = pd.to_numeric(_combined["story_points"], errors="coerce") \
                .fillna(pd.to_numeric(_combined.get("scope_points", pd.Series(dtype=float)), errors="coerce"))

            # In-scope flag
            _combined["in_scope"] = _combined["key"].isin(scope_keys)

            _all_sp_s = pd.Timestamp(sprint_start)
            _all_sp_e = pd.Timestamp(sprint_end) + pd.Timedelta(hours=23, minutes=59)

            # Per date column: keep only if within sprint window
            _all_date_cols = [c for c in ["qualification_date", "resolved", "closure_date"]
                              if c in _combined.columns]
            for _adc in _all_date_cols:
                _ts = pd.to_datetime(_combined[_adc], errors="coerce")
                _combined[_adc + "_in"] = _ts.where(
                    _ts.notna() & (_ts >= _all_sp_s) & (_ts <= _all_sp_e)
                )

            # Earliest date within sprint (Option A)
            _combined["_resolved_at"] = pd.concat(
                [_combined[_adc + "_in"] for _adc in _all_date_cols], axis=1
            ).min(axis=1)

            # Status gate
            _combined_is_done = _combined["status"].str.lower().str.strip().isin(_DELIVERED_ALL) \
                                if "status" in _combined.columns \
                                else pd.Series(False, index=_combined.index)
            _combined["_resolved_at"] = _combined["_resolved_at"].where(_combined_is_done, pd.NaT)

            # NO_DATE: delivered but all dates null → place at last day of sprint
            _combined["_any_date_ft"] = pd.concat(
                [pd.to_datetime(_combined[_adc], errors="coerce") for _adc in _all_date_cols], axis=1
            ).min(axis=1)
            _no_date_ft = _combined_is_done & _combined["_resolved_at"].isna() & _combined["_any_date_ft"].isna()
            _combined.loc[_no_date_ft, "_resolved_at"] = _all_sp_e

            # Weight
            _combined["_weight"] = pd.to_numeric(_combined["story_points"], errors="coerce").fillna(0) \
                                   if burn_mode == "Story Points" else 1.0

            # Total pool = all tickets in combined (committed scope always in, out-of-scope only if resolved)
            _scope_pool_all  = _combined[_combined["in_scope"]].copy()
            _extra_resolved  = _combined[~_combined["in_scope"] & _combined["_resolved_at"].notna()].copy()
            _full_pool       = pd.concat([_scope_pool_all, _extra_resolved], ignore_index=True)

            _all_total = _full_pool["_weight"].sum()
            _all_resolved_n = _full_pool["_resolved_at"].notna().sum()

            # Daily remaining
            _all_days = pd.date_range(start=sprint_start, end=sprint_end, freq="D")
            _all_remaining = []
            for _aday in _all_days:
                _aday_end = pd.Timestamp(_aday) + pd.Timedelta(hours=23, minutes=59)
                _done_by = _full_pool[_full_pool["_resolved_at"].notna() &
                                      (_full_pool["_resolved_at"] <= _aday_end)]["_weight"].sum()
                _all_remaining.append(_all_total - _done_by)

            _all_burn_df = pd.DataFrame({"Date": _all_days, "Remaining": _all_remaining})
            _all_n = len(_all_days)
            _all_burn_df["Ideal"] = [
                _all_total * (1 - i / (_all_n - 1)) for i in range(_all_n)
            ] if _all_n > 1 else [0]

            # KPIs
            _all_pct = _all_resolved_n / len(_full_pool) * 100 if len(_full_pool) > 0 else 0
            _ak1, _ak2, _ak3, _ak4 = st.columns(4)
            with _ak1: kpi_card("Total Pool", f"{len(_full_pool)} tickets")
            with _ak2: kpi_card("Committed Scope", f"{len(_scope_pool_all)} tickets")
            with _ak3: kpi_card("Extra (out of scope)", f"{len(_extra_resolved)} tickets")
            with _ak4: kpi_card("Resolved", f"{_all_resolved_n} ({_all_pct:.0f}%)",
                                color=DXC_PURPLE_LITE if _all_pct >= 80 else "#E65100")

            # Chart
            _all_fig = go.Figure()
            _all_fig.add_trace(go.Scatter(
                x=_all_burn_df["Date"], y=_all_burn_df["Ideal"],
                mode="lines", name="Ideal",
                line=dict(color=DXC_GREY, width=2, dash="dash"),
            ))
            _all_fig.add_trace(go.Scatter(
                x=_all_burn_df["Date"], y=_all_burn_df["Remaining"],
                mode="lines+markers+text", name="Actual Remaining",
                line=dict(color=DXC_PURPLE_LITE, width=3),
                marker=dict(size=6),
                fill="tozeroy", fillcolor="rgba(109,32,119,0.12)",
                text=[f"{v:.1f}" for v in _all_burn_df["Remaining"]],
                textposition="top center",
                textfont=dict(color=DXC_PURPLE_LITE, size=11),
            ))
            _all_fig.update_layout(
                yaxis=dict(title=f"Remaining ({unit})", gridcolor=_GRID),
                hovermode="x unified", **CHART_THEME,
            )
            chart(_all_fig)

            # ── Save to DB ────────────────────────────────────────────────────
            st.markdown("---")
            if st.button("Save Sprint Burndowns to DB (Committed + Full Team)", key="save_full_burn"):
                with st.spinner("Saving…"):
                    # Step 1: Committed burndown — drops & recreates r25_burndown + r25_sprint_tickets
                    materialise_r25_burndown(_engine())

                    # Step 2: Build Full Team burndown rows
                    _sp_total_ft  = pd.to_numeric(_full_pool["story_points"], errors="coerce").fillna(0).sum()
                    _tkt_total_ft = len(_full_pool)
                    _ft_rows = []
                    for _i, _aday in enumerate(_all_days):
                        _aday_end = pd.Timestamp(_aday) + pd.Timedelta(hours=23, minutes=59)
                        _res_sp  = pd.to_numeric(
                            _full_pool[_full_pool["_resolved_at"].notna() &
                                       (_full_pool["_resolved_at"] <= _aday_end)]["story_points"],
                            errors="coerce").fillna(0).sum()
                        _res_tkt = int(_full_pool[_full_pool["_resolved_at"].notna() &
                                                   (_full_pool["_resolved_at"] <= _aday_end)].shape[0])
                        _ideal_sp  = _sp_total_ft  * (1 - _i / (_all_n - 1)) if _all_n > 1 else 0
                        _ideal_tkt = _tkt_total_ft * (1 - _i / (_all_n - 1)) if _all_n > 1 else 0
                        _ft_rows.append({
                            "date":               _aday.date(),
                            "scope_type":         "Full Team",
                            "total_pts":          round(_sp_total_ft, 2),
                            "resolved_pts":       round(float(_res_sp), 2),
                            "remaining_pts":      round(float(_sp_total_ft - _res_sp), 2),
                            "ideal_pts":          round(_ideal_sp, 4),
                            "pct_complete":       round(_res_sp / _sp_total_ft * 100, 2) if _sp_total_ft else 0,
                            "total_tickets":      _tkt_total_ft,
                            "resolved_tickets":   _res_tkt,
                            "remaining_tickets":  _tkt_total_ft - _res_tkt,
                            "ideal_tickets":      round(_ideal_tkt, 4),
                            "pct_complete_tickets": round(_res_tkt / _tkt_total_ft * 100, 2) if _tkt_total_ft else 0,
                        })
                    _ft_burn_df = pd.DataFrame(_ft_rows)

                    # Step 3: Build unified ticket table
                    _DELIVERED_SET_SAVE = {
                        "closed", "qualification test", "ready for staging",
                        "ready for exceptions", "ready for qa", "ready for sprint",
                        "cancelled", "canceled", "on hold", "plan investigation", "work approved",
                        "ready for acceptance", "waiting for customer",
                    }
                    _tkt_out_cols = [c for c in ["key", "summary", "assignee", "status",
                                                  "story_points", "in_scope", "_resolved_at",
                                                  "qualification_date", "resolved", "closure_date"]
                                     if c in _full_pool.columns]
                    _save_tkt_df = _full_pool[_tkt_out_cols].rename(
                        columns={"_resolved_at": "completed_at"}
                    ).copy()
                    _save_tkt_df["is_delivered"] = _save_tkt_df["status"].str.lower().str.strip() \
                                                     .isin(_DELIVERED_SET_SAVE).astype(int)
                    _save_tkt_df["in_scope"]     = _save_tkt_df["in_scope"].astype(int)
                    for _dc in ["completed_at", "qualification_date", "resolved", "closure_date"]:
                        if _dc in _save_tkt_df.columns:
                            _save_tkt_df[_dc] = pd.to_datetime(_save_tkt_df[_dc], errors="coerce") \
                                                  .dt.tz_localize(None)

                    _counts = append_r25_full_burndown(_engine(), _ft_burn_df, _save_tkt_df)
                st.success(
                    f"Saved to DB — r25_burndown: Committed + Full Team rows · "
                    f"r25_sprint_tickets: {_counts['ticket_rows']} tickets"
                )

            # ── Ticket table with assignee filter ─────────────────────────────
            st.markdown("---")
            sec(f"Full Ticket List ({len(_full_pool)} tickets)")

            _tbl_assignees = ["All"] + sorted(_full_pool["assignee"].dropna().unique().tolist())
            _tbl_scope_filter = st.radio("Scope", ["All", "In Scope", "Out of Scope"],
                                         horizontal=True, key="all_burn_scope_filter")
            _tbl_assignee_filter = st.selectbox("Assignee", _tbl_assignees, key="all_burn_assignee")

            _tbl_df = _full_pool.copy()
            if _tbl_assignee_filter != "All":
                _tbl_df = _tbl_df[_tbl_df["assignee"] == _tbl_assignee_filter]
            if _tbl_scope_filter == "In Scope":
                _tbl_df = _tbl_df[_tbl_df["in_scope"]]
            elif _tbl_scope_filter == "Out of Scope":
                _tbl_df = _tbl_df[~_tbl_df["in_scope"]]

            _tbl_cols = [c for c in ["key", "summary", "assignee", "status",
                                      "story_points", "in_scope", "_resolved_at"]
                         if c in _tbl_df.columns]
            st.dataframe(
                _tbl_df[_tbl_cols]
                .rename(columns={"_resolved_at": "completed_at", "in_scope": "In Scope"})
                .sort_values("completed_at", na_position="last"),
                use_container_width=True, hide_index=True,
            )
        else:
            st.info("Select sprint dates above to display this burndown.")


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
    st.markdown("#### Team Commitment — R25")

    # ── Status classification (case-insensitive) ──────────────────────────────
    DELIVERED_STATUSES = {
        "closed", "qualification test", "ready for staging",
        "ready for exceptions", "ready for qa", "ready for sprint",
        "cancelled", "canceled", "on hold", "plan investigation", "work approved",
        "ready for acceptance", "waiting for customer",
    }
    NOT_DELIVERED_STATUSES = {
        "acknowledge", "analysis", "dev in progress", "estimation", "in progress",
    }

    # ── Load data ─────────────────────────────────────────────────────────────
    try:
        avail_df, sprint_info = load_team_availability()
        scope_df_t   = load_r25_scope()
        scope_keys_t = scope_df_t["key"].tolist()
        assignee_squad_df = load_r25_assignee_squad()
    except Exception as _e:
        st.error(f"Could not load Release Lifecycle file: {_e}")
        st.stop()

    # ── Build ticket dataframe ────────────────────────────────────────────────
    _db_cols = ["key", "status", "story_points", "qualification_date",
                "resolved", "closure_date", "assignee", "expected_sprint",
                "issue_type", "project", "summary", "priority"]
    _df_all = df[[c for c in _db_cols if c in df.columns]].copy()
    _df_all["_pts"] = pd.to_numeric(_df_all["story_points"], errors="coerce").fillna(0)
    _df_all["_status_lower"] = _df_all["status"].str.lower().str.strip().fillna("")
    _df_all["_is_delivered"]     = _df_all["_status_lower"].isin(DELIVERED_STATUSES)
    _df_all["_is_not_delivered"] = _df_all["_status_lower"].isin(NOT_DELIVERED_STATUSES)

    # Committed scope only
    _df_m = _df_all[_df_all["key"].isin(scope_keys_t)].copy()

    # ── Sprint date pickers ───────────────────────────────────────────────────
    import datetime as _dt_team
    _T_DEFAULT_START = sprint_info.get("start") or _dt_team.date(2026, 3, 8)
    _T_DEFAULT_END   = sprint_info.get("end")   or _dt_team.date(2026, 4, 4)

    _tc1, _tc2 = st.columns(2)
    with _tc1:
        _team_sprint_start = st.date_input(
            "Sprint Start",
            value=st.session_state.get("burn_start", _T_DEFAULT_START),
            key="team_sprint_start",
        )
    with _tc2:
        _team_sprint_end = st.date_input(
            "Sprint End",
            value=st.session_state.get("burn_end", _T_DEFAULT_END),
            key="team_sprint_end",
        )

    _sp_start = pd.Timestamp(_team_sprint_start)
    _sp_end   = pd.Timestamp(_team_sprint_end) + pd.Timedelta(hours=23, minutes=59)

    st.markdown("---")

    # ── Exclusive one-to-one name matching ───────────────────────────────────
    _all_scope_assignees = _df_all["assignee"].dropna().unique().tolist()
    _unique_avail_names  = avail_df["name"].drop_duplicates().tolist()

    _pair_scores = []
    for _jn in _all_scope_assignees:
        for _an in _unique_avail_names:
            _s = _name_score(_jn, _an)
            if _s >= 0.65:
                _pair_scores.append({"jira": _jn, "avail": _an, "score": _s})

    _jira_to_avail: dict = {}
    for _p in sorted(_pair_scores, key=lambda x: -x["score"]):
        if _p["jira"] not in _jira_to_avail:
            _jira_to_avail[_p["jira"]] = _p["avail"]

    _avail_to_jiras: dict = {}
    for _jn, _an in _jira_to_avail.items():
        _avail_to_jiras.setdefault(_an, []).append(_jn)

    _matched_jira_names = set(_jira_to_avail.keys())

    # ── Squad normalisation ───────────────────────────────────────────────────
    def _normalise_squad(s):
        if not s or str(s).strip().lower() in ("", "nan", "none"):
            return "—"
        s = str(s).strip()
        sl = s.lower()
        # Transverse is a work category, not a real squad — exclude
        if sl in ("transverse",):
            return "—"
        # DSN/FLUX FINANCIER — case unify
        if s.upper() == "DSN/FLUX FINANCIER" or "flux financier" in sl or "flux" in sl and "dsn" in sl:
            return "DSN/FLUX FINANCIER"
        # Prévoyance / Risk & Protection (same squad)
        if "pr" in sl and ("voyance" in sl or "voyance" in sl):
            return "Risk & Protection"
        if "risk" in sl and "protection" in sl:
            return "Risk & Protection"
        # Contrats & Santé → Health & Contracts & Persons
        if "contrat" in sl or "sant" in sl:
            return "Health & Contracts & Persons"
        if "health" in sl and ("contract" in sl or "person" in sl):
            return "Health & Contracts & Persons"
        # Editique → Printing
        if "editique" in sl or "\u00e9ditique" in sl:
            return "Printing"
        # Comptabilité/PDM → Accounting/PDM/BI
        if "comptab" in sl or "compta" in sl:
            return "Accounting/PDM/BI"
        if "accounting" in sl or "pdm" in sl:
            return "Accounting/PDM/BI"
        return s

    # ── Squad lookup: jira_name → squad (three-level priority) ───────────────
    # 1. r25_assignee_squad: AQ roster rows in scope file (most authoritative)
    # Priority order (sprint-specific beats general roster):
    # 1. Scope ticket key→squad  — most specific: sprint planning document says who's in which squad
    # 2. AQ roster               — general team structure (fallback for people with no scope tickets)
    # 3. Availability sheet      — last resort
    _jn_squad_map: dict = {}

    # Level 1: scope ticket key→squad (PRIMARY — explicit sprint assignment)
    _scope_key_squad: dict = {}
    if "squad" in scope_df_t.columns:
        for _, _sr in scope_df_t[["key", "squad"]].iterrows():
            _sq = _normalise_squad(_sr["squad"])
            if _sq != "—":
                _scope_key_squad[_sr["key"]] = _sq
        _scope_jn_df = _df_all[["key", "assignee"]].copy()
        _scope_jn_df["squad"] = _scope_jn_df["key"].map(_scope_key_squad)
        for _jn in _matched_jira_names:
            _squads = _scope_jn_df[_scope_jn_df["assignee"] == _jn]["squad"].dropna()
            if not _squads.empty:
                _jn_squad_map[_jn] = _squads.mode().iloc[0]

    # Level 2: AQ roster (fallback for people without scope tickets, e.g. capacity-only members)
    if not assignee_squad_df.empty:
        _sa_squad: dict = {}
        for _, _sr in assignee_squad_df.iterrows():
            _raw_name = str(_sr["assignee_name"]).strip()
            _sq = _normalise_squad(_sr["squad"])
            if not _raw_name or _raw_name.lower() in ("nan", "none", "") or _sq == "—":
                continue
            _sa_squad.setdefault(_raw_name, _sq)

        for _raw_name, _sq in _sa_squad.items():
            _best_jn, _best_score = None, 0.0
            for _jn in _matched_jira_names:
                _sc = _name_score(_raw_name, _jn)
                if _sc > _best_score:
                    _best_score, _best_jn = _sc, _jn
            if _best_jn and _best_score >= 0.55 and _best_jn not in _jn_squad_map:
                _jn_squad_map[_best_jn] = _sq

    # Level 3: availability sheet squad (last resort, Transverse excluded by normaliser)
    _avail_name_squad_lookup = {
        row["name"]: _normalise_squad(row.get("squad", "—"))
        for _, row in avail_df.iterrows()
    }
    for _an, _jiras in _avail_to_jiras.items():
        for _jn in _jiras:
            if _jn not in _jn_squad_map:
                _sq = _avail_name_squad_lookup.get(_an, "—")
                if _sq != "—":
                    _jn_squad_map[_jn] = _sq

    # Supplementary: scope ticket owners NOT in availability sheet (e.g. LERMA/TMA)
    # They contribute to the squad chart only — no capacity data.
    _scope_extra_jn_squad: dict = {}
    if _scope_key_squad:
        _scope_ticket_assignees = (
            _df_all[_df_all["key"].isin(scope_keys_t)]["assignee"].dropna().unique()
        )
        for _jn in _scope_ticket_assignees:
            if _jn in _matched_jira_names or _jn in _jn_squad_map:
                continue
            _keys = _df_all[_df_all["assignee"] == _jn]["key"].tolist()
            for _k in _keys:
                if _k in _scope_key_squad:
                    _scope_extra_jn_squad[_jn] = _scope_key_squad[_k]
                    break

    # ── Combined squad map (scope-extra overridden by AQ-roster) ─────────────
    _combined_squad_map = {**_scope_extra_jn_squad, **_jn_squad_map}

    # ── Scope ticket pool: committed scope tickets with known assignees ────────
    _all_team_jn = _matched_jira_names | set(_scope_extra_jn_squad.keys())
    _scope_pool = _df_m[_df_m["assignee"].isin(_all_team_jn)].copy()
    _scope_pool["squad"] = _scope_pool["assignee"].map(_combined_squad_map).fillna("—")
    _scope_pool["display_name"] = _scope_pool["assignee"].map(
        {_jn: _jira_to_avail.get(_jn, _jn) for _jn in _all_team_jn}
    ).fillna(_scope_pool["assignee"])

    # ── Commitment formula (aligned with team standard):
    # Commitment % = Delivered / (Delivered + Not Delivered) × 100
    # OTHER-status tickets are excluded from the denominator — they are engaged
    # but neither clearly delivered nor clearly in-progress, so they don't
    # penalise or inflate the commitment score.
    def _commitment(delivered, not_delivered):
        denom = delivered + not_delivered
        return round(delivered / denom * 100, 1) if denom > 0 else 0.0

    # ── Per-assignee commitment metrics ──────────────────────────────────────
    _assignee_rows = []
    for _jn in sorted(_all_team_jn):
        _tix = _scope_pool[_scope_pool["assignee"] == _jn]
        if _tix.empty:
            continue
        _eng_t   = len(_tix)
        _eng_sp  = float(_tix["_pts"].sum())
        _del_t   = int(_tix["_is_delivered"].sum())
        _del_sp  = float(_tix[_tix["_is_delivered"]]["_pts"].sum())
        _ndel_t  = int(_tix["_is_not_delivered"].sum())
        _ndel_sp = float(_tix[_tix["_is_not_delivered"]]["_pts"].sum())
        _assignee_rows.append({
            "display_name":          _jira_to_avail.get(_jn, _jn),
            "jira_name":             _jn,
            "squad":                 _combined_squad_map.get(_jn, "—"),
            "engaged_tickets":       _eng_t,
            "engaged_sp":            _eng_sp,
            "delivered_tickets":     _del_t,
            "delivered_sp":          _del_sp,
            "not_delivered_tickets": _ndel_t,
            "not_delivered_sp":      _ndel_sp,
            "commitment_pct":        _commitment(_del_t, _ndel_t),
            "commitment_sp_pct":     _commitment(_del_sp, _ndel_sp),
        })
    _assignee_df = pd.DataFrame(_assignee_rows)

    # ── Per-squad commitment metrics (aggregated from scope_pool directly) ────
    # Aggregate from raw tickets (not from assignee rows) to avoid double-counting
    _squad_rows = []
    _sq_pool_valid = _scope_pool[_scope_pool["squad"] != "—"].copy()
    for _sq, _grp in _sq_pool_valid.groupby("squad"):
        _sq_eng_t   = len(_grp)
        _sq_eng_sp  = float(_grp["_pts"].sum())
        _sq_del_t   = int(_grp["_is_delivered"].sum())
        _sq_del_sp  = float(_grp[_grp["_is_delivered"]]["_pts"].sum())
        _sq_ndel_t  = int(_grp["_is_not_delivered"].sum())
        _sq_ndel_sp = float(_grp[_grp["_is_not_delivered"]]["_pts"].sum())
        _members    = _grp["assignee"].nunique()
        _squad_rows.append({
            "squad":                 _sq,
            "members":               _members,
            "engaged_tickets":       _sq_eng_t,
            "engaged_sp":            _sq_eng_sp,
            "delivered_tickets":     _sq_del_t,
            "delivered_sp":          _sq_del_sp,
            "not_delivered_tickets": _sq_ndel_t,
            "not_delivered_sp":      _sq_ndel_sp,
            "commitment_pct":        _commitment(_sq_del_t, _sq_ndel_t),
            "commitment_sp_pct":     _commitment(_sq_del_sp, _sq_ndel_sp),
        })
    _squad_df = (
        pd.DataFrame(_squad_rows).sort_values("commitment_pct", ascending=False).reset_index(drop=True)
        if _squad_rows else pd.DataFrame()
    )

    # ── Team-level KPI totals ─────────────────────────────────────────────────
    _total_eng_t   = int(_sq_pool_valid["_is_delivered"].count()) if not _sq_pool_valid.empty else 0
    _total_eng_sp  = float(_sq_pool_valid["_pts"].sum()) if not _sq_pool_valid.empty else 0
    _total_del_t   = int(_sq_pool_valid["_is_delivered"].sum()) if not _sq_pool_valid.empty else 0
    _total_del_sp  = float(_sq_pool_valid[_sq_pool_valid["_is_delivered"]]["_pts"].sum()) if not _sq_pool_valid.empty else 0
    _total_ndel_t  = int(_sq_pool_valid["_is_not_delivered"].sum()) if not _sq_pool_valid.empty else 0
    _total_ndel_sp = float(_sq_pool_valid[_sq_pool_valid["_is_not_delivered"]]["_pts"].sum()) if not _sq_pool_valid.empty else 0
    _team_commit   = _commitment(_total_del_t, _total_ndel_t)
    _team_commit_sp = _commitment(_total_del_sp, _total_ndel_sp)

    # ── Sprint banner ─────────────────────────────────────────────────────────
    _team_n_days = (_team_sprint_end - _team_sprint_start).days + 1
    _sb1, _sb2, _sb3, _sb4, _sb5 = st.columns(5)
    with _sb1: kpi_card("Sprint", "R25")
    with _sb2: kpi_card("Duration", f"{_team_n_days} days")
    with _sb3: kpi_card("Dates",
                         f"{_team_sprint_start.strftime('%d %b')} → "
                         f"{_team_sprint_end.strftime('%d %b %Y')}")
    with _sb4: kpi_card("Engaged SP", f"{_total_eng_sp:.0f} SP")
    with _sb5: kpi_card("Team Commitment", f"{_team_commit:.1f}%",
                         color="#4CAF50" if _team_commit >= 80 else "#E65100")

    st.markdown("---")

    # ── Team KPI banner ────────────────────────────────────────────────────────
    st.caption(
        "Commitment % = Delivered / (Delivered + Not Delivered) × 100  "
        "— OTHER-status tickets are engaged but excluded from the denominator."
    )
    _k1, _k2, _k3, _k4, _k5, _k6 = st.columns(6)
    with _k1: kpi_card("Engaged Tickets", str(_total_eng_t))
    with _k2: kpi_card("Engaged SP", f"{_total_eng_sp:.0f}")
    with _k3: kpi_card("Delivered (T)", str(_total_del_t), color="#4CAF50")
    with _k4: kpi_card("Delivered SP", f"{_total_del_sp:.0f}", color="#4CAF50")
    with _k5: kpi_card("Not Delivered (T)", str(_total_ndel_t), color="#E65100")
    with _k6: kpi_card("Commitment (T)",
                        f"{_team_commit:.1f}%",
                        color="#4CAF50" if _team_commit >= 80 else "#E65100")

    st.markdown("---")

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 1 — SQUAD COMMITMENT SUMMARY
    # ══════════════════════════════════════════════════════════════════════════
    sec("Squad Commitment Summary")

    if _squad_df.empty:
        st.info("No squad data available.")
    else:
        # ── Table with Total row ───────────────────────────────────────────────
        _sq_tbl = _squad_df[[
            "squad", "members", "engaged_tickets", "engaged_sp",
            "delivered_tickets", "delivered_sp",
            "not_delivered_tickets", "not_delivered_sp",
            "commitment_pct",
        ]].copy()

        # Add Total row
        _sq_total = pd.DataFrame([{
            "squad":                 "TOTAL",
            "members":               _sq_tbl["members"].sum(),
            "engaged_tickets":       _sq_tbl["engaged_tickets"].sum(),
            "engaged_sp":            _sq_tbl["engaged_sp"].sum(),
            "delivered_tickets":     _sq_tbl["delivered_tickets"].sum(),
            "delivered_sp":          _sq_tbl["delivered_sp"].sum(),
            "not_delivered_tickets": _sq_tbl["not_delivered_tickets"].sum(),
            "not_delivered_sp":      _sq_tbl["not_delivered_sp"].sum(),
            "commitment_pct":        _commitment(
                int(_sq_tbl["delivered_tickets"].sum()),
                int(_sq_tbl["not_delivered_tickets"].sum()),
            ),
        }])
        _sq_tbl = pd.concat([_sq_tbl, _sq_total], ignore_index=True)
        _sq_tbl = _sq_tbl.rename(columns={
            "squad":                 "Squad",
            "members":               "Members",
            "engaged_tickets":       "Engaged (T)",
            "engaged_sp":            "Engaged SP",
            "delivered_tickets":     "Delivered (T)",
            "delivered_sp":          "Delivered SP",
            "not_delivered_tickets": "Not Delivered (T)",
            "not_delivered_sp":      "Not Delivered SP",
            "commitment_pct":        "Commitment %",
        })

        def _sq_commit_color(val):
            if val == "TOTAL":
                return "font-weight:bold"
            c = "#4CAF50" if val >= 80 else ("#E65100" if val >= 50 else "#C62828")
            return f"background-color:{c};color:white;font-weight:bold;border-radius:4px"

        st.dataframe(
            _sq_tbl.style.applymap(_sq_commit_color, subset=["Commitment %"]),
            use_container_width=True, hide_index=True,
        )
        st.markdown("<br>", unsafe_allow_html=True)

        # ── Stacked bar: delivered vs not-delivered SP per squad ───────────────
        _sq_sorted = _squad_df.sort_values("commitment_pct", ascending=False)
        _sq_fig = go.Figure()
        _sq_fig.add_trace(go.Bar(
            x=_sq_sorted["squad"],
            y=_sq_sorted["delivered_sp"],
            name="Delivered SP",
            marker=dict(color="#4CAF50", line=dict(color="white", width=1)),
            text=[f"<b>{v:.0f}</b>" for v in _sq_sorted["delivered_sp"]],
            textposition="inside",
            textfont=dict(color="white", size=12),
            hovertemplate="<b>%{x}</b><br>Delivered: %{y:.0f} SP (%{customdata} tickets)<extra></extra>",
            customdata=_sq_sorted["delivered_tickets"],
        ))
        _sq_fig.add_trace(go.Bar(
            x=_sq_sorted["squad"],
            y=_sq_sorted["not_delivered_sp"],
            name="Not Delivered SP",
            marker=dict(color="#E65100", line=dict(color="white", width=1)),
            text=[f"<b>{v:.0f}</b>" for v in _sq_sorted["not_delivered_sp"]],
            textposition="inside",
            textfont=dict(color="white", size=12),
            hovertemplate="<b>%{x}</b><br>Not Delivered: %{y:.0f} SP (%{customdata} tickets)<extra></extra>",
            customdata=_sq_sorted["not_delivered_tickets"],
        ))
        # Commitment % label above each bar
        _sq_fig.add_trace(go.Scatter(
            x=_sq_sorted["squad"],
            y=_sq_sorted["engaged_sp"] * 1.06,
            mode="text",
            text=[f"<b>{p:.0f}%</b>" for p in _sq_sorted["commitment_pct"]],
            textfont=dict(size=14, color=DXC_PURPLE),
            showlegend=False,
            hoverinfo="skip",
        ))
        _sq_fig.update_layout(**{
            **CHART_THEME,
            "barmode": "stack",
            "height": 400,
            "bargap": 0.35,
            "xaxis": dict(gridcolor=_GRID, tickfont=dict(size=12, color=DXC_TEXT)),
            "yaxis": dict(title="Story Points", gridcolor=_GRID, zeroline=False),
            "legend": dict(orientation="h", y=1.08, x=0.5, xanchor="center",
                           font=dict(size=12, color=DXC_TEXT)),
            "margin": dict(t=50, b=30, l=20, r=20),
        })
        chart(_sq_fig)

    st.markdown("---")

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 2 — ASSIGNEE COMMITMENT BREAKDOWN
    # ══════════════════════════════════════════════════════════════════════════
    sec("Assignee Commitment Breakdown")
    st.caption(
        "Green = delivered · Orange = not yet delivered · "
        "**Commitment %** = Delivered / (Delivered + Not Delivered) × 100 (tickets) · "
        "OTHER-status tickets are shown in Engaged but excluded from the % denominator."
    )

    if _assignee_df.empty:
        st.info("No assignee data available.")
    else:
        # ── Table ──────────────────────────────────────────────────────────────
        _a_tbl = _assignee_df[[
            "display_name", "squad",
            "engaged_tickets", "engaged_sp",
            "delivered_tickets", "delivered_sp",
            "not_delivered_tickets", "not_delivered_sp",
            "commitment_pct", "commitment_sp_pct",
        ]].copy()
        _a_tbl.columns = [
            "Name", "Squad",
            "Engaged (T)", "Engaged SP",
            "Delivered (T)", "Delivered SP",
            "Not Delivered (T)", "Not Delivered SP",
            "Commitment % (T)", "Commitment % (SP)",
        ]
        _a_tbl = _a_tbl.sort_values("Commitment % (T)", ascending=False).reset_index(drop=True)
        st.dataframe(
            _a_tbl.style.background_gradient(
                subset=["Commitment % (T)", "Commitment % (SP)"], cmap="RdYlGn", vmin=0, vmax=100
            ),
            use_container_width=True, hide_index=True,
        )
        st.markdown("<br>", unsafe_allow_html=True)

        # ── Horizontal stacked bar: delivered vs not-delivered SP per person ───
        _a_sorted = _assignee_df.sort_values("commitment_pct", ascending=True)
        _af = go.Figure()
        _af.add_trace(go.Bar(
            x=_a_sorted["delivered_sp"],
            y=_a_sorted["display_name"],
            orientation="h",
            name="Delivered SP",
            marker=dict(color="#4CAF50", line=dict(width=0)),
            text=[f"{v:.0f}" for v in _a_sorted["delivered_sp"]],
            textposition="inside",
            textfont=dict(color="white", size=11),
            hovertemplate="<b>%{y}</b><br>Delivered: %{x:.0f} SP (%{customdata} tickets)<extra></extra>",
            customdata=_a_sorted["delivered_tickets"],
        ))
        _af.add_trace(go.Bar(
            x=_a_sorted["not_delivered_sp"],
            y=_a_sorted["display_name"],
            orientation="h",
            name="Not Delivered SP",
            marker=dict(color="#E65100", line=dict(width=0)),
            text=[f"{v:.0f}" for v in _a_sorted["not_delivered_sp"]],
            textposition="inside",
            textfont=dict(color="white", size=11),
            hovertemplate="<b>%{y}</b><br>Not Delivered: %{x:.0f} SP (%{customdata} tickets)<extra></extra>",
            customdata=_a_sorted["not_delivered_tickets"],
        ))
        # Commitment % label at end of bar
        _af.add_trace(go.Scatter(
            x=_a_sorted["engaged_sp"] * 1.03,
            y=_a_sorted["display_name"],
            mode="text",
            text=[f"<b>{p:.0f}%</b>" for p in _a_sorted["commitment_pct"]],
            textfont=dict(size=11, color=DXC_PURPLE),
            showlegend=False,
            hoverinfo="skip",
        ))
        _af.update_layout(**{
            **CHART_THEME,
            "barmode": "stack",
            "height": max(400, len(_a_sorted) * 38),
            "xaxis": dict(title="Story Points", gridcolor=_GRID),
            "yaxis": dict(tickfont=dict(size=11)),
            "legend": dict(orientation="h", y=1.04, x=0),
            "margin": dict(t=20, b=10, l=10, r=80),
        })
        chart(_af)

    st.markdown("---")

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 3 — TICKET DRILL-DOWN (per squad → per assignee)
    # ══════════════════════════════════════════════════════════════════════════
    sec("Ticket Drill-down")
    st.caption(
        "Scope tickets per assignee, classified by current status.  "
        "Green background = delivered · Orange = not delivered."
    )

    def _cell_status_style(val):
        sl = str(val).lower().strip()
        if sl in DELIVERED_STATUSES:
            return "background-color:#e8f5e9;color:#1b5e20"
        if sl in NOT_DELIVERED_STATUSES:
            return "background-color:#fff3e0;color:#bf360c"
        return "background-color:#f3e5f5;color:#4a148c"

    _drill_squads = sorted(
        s for s in _scope_pool["squad"].dropna().unique() if s != "—"
    )

    for _dsq in _drill_squads:
        _sq_tix = _scope_pool[_scope_pool["squad"] == _dsq]
        _sq_del = int(_sq_tix["_is_delivered"].sum())
        _sq_eng = len(_sq_tix)
        _sq_commit_pct = round(_sq_del / _sq_eng * 100) if _sq_eng > 0 else 0

        with st.expander(
            f"{_dsq}  —  {_sq_del}/{_sq_eng} delivered  ({_sq_commit_pct}%)",
            expanded=False,
        ):
            for _jn in sorted(_sq_tix["assignee"].unique()):
                _p_tix = _sq_tix[_sq_tix["assignee"] == _jn].copy()
                _p_name  = _jira_to_avail.get(_jn, _jn)
                _p_del   = int(_p_tix["_is_delivered"].sum())
                _p_eng   = len(_p_tix)
                _p_commit_pct = round(_p_del / _p_eng * 100) if _p_eng > 0 else 0
                _p_del_sp = float(_p_tix[_p_tix["_is_delivered"]]["_pts"].sum())
                _p_eng_sp = float(_p_tix["_pts"].sum())

                st.markdown(
                    f"**{_p_name}** &nbsp;·&nbsp; "
                    f"{_p_del}/{_p_eng} tickets &nbsp;·&nbsp; "
                    f"{_p_del_sp:.0f}/{_p_eng_sp:.0f} SP &nbsp;·&nbsp; "
                    f"**{_p_commit_pct}% commitment**"
                )
                _show_cols = [c for c in [
                    "key", "summary", "status", "_pts", "issue_type", "priority",
                ] if c in _p_tix.columns]
                _tix_show = _p_tix[_show_cols].rename(columns={
                    "key": "Key", "summary": "Summary", "status": "Status",
                    "_pts": "SP", "issue_type": "Type", "priority": "Priority",
                }).reset_index(drop=True)
                st.dataframe(
                    _tix_show.style.applymap(_cell_status_style, subset=["Status"]),
                    use_container_width=True, hide_index=True,
                )
                st.markdown("<br>", unsafe_allow_html=True)

    st.markdown("---")

    # ══════════════════════════════════════════════════════════════════════════
    # EXPORT TO DATABASE (for PowerBI)
    # ══════════════════════════════════════════════════════════════════════════
    sec("Export to Database")
    st.caption(
        "Writes three tables to the DB: **r25_team_assignee**, **r25_team_squad**, "
        "**r25_team_tickets** — connect these in PowerBI for commitment charts."
    )
    def _do_save_team_db():
        """Build ticket table and write all three commitment tables to DB."""
        _tickets_out = _scope_pool[[
            c for c in ["key", "summary", "status", "assignee", "display_name",
                         "squad", "_pts", "issue_type", "priority",
                         "_is_delivered", "_is_not_delivered",
                         "qualification_date", "resolved", "closure_date"]
            if c in _scope_pool.columns
        ]].rename(columns={
            "_pts":              "story_points",
            "_is_delivered":     "is_delivered",
            "_is_not_delivered": "is_not_delivered",
        }).copy()
        for _bc in ["is_delivered", "is_not_delivered"]:
            if _bc in _tickets_out.columns:
                _tickets_out[_bc] = _tickets_out[_bc].astype(int)

        # Compute exclusion_reason for burndown context
        # A ticket is excluded from burndown if: delivered status but no date within sprint
        _t_sp_s = pd.Timestamp(_team_sprint_start)
        _t_sp_e = pd.Timestamp(_team_sprint_end) + pd.Timedelta(hours=23, minutes=59)
        _DELIVERED_SET = {
            "closed", "qualification test", "ready for staging",
            "ready for exceptions", "ready for qa", "ready for sprint",
            "cancelled", "canceled", "on hold", "plan investigation", "work approved",
            "ready for acceptance", "waiting for customer",
        }
        _t_is_done = _tickets_out["status"].str.lower().str.strip().isin(_DELIVERED_SET)
        _date_cols_t = [c for c in ["qualification_date", "resolved", "closure_date"]
                        if c in _tickets_out.columns]
        # Earliest raw date
        _any_date = pd.concat(
            [pd.to_datetime(_tickets_out[c], errors="coerce") for c in _date_cols_t], axis=1
        ).min(axis=1)
        # Earliest date within sprint
        _in_sprint = pd.concat([
            pd.to_datetime(_tickets_out[c], errors="coerce").where(
                lambda s: s.notna() & (s >= _t_sp_s) & (s <= _t_sp_e)
            ) for c in _date_cols_t
        ], axis=1).min(axis=1)
        _has_in_sprint = _in_sprint.notna()

        def _excl_reason(row_idx):
            if not _t_is_done.iloc[row_idx]:
                return None  # not delivered — not applicable
            if _has_in_sprint.iloc[row_idx]:
                return None  # correctly placed on burndown
            if pd.isna(_any_date.iloc[row_idx]):
                return None  # NO_DATE → counted at end of sprint, not excluded
            return "DATE_OUTSIDE_SPRINT"

        _tickets_out["exclusion_reason"] = [
            _excl_reason(i) for i in range(len(_tickets_out))
        ]

        _assignee_out = _assignee_df.drop(columns=["jira_name"], errors="ignore")
        _squad_out = _squad_df.copy()

        return materialise_r25_team_commitment(
            _engine(),
            _assignee_out,
            _squad_out,
            _tickets_out,
        )

    _btn_col1, _btn_col2 = st.columns([2, 2])
    with _btn_col1:
        if st.button("Save team commitment to DB", type="primary", key="save_team_db"):
            if _assignee_df.empty:
                st.warning("No data to save — load the Release Lifecycle file first.")
            else:
                try:
                    _counts = _do_save_team_db()
                    st.success(
                        f"Saved — "
                        f"{_counts['r25_team_assignee']} assignees · "
                        f"{_counts['r25_team_squad']} squads · "
                        f"{_counts['r25_team_tickets']} tickets"
                    )
                except Exception as _ex:
                    st.error(f"DB write failed: {_ex}")
    with _btn_col2:
        if st.button("Refresh DB tables", key="refresh_team_db",
                     help="Re-run the save with current data (use after a Jira sync)"):
            if _assignee_df.empty:
                st.warning("No data to refresh — load the Release Lifecycle file first.")
            else:
                try:
                    _counts = _do_save_team_db()
                    st.success(
                        f"Refreshed — "
                        f"{_counts['r25_team_assignee']} assignees · "
                        f"{_counts['r25_team_squad']} squads · "
                        f"{_counts['r25_team_tickets']} tickets"
                    )
                except Exception as _ex:
                    st.error(f"DB refresh failed: {_ex}")

    st.markdown("---")

    # Debug — name matching (hidden by default)
    with st.expander("Debug — Name Matching & Squad Assignments", expanded=False):
        _score_lookup = {(_p["avail"], _p["jira"]): round(_p["score"], 2) for _p in _pair_scores}
        _debug_rows = []
        for _an in _unique_avail_names:
            _jiras   = _avail_to_jiras.get(_an, [])
            _scores  = [str(_score_lookup.get((_an, _jn), "?")) for _jn in _jiras]
            _squad_d = next((_jn_squad_map.get(_jn) for _jn in _jiras if _jn in _jn_squad_map), "—")
            _a_row   = next(
                (r for r in _assignee_rows if r["display_name"] == _an), {}
            )
            _debug_rows.append({
                "Avail Name":           _an,
                "Matched Jira Name(s)": ", ".join(_jiras) if _jiras else "— no match —",
                "Score(s)":             ", ".join(_scores) if _scores else "—",
                "Squad":                _squad_d,
                "Engaged Tickets":      _a_row.get("engaged_tickets", 0),
                "Delivered SP":         round(_a_row.get("delivered_sp", 0.0), 1),
                "Commitment %":         _a_row.get("commitment_pct", 0.0),
            })
        st.dataframe(pd.DataFrame(_debug_rows), use_container_width=True, hide_index=True)



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
