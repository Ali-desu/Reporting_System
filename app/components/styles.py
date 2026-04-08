"""
DXC colour tokens, global CSS, and Plotly chart theme.
"""

# ── Colour tokens ─────────────────────────────────────────────────────────────
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

# Light-mode grid colour used in per-chart xaxis/yaxis overrides
_GRID = "#E8E2EE"

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

# ── Global CSS ────────────────────────────────────────────────────────────────
CSS = f"""
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
"""
