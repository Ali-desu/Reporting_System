"""
ETL module: read Extract.xlsx → clean → load into MySQL `issues` table.
Run standalone:  python etl.py [path/to/Extract.xlsx]
"""
import re
import ssl
import sys
import os

import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()


def build_engine(host: str, port: int, name: str, user: str, password: str):
    """Create a SQLAlchemy engine from explicit credentials."""
    url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{name}"
    if host == "localhost":
        return create_engine(url, connect_args={"ssl_disabled": True})
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return create_engine(url, connect_args={"ssl": ctx})


def get_engine():
    """CLI use only — reads credentials from .env."""
    return build_engine(
        host=os.getenv("DB_HOST", "mysql-6047a7e-uca-0f17.e.aivencloud.com"),
        port=int(os.getenv("DB_PORT", "25768")),
        name=os.getenv("DB_NAME", "ReportingSystemDB"),
        user=os.getenv("DB_USER", "avnadmin"),
        password=os.getenv("DB_PASSWORD", ""),
    )

# Columns we care about: original name → DB column name
COLUMNS_MAP = {
    "Key":                                  "key",
    "Issue Type":                           "issue_type",
    "Summary":                              "summary",
    "Organizations":                        "organizations",
    "Customer Reference Id":                "customer_reference_id",
    "Environment Type":                     "environment_type",
    "Environment":                          "environment",
    "Component":                            "component",
    "Assignee":                             "assignee",
    "Reporter":                             "reporter",
    "Priority":                             "priority",
    "Current Tier":                         "current_tier",
    "Status":                               "status",
    "Created":                              "created",
    "Reproductibility":                     "reproductibility",
    "Resolutions":                          "resolutions",
    "Root Cause Description":               "root_cause_description",
    "Impact Description":                   "impact_description",
    "Resolution Description":               "resolution_description",
    "Last Comment Date/Time":               "last_comment_datetime",
    "Client Priority":                      "client_priority",
    "Target Release":                       "target_release",
    "Closure Date":                         "closure_date",
    "Resolved":                             "resolved",
    "Count of Ready for acceptance":        "count_ready_acceptance",
    "Count of ready for staging":           "count_ready_staging",
    "Start Date & Time":                    "start_date_time",
    "Due date":                             "due_date",
    "Product Line":                         "product_line",
    "KPI - Time to Solve":                  "kpi_time_to_solve",
    "KPI - Time Initial Response":          "kpi_time_initial_response",
    "KPI - Time to Analyse":               "kpi_time_to_analyse",
    "KPI - Time to Assist":                 "kpi_time_to_assist",
    "KPI - Time to Estimate":              "kpi_time_to_estimate",
    "Occurrences":                          "occurrences",
    "Sending Date":                         "sending_date",
    "SLA Justified":                        "sla_justified",
    "OUT OF SLA Reason":                    "out_of_sla_reason",
    "Story Points":                         "story_points",
    "Root Cause Origin":                    "root_cause_origin",
    "Nombre d'UO":                          "nombre_uo",
    "Service request types":               "service_request_types",
    "Enhancement request type":            "enhancement_request_type",
    "Project":                              "project",
    "Qualification date":                   "qualification_date",
    "Resolution Owner":                     "resolution_owner",
    "Fix versions":                         "fix_versions",
    "Expected Sprint":                      "expected_sprint",
    "Original Expected Sprint":             "original_expected_sprint",
    "Baseline / Standard Issue":            "baseline_standard_issue",
}

DATE_COLS = [
    "created", "resolved", "closure_date", "sending_date",
    "qualification_date", "last_comment_datetime",
    "start_date_time", "due_date",
]

KPI_COLS = [
    "kpi_time_to_solve",
    "kpi_time_initial_response",
    "kpi_time_to_analyse",
    "kpi_time_to_assist",
    "kpi_time_to_estimate",
]


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _parse_kpi_minutes(val) -> float | None:
    """
    Convert KPI strings like '998h 31m' or '-2,891h 24m' to total minutes.
    Negative result means SLA breach.
    """
    if pd.isna(val) or str(val).strip() == "":
        return None
    val = str(val).replace(",", "").strip()
    m = re.match(r"(-?\d+)h\s*(\d+)m", val)
    if not m:
        return None
    hours, mins = int(m.group(1)), int(m.group(2))
    sign = -1 if hours < 0 else 1
    return hours * 60 + sign * mins


def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """Clean and normalise a raw Extract DataFrame."""

    # 1. Select & rename columns present in this file
    available = {k: v for k, v in COLUMNS_MAP.items() if k in df.columns}
    df = df[list(available.keys())].rename(columns=available).copy()

    # 2. Drop rows with no Key (empty trailing rows in Excel exports)
    #    Trim key first so "ABC-123 " and "ABC-123" are treated as the same,
    #    then deduplicate — keep last occurrence of each key
    if "key" in df.columns:
        df["key"] = df["key"].astype(str).str.strip()
        df = df[df["key"].notna() & (df["key"] != "") & (df["key"] != "nan")].copy()
        df = df.drop_duplicates(subset=["key"], keep="last")

    # 3. Drop entirely-null columns (e.g. Committed Release)
    df.dropna(axis=1, how="all", inplace=True)

    # 3. Parse KPI strings → numeric minutes; keep originals too
    for col in KPI_COLS:
        if col in df.columns:
            df[col + "_minutes"] = df[col].apply(_parse_kpi_minutes)
            df.drop(columns=[col], inplace=True)

    # 4. Normalise string columns
    obj_cols = df.select_dtypes(include="object").columns
    for col in obj_cols:
        df[col] = df[col].astype(str).str.strip()
        df[col] = df[col].replace({"nan": None, "None": None, "": None})

    # 5. Parse dates
    for col in DATE_COLS:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    # 6. Derived columns
    df["is_resolved"] = (df.get("resolved") is not None and df["resolved"].notna()) | \
                        (df.get("closure_date") is not None and df["closure_date"].notna())

    if "resolved" in df.columns and "closure_date" in df.columns:
        df["is_resolved"] = df["resolved"].notna() | df["closure_date"].notna()
    elif "resolved" in df.columns:
        df["is_resolved"] = df["resolved"].notna()
    elif "closure_date" in df.columns:
        df["is_resolved"] = df["closure_date"].notna()
    else:
        df["is_resolved"] = False

    if "created" in df.columns and "resolved" in df.columns:
        mask = df["resolved"].notna() & df["created"].notna()
        df["resolution_days"] = None
        df.loc[mask, "resolution_days"] = (
            (df.loc[mask, "resolved"] - df.loc[mask, "created"]).dt.total_seconds() / 86400
        )
    else:
        df["resolution_days"] = None

    if "created" in df.columns:
        df["created_yearmonth"] = df["created"].dt.to_period("M").astype(str)
        df["created_year"]      = df["created"].dt.year
        df["created_month"]     = df["created"].dt.month
        df["created_week"]      = df["created"].dt.isocalendar().week.astype(float)

    return df


# ──────────────────────────────────────────────────────────────────────────────
# DB helpers
# ──────────────────────────────────────────────────────────────────────────────



def initial_load(df: pd.DataFrame, engine) -> int:
    """Drop + recreate the issues table with fresh data."""
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS issues"))
        conn.execute(text("""
            CREATE TABLE issues (
                `key`                            VARCHAR(100) NOT NULL,
                issue_type                       VARCHAR(100),
                summary                          TEXT,
                organizations                    VARCHAR(100),
                customer_reference_id            VARCHAR(100),
                environment_type                 VARCHAR(100),
                environment                      VARCHAR(200),
                component                        VARCHAR(200),
                assignee                         VARCHAR(200),
                reporter                         VARCHAR(200),
                priority                         VARCHAR(50),
                current_tier                     VARCHAR(100),
                status                           VARCHAR(100),
                created                          DATETIME,
                reproductibility                 VARCHAR(100),
                resolutions                      VARCHAR(200),
                root_cause_description           TEXT,
                impact_description               TEXT,
                resolution_description           TEXT,
                last_comment_datetime            DATETIME,
                client_priority                  VARCHAR(100),
                target_release                   TEXT,
                closure_date                     DATETIME,
                resolved                         DATETIME,
                count_ready_acceptance           FLOAT,
                count_ready_staging              FLOAT,
                start_date_time                  DATETIME,
                due_date                         DATETIME,
                product_line                     VARCHAR(100),
                occurrences                      FLOAT,
                sending_date                     DATETIME,
                sla_justified                    VARCHAR(10),
                out_of_sla_reason                TEXT,
                story_points                     FLOAT,
                root_cause_origin                VARCHAR(200),
                nombre_uo                        FLOAT,
                service_request_types            VARCHAR(200),
                enhancement_request_type         VARCHAR(200),
                project                          VARCHAR(300),
                qualification_date               DATETIME,
                resolution_owner                 VARCHAR(100),
                fix_versions                     VARCHAR(300),
                expected_sprint                  VARCHAR(200),
                original_expected_sprint         VARCHAR(200),
                baseline_standard_issue          VARCHAR(10),
                kpi_time_to_solve_minutes        FLOAT,
                kpi_time_initial_response_minutes FLOAT,
                kpi_time_to_analyse_minutes      FLOAT,
                kpi_time_to_assist_minutes       FLOAT,
                kpi_time_to_estimate_minutes     FLOAT,
                is_resolved                      TINYINT(1),
                resolution_days                  FLOAT,
                created_yearmonth                VARCHAR(10),
                created_year                     INT,
                created_month                    INT,
                created_week                     INT,
                PRIMARY KEY (`key`)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """))
    df.to_sql("issues", con=engine, if_exists="append", index=False, chunksize=500)
    print(f"[ETL] Loaded {len(df):,} rows into 'issues' (full replace).")
    return len(df)


def upsert(df: pd.DataFrame, engine) -> int:
    """
    Upsert by `key`:
      - Delete rows whose key already exists in DB
      - Append all rows from the new file
    """
    keys = df["key"].dropna().tolist()
    if not keys:
        return 0

    with engine.begin() as conn:
        # Batch deletes to avoid huge IN() clauses
        batch = 500
        for i in range(0, len(keys), batch):
            chunk = keys[i : i + batch]
            placeholders = ",".join([f"'{k}'" for k in chunk])
            conn.execute(text(f"DELETE FROM issues WHERE `key` IN ({placeholders})"))

    df.to_sql("issues", con=engine, if_exists="append", index=False, chunksize=500)
    print(f"[ETL] Upserted {len(df):,} rows.")
    return len(df)


# ──────────────────────────────────────────────────────────────────────────────
# Jira API ETL
# ──────────────────────────────────────────────────────────────────────────────

# Mapping: Jira field id → DB column name
_JIRA_FIELD_MAP = {
    # Standard fields (value extracted from issue["key"] or fields[...])
    "issuetype":          "issue_type",
    "summary":            "summary",
    "assignee":           "assignee",
    "reporter":           "reporter",
    "priority":           "priority",
    "status":             "status",
    "created":            "created",
    "resolutiondate":     "resolved",
    "duedate":            "due_date",
    "fixVersions":        "fix_versions",
    "project":            "project",
    # Custom fields
    "customfield_10002":  "organizations",
    "customfield_10127":  "customer_reference_id",
    "customfield_10187":  "environment_type",
    "customfield_10238":  "environment",
    "customfield_10171":  "component",
    "customfield_10173":  "current_tier",
    "customfield_10242":  "reproductibility",
    "customfield_10301":  "resolutions",
    "customfield_10310":  "root_cause_description",
    "customfield_10312":  "impact_description",
    "customfield_10311":  "resolution_description",
    "customfield_10248":  "last_comment_datetime",
    "customfield_10303":  "client_priority",
    "customfield_10179":  "target_release",
    "customfield_10297":  "closure_date",
    "customfield_10492":  "qualification_date",
    "customfield_10327":  "count_ready_acceptance",
    "customfield_10321":  "count_ready_staging",
    "customfield_10317":  "start_date_time",
    "customfield_10229":  "product_line",
    "customfield_10049":  "story_points",       # numeric SP (non-IRPAUTO projects)
    "customfield_10520":  "story_points_option", # option-based SP (IRPAUTO) — merged below
    "customfield_10369":  "sending_date",
    "customfield_10381":  "occurrences",
    "customfield_10429":  "sla_justified",
    "customfield_10446":  "out_of_sla_reason",
    "customfield_10452":  "root_cause_origin",
    "customfield_10447":  "nombre_uo",
    "customfield_10165":  "service_request_types",
    "customfield_10382":  "enhancement_request_type",
    "customfield_11038":  "resolution_owner",
    "customfield_10315":  "expected_sprint",
    "customfield_10642":  "original_expected_sprint",
    "customfield_10305":  "baseline_standard_issue",
    "customfield_10553":  "project_cf",   # "Project" custom field (some issues)
}


def _adf_to_text(node) -> str:
    """Recursively extract plain text from an Atlassian Document Format node."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        t = node.get("type", "")
        if t == "text":
            return node.get("text", "")
        if t == "hardBreak":
            return "\n"
        children = node.get("content", [])
        sep = "\n" if t in ("paragraph", "bulletList", "orderedList", "listItem", "heading") else ""
        return sep.join(_adf_to_text(c) for c in children)
    if isinstance(node, list):
        return " ".join(_adf_to_text(c) for c in node)
    return str(node)


def _jira_extract(field_id: str, val):
    """Extract a scalar/string value from a Jira field value."""
    if val is None:
        return None

    # Sprint (list of sprint objects)
    if field_id == "customfield_10020":
        if isinstance(val, list) and val:
            return val[-1].get("name")   # latest sprint
        return None

    # Fix versions — join names
    if field_id == "fixVersions":
        if isinstance(val, list):
            return ", ".join(v.get("name", "") for v in val if isinstance(v, dict))
        return None

    # Organizations — list of dicts with "name"
    if field_id == "customfield_10002":
        if isinstance(val, list) and val:
            return val[0].get("name")
        return None

    # Resolutions — list of option dicts with "value"
    if field_id == "customfield_10301":
        if isinstance(val, list) and val:
            return val[0].get("value")
        if isinstance(val, dict):
            return val.get("value") or val.get("name")
        return str(val) if val is not None else None

    # ADF rich-text fields
    if field_id in ("customfield_10310", "customfield_10311", "customfield_10312",
                    "customfield_10179"):
        if isinstance(val, dict) and val.get("type") == "doc":
            return _adf_to_text(val).strip() or None
        return str(val) if val else None

    # Plain dicts — grab name / displayName / value
    if isinstance(val, dict):
        return (val.get("name") or val.get("displayName") or
                val.get("value") or val.get("key"))

    # Lists of dicts — join names
    if isinstance(val, list):
        parts = []
        for item in val:
            if isinstance(item, dict):
                parts.append(str(item.get("name") or item.get("displayName") or item.get("value") or ""))
            else:
                parts.append(str(item))
        return ", ".join(p for p in parts if p) or None

    # Scalar
    return val


def fetch_jira_issues(engine, jira_url: str, email: str, api_token: str,
                      project: str = "IRPAUTO", mode: str = "upsert",
                      updated_since: str = None,
                      progress_cb=None) -> dict:
    """
    Fetch issues from a Jira project via the REST API v3 and load into `issues`.

    updated_since: ISO date string "YYYY-MM-DD" — only fetch issues updated on/after this date.
                   None = fetch everything.
    progress_cb: optional callable(fetched_so_far, total) for UI progress updates.
    mode: "upsert" | "replace"
    Returns {"fetched": N, "loaded": N}
    """
    import requests
    from requests.auth import HTTPBasicAuth

    auth    = HTTPBasicAuth(email, api_token)
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    base    = jira_url.rstrip("/")
    endpoint = f"{base}/rest/api/3/search/jql"

    jql = f"project = {project}"
    if updated_since:
        jql += f' AND updated >= "{updated_since}"'
    jql += " ORDER BY updated ASC"

    # Get approximate total first for accurate progress bar
    total_hint = 0
    try:
        _cr = requests.post(
            f"{base}/rest/api/3/search/approximate-count",
            auth=auth, headers=headers,
            json={"jql": jql}, timeout=15,
        )
        if _cr.ok:
            total_hint = _cr.json().get("count", 0)
    except Exception:
        pass

    # All field IDs we want to request
    requested_fields = list(_JIRA_FIELD_MAP.keys())

    all_rows = []
    next_page_token = None
    page_size = 100

    while True:
        payload = {
            "jql":        jql,
            "maxResults": page_size,
            "fields":     requested_fields,
        }
        if next_page_token:
            payload["nextPageToken"] = next_page_token

        resp = requests.post(endpoint, auth=auth, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        for issue in data.get("issues", []):
            row = {"key": issue["key"]}
            fields = issue.get("fields", {})
            for jira_fid, db_col in _JIRA_FIELD_MAP.items():
                if db_col in row:           # skip duplicate db_col (e.g. project_cf)
                    continue
                row[db_col] = _jira_extract(jira_fid, fields.get(jira_fid))
            all_rows.append(row)

        if progress_cb:
            progress_cb(len(all_rows), total_hint or len(all_rows))

        if data.get("isLast", True):
            break
        next_page_token = data.get("nextPageToken")
        if not next_page_token:
            break

    if not all_rows:
        return {"fetched": 0, "loaded": 0}

    df = pd.DataFrame(all_rows)

    # Apply the same cleaning pipeline as clean_data()
    # 1. String columns first (strip whitespace / None normalization)
    obj_cols = df.select_dtypes(include="object").columns
    for col in obj_cols:
        df[col] = df[col].astype(str).str.strip().replace({"nan": None, "None": None, "": None})

    def _to_dt(series):
        """Parse a series to tz-naive datetime, handling ISO strings with offsets."""
        return pd.to_datetime(series, errors="coerce", utc=True).dt.tz_convert(None)

    # 2. Parse ALL date columns to datetime (must come after string cleaning)
    for col in DATE_COLS:
        if col in df.columns:
            df[col] = _to_dt(df[col])

    # KPI columns — Jira API returns SLA objects, not "Xh Ym" strings; set to None
    for kpi in KPI_COLS:
        if kpi not in df.columns:
            df[kpi] = None
        df[kpi + "_minutes"] = None
        df.drop(columns=[kpi], inplace=True, errors="ignore")

    # Numeric
    for col in ("story_points", "occurrences", "nombre_uo",
                "count_ready_acceptance", "count_ready_staging"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Merge option-based SP (customfield_10520) into story_points where still null
    if "story_points_option" in df.columns:
        _sp_opt = pd.to_numeric(df["story_points_option"], errors="coerce")
        if "story_points" not in df.columns:
            df["story_points"] = _sp_opt
        else:
            df["story_points"] = df["story_points"].fillna(_sp_opt)
        df.drop(columns=["story_points_option"], inplace=True)

    # Derived columns (same as clean_data)
    if "resolved" in df.columns and "closure_date" in df.columns:
        df["is_resolved"] = df["resolved"].notna() | df["closure_date"].notna()
    elif "resolved" in df.columns:
        df["is_resolved"] = df["resolved"].notna()
    else:
        df["is_resolved"] = False

    if "created" in df.columns and "resolved" in df.columns:
        mask = df["resolved"].notna() & df["created"].notna()
        df["resolution_days"] = None
        df.loc[mask, "resolution_days"] = (
            (df.loc[mask, "resolved"] - df.loc[mask, "created"]).dt.total_seconds() / 86400
        )
    else:
        df["resolution_days"] = None

    if "created" in df.columns:
        df["created_yearmonth"] = df["created"].dt.to_period("M").astype(str)
        df["created_year"]      = df["created"].dt.year
        df["created_month"]     = df["created"].dt.month
        df["created_week"]      = df["created"].dt.isocalendar().week.astype(float)

    # Drop entirely-null columns
    df.dropna(axis=1, how="all", inplace=True)

    # Deduplicate keys (keep last)
    df = df.drop_duplicates(subset=["key"], keep="last")

    from sqlalchemy import inspect as _inspect
    if mode == "replace" or not _inspect(engine).has_table("issues"):
        n = initial_load(df, engine)
    else:
        n = upsert(df, engine)

    print(f"[ETL] Jira fetch complete: {len(all_rows)} issues fetched, {n} loaded into DB.")
    return {"fetched": len(all_rows), "loaded": n}


# ──────────────────────────────────────────────────────────────────────────────
# Release Lifecycle ETL (Scope UPDATE + Team availibility sheets)
# ──────────────────────────────────────────────────────────────────────────────

def load_release_lifecycle(file_bytes, engine) -> dict:
    """
    Parse Release_lifecycle_R25.xlsx (from bytes) and load into:
      - r25_scope       (key, scope_sprint, scope_points, scope_status,
                         jira_sprint, committed)
      - r25_team_avail  (squad, name, cap_prod)
      - r25_sprint_meta (sprint_name, duration_days, sprint_start, sprint_end,
                         cap_planifiee, velocite_reele, sp_vs_jh)
    Returns a summary dict.
    """
    import io as _io

    buf = _io.BytesIO(file_bytes) if not isinstance(file_bytes, _io.BytesIO) else file_bytes

    # ── Sheet 1: Scope UPDATE ─────────────────────────────────────────────────
    raw_scope = pd.read_excel(buf, sheet_name="Scope UPDATE", header=0)
    raw_scope.columns = [str(c).strip() for c in raw_scope.columns]

    # The last two columns (AP=SUB Component, AQ=assignee) hold the
    # authoritative assignee→squad mapping. Extract ALL rows BEFORE key
    # filtering, because team-roster rows often have no ticket Key.
    _last_col = raw_scope.columns[-1]   # 'assignee'  (col AQ)

    _aq = raw_scope[["Squad", _last_col]].copy()
    _aq.columns = ["squad", "assignee_name"]
    _aq["assignee_name"] = _aq["assignee_name"].astype(str).str.strip().replace({"nan": None, "": None})
    _aq["squad"]         = _aq["squad"].astype(str).str.strip().replace({"nan": None, "": None})
    assignee_squad = (
        _aq.dropna(subset=["assignee_name", "squad"])
        .drop_duplicates(subset=["assignee_name"])
        .reset_index(drop=True)
    )

    scope = raw_scope[["Key", "Squad", "expected sprint", "Story point", "statut",
                        "expected sprint Jira", "Committed (Yes/No)"]].copy()
    scope.columns = ["key", "squad", "scope_sprint", "scope_points",
                     "scope_status", "jira_sprint", "committed"]
    scope["key"] = scope["key"].astype(str).str.strip()
    scope = scope[
        scope["key"].notna() & (scope["key"] != "nan") & (scope["key"] != "")
    ].copy()
    scope["scope_points"] = pd.to_numeric(scope["scope_points"], errors="coerce")
    for col in ["squad", "scope_sprint", "scope_status", "jira_sprint", "committed"]:
        scope[col] = scope[col].astype(str).str.strip().replace({"nan": None, "": None})

    # ── Sheet 2: Team availibility ─────────────────────────────────────────────
    buf.seek(0)
    raw_team = pd.read_excel(buf, sheet_name="Team availibility", header=None)

    # Sprint metadata from fixed cells
    sprint_duration = float(raw_team.iloc[0, 13]) if pd.notna(raw_team.iloc[0, 13]) else 15.0
    cap_planifiee   = float(raw_team.iloc[0, 19]) if pd.notna(raw_team.iloc[0, 19]) else None
    velocite_reele  = float(raw_team.iloc[1, 19]) if pd.notna(raw_team.iloc[1, 19]) else None
    sp_vs_jh        = float(raw_team.iloc[23, 13]) if pd.notna(raw_team.iloc[23, 13]) else None

    import datetime as _dt

    def _parse_xl_date(v):
        """Parse a cell value that may be a datetime object, Excel serial number, or date string."""
        if v is None or (isinstance(v, float) and pd.isna(v)):
            raise ValueError(f"Empty date cell: {v!r}")
        if isinstance(v, (_dt.datetime, _dt.date)):
            return pd.Timestamp(v)
        if isinstance(v, (int, float)):
            # Excel date serial (Windows epoch 1899-12-30)
            return pd.Timestamp("1899-12-30") + pd.Timedelta(days=int(v))
        # String: try dayfirst then monthfirst
        s = str(v).strip()
        for _df in (True, False):
            try:
                return pd.to_datetime(s, dayfirst=_df)
            except Exception:
                continue
        raise ValueError(f"Cannot parse date: {v!r}")

    try:
        _raw_start = raw_team.iloc[0, 16]
        _raw_end   = raw_team.iloc[1, 16]
        print(f"[ETL] Sprint date cells: start={_raw_start!r} ({type(_raw_start).__name__}), "
              f"end={_raw_end!r} ({type(_raw_end).__name__})")
        start_dt = _parse_xl_date(_raw_start)
        end_dt   = _parse_xl_date(_raw_end)
        # Guard against day/month swap (e.g. 08/03 read as August 3 instead of March 8)
        if start_dt > end_dt:
            start_dt = pd.Timestamp(start_dt.year, start_dt.day, start_dt.month)
        sprint_start = start_dt.date()
        sprint_end   = end_dt.date()
        print(f"[ETL] Parsed sprint: {sprint_start} → {sprint_end} "
              f"({(sprint_end - sprint_start).days + 1} days)")
    except Exception as _ex:
        print(f"[ETL] WARNING: Sprint date parse failed ({_ex}), using fallback dates")
        sprint_start = _dt.date(2026, 3, 8)
        sprint_end   = _dt.date(2026, 4, 4)

    team = raw_team.iloc[1:22, [0, 1, 4, 6, 7]].copy()
    team.columns = ["squad", "name", "transverse", "contingence", "cap_prod"]
    team = team[team["name"].notna() & (team["name"].astype(str).str.strip() != "nan")].copy()
    team["name"]       = team["name"].astype(str).str.strip()
    team["squad"]      = team["squad"].astype(str).str.strip().replace({"nan": "—"})
    team["cap_prod"]   = pd.to_numeric(team["cap_prod"], errors="coerce").fillna(0)
    team["transverse"] = pd.to_numeric(team["transverse"], errors="coerce").fillna(0)
    team["contingence"]= pd.to_numeric(team["contingence"], errors="coerce").fillna(0)
    team = team[["squad", "name", "cap_prod", "transverse"]].reset_index(drop=True)

    sprint_meta = pd.DataFrame([{
        "sprint_name":    "R25",
        "duration_days":  sprint_duration,
        "sprint_start":   sprint_start,
        "sprint_end":     sprint_end,
        "cap_planifiee":  cap_planifiee,
        "velocite_reele": velocite_reele,
        "sp_vs_jh":       sp_vs_jh,
    }])

    # ── Write to DB ────────────────────────────────────────────────────────────
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS r25_assignee_squad"))
        conn.execute(text("""
            CREATE TABLE r25_assignee_squad (
                assignee_name  VARCHAR(200) NOT NULL,
                squad          VARCHAR(100),
                PRIMARY KEY (assignee_name)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """))

        conn.execute(text("DROP TABLE IF EXISTS r25_scope"))
        conn.execute(text("""
            CREATE TABLE r25_scope (
                `key`           VARCHAR(100) NOT NULL,
                squad           VARCHAR(100),
                scope_sprint    VARCHAR(200),
                scope_points    FLOAT,
                scope_status    VARCHAR(100),
                jira_sprint     VARCHAR(200),
                committed       VARCHAR(20),
                PRIMARY KEY (`key`)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """))

        conn.execute(text("DROP TABLE IF EXISTS r25_team_avail"))
        conn.execute(text("""
            CREATE TABLE r25_team_avail (
                id         INT NOT NULL AUTO_INCREMENT,
                squad      VARCHAR(100),
                name       VARCHAR(200),
                cap_prod   FLOAT,
                transverse FLOAT,
                PRIMARY KEY (id)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """))

        conn.execute(text("DROP TABLE IF EXISTS r25_sprint_meta"))
        conn.execute(text("""
            CREATE TABLE r25_sprint_meta (
                sprint_name    VARCHAR(50) NOT NULL,
                duration_days  FLOAT,
                sprint_start   DATE,
                sprint_end     DATE,
                cap_planifiee  FLOAT,
                velocite_reele FLOAT,
                sp_vs_jh       FLOAT,
                PRIMARY KEY (sprint_name)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """))

    assignee_squad.to_sql("r25_assignee_squad", con=engine, if_exists="append", index=False)
    scope.to_sql("r25_scope",      con=engine, if_exists="append", index=False)
    team.to_sql("r25_team_avail",  con=engine, if_exists="append", index=False)
    sprint_meta.to_sql("r25_sprint_meta", con=engine, if_exists="append", index=False)

    print(f"[ETL] r25_scope: {len(scope)} rows | r25_team_avail: {len(team)} rows | "
          f"r25_assignee_squad: {len(assignee_squad)} rows")
    return {"scope_rows": len(scope), "team_rows": len(team)}


# ──────────────────────────────────────────────────────────────────────────────
# Burndown materialisation — pre-compute daily series into DB tables
# ──────────────────────────────────────────────────────────────────────────────

def materialise_r25_burndown(engine, sprint_start=None, sprint_end=None) -> int:
    """
    Compute the R25 sprint burndown (scope-based) and write to `r25_burndown`.

    Columns: date, total_pts, remaining_pts, resolved_pts, ideal_pts, pct_complete

    sprint_start / sprint_end: datetime.date objects; read from r25_sprint_meta if omitted.
    Returns number of rows written.
    """
    import datetime as _dt

    # ── Load scope keys & points ───────────────────────────────────────────────
    scope = pd.read_sql("SELECT `key`, scope_points FROM r25_scope", con=engine)
    keys  = scope["key"].tolist()

    issues = pd.read_sql(
        "SELECT `key`, status, story_points, qualification_date, resolved, closure_date "
        "FROM issues",
        con=engine,
    )
    issues = issues[issues["key"].isin(keys)].copy()

    # Effective points: DB first, scope fallback
    merged = scope.merge(issues, on="key", how="left")
    merged["_pts"] = (
        pd.to_numeric(merged["story_points"], errors="coerce")
        .fillna(pd.to_numeric(merged["scope_points"], errors="coerce"))
        .fillna(0)
    )

    _date_cols_e = [c for c in ["qualification_date", "resolved", "closure_date"] if c in merged.columns]

    # Sprint window — from meta table or arguments
    if sprint_start is None or sprint_end is None:
        meta = pd.read_sql("SELECT * FROM r25_sprint_meta WHERE sprint_name='R25'", con=engine)
        if meta.empty:
            raise ValueError("r25_sprint_meta has no R25 row — upload Release Lifecycle first.")
        sprint_start = pd.Timestamp(meta.iloc[0]["sprint_start"]).date()
        sprint_end   = pd.Timestamp(meta.iloc[0]["sprint_end"]).date()

    # A ticket counts only if: status ∈ DELIVERED_STATUSES AND earliest date within sprint.
    _DELIVERED_STATUSES = {
        "closed", "qualification test", "ready for staging",
        "ready for exceptions", "ready for qa", "ready for sprint",
        "cancelled", "canceled", "on hold", "plan investigation", "work approved",
        "ready for acceptance", "waiting for customer",
    }
    _sp_s = pd.Timestamp(sprint_start)
    _sp_e = pd.Timestamp(sprint_end) + pd.Timedelta(hours=23, minutes=59)
    _is_done = merged["status"].str.lower().str.strip().isin(_DELIVERED_STATUSES) \
               if "status" in merged.columns \
               else pd.Series(False, index=merged.index)
    # Per date column: keep only if within sprint
    for _dc in _date_cols_e:
        _ts = pd.to_datetime(merged[_dc], errors="coerce")
        merged[_dc + "_ts"]  = _ts          # raw parsed
        merged[_dc + "_in"]  = _ts.where(_ts.notna() & (_ts >= _sp_s) & (_ts <= _sp_e))

    # Earliest date within sprint across all three columns
    merged["_resolved_at"] = pd.concat(
        [merged[_dc + "_in"] for _dc in _date_cols_e], axis=1
    ).min(axis=1)

    # Earliest raw date (any, inside or outside sprint) — used to classify exclusions
    merged["_any_date"] = pd.concat(
        [merged[_dc + "_ts"] for _dc in _date_cols_e], axis=1
    ).min(axis=1)

    # Final gate: delivered status AND date within sprint → only these count in burndown
    merged["_resolved_at"] = merged["_resolved_at"].where(_is_done, pd.NaT)

    # NO_DATE tickets: delivered but all dates null → place at last day of sprint
    _no_date_mask = _is_done & merged["_resolved_at"].isna() & merged["_any_date"].isna()
    merged.loc[_no_date_mask, "_resolved_at"] = _sp_e

    # ── Build exclusion table (DATE_OUTSIDE_SPRINT only) ──────────────────────
    _excluded = merged[_is_done & merged["_resolved_at"].isna()].copy()
    _excluded["exclusion_reason"] = "DATE_OUTSIDE_SPRINT"
    _excl_out = _excluded[
        ["key"] + [c for c in ["status", "story_points", "assignee"] if c in _excluded.columns] +
        [_dc + "_ts" for _dc in _date_cols_e] + ["exclusion_reason"]
    ].rename(columns={_dc + "_ts": _dc for _dc in _date_cols_e}).copy()
    _excl_out.columns = [c.replace("_ts", "") for c in _excl_out.columns]

    days         = pd.date_range(sprint_start, sprint_end, freq="D")
    total_pts    = float(merged["_pts"].sum())
    total_tickets = len(merged)
    n_days       = len(days)
    rows = []
    for i, day in enumerate(days):
        day_ts = pd.Timestamp(day) + pd.Timedelta(hours=23, minutes=59)
        done_mask = merged["_resolved_at"].notna() & (merged["_resolved_at"] <= day_ts)
        resolved_pts     = float(merged[done_mask]["_pts"].sum())
        resolved_tickets = int(done_mask.sum())
        ideal_pts     = round(total_pts    * (1 - i / (n_days - 1)), 4) if n_days > 1 else 0.0
        ideal_tickets = round(total_tickets * (1 - i / (n_days - 1)), 4) if n_days > 1 else 0.0
        rows.append({
            "date":              day.date(),
            "total_pts":         round(total_pts, 2),
            "resolved_pts":      round(resolved_pts, 2),
            "remaining_pts":     round(total_pts - resolved_pts, 2),
            "ideal_pts":         ideal_pts,
            "pct_complete":      round(resolved_pts / total_pts * 100, 2) if total_pts else 0.0,
            "total_tickets":     total_tickets,
            "resolved_tickets":  resolved_tickets,
            "remaining_tickets": total_tickets - resolved_tickets,
            "ideal_tickets":     ideal_tickets,
            "pct_complete_tickets": round(resolved_tickets / total_tickets * 100, 2) if total_tickets else 0.0,
        })

    df_out = pd.DataFrame(rows)

    # Tag committed rows and store as scope_type="Committed"
    df_out["scope_type"] = "Committed"

    # ── Write unified burndown table (append Committed rows; Full Team added from app) ──
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS r25_burndown"))
        conn.execute(text("""
            CREATE TABLE r25_burndown (
                `date`                DATE        NOT NULL,
                scope_type            VARCHAR(20) NOT NULL,
                total_pts             FLOAT,
                resolved_pts          FLOAT,
                remaining_pts         FLOAT,
                ideal_pts             FLOAT,
                pct_complete          FLOAT,
                total_tickets         INT,
                resolved_tickets      INT,
                remaining_tickets     INT,
                ideal_tickets         FLOAT,
                pct_complete_tickets  FLOAT,
                PRIMARY KEY (`date`, scope_type)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """))
        conn.execute(text("DROP TABLE IF EXISTS r25_sprint_tickets"))
        conn.execute(text("""
            CREATE TABLE r25_sprint_tickets (
                `key`               VARCHAR(30)  NOT NULL,
                summary             TEXT,
                assignee            VARCHAR(120),
                squad               VARCHAR(120),
                status              VARCHAR(80),
                story_points        FLOAT,
                in_scope            TINYINT(1),
                is_delivered        TINYINT(1),
                completed_at        DATETIME,
                qualification_date  DATETIME,
                resolved            DATETIME,
                closure_date        DATETIME,
                PRIMARY KEY (`key`)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """))
    df_out.to_sql("r25_burndown", con=engine, if_exists="append", index=False)

    print(f"[ETL] r25_burndown (Committed): {len(df_out)} rows ({sprint_start} -> {sprint_end})")
    print(f"[ETL] burndown excluded (logged in r25_team_tickets.exclusion_reason): {len(_excl_out)} tickets "
          f"({(_excl_out['exclusion_reason']=='NO_DATE').sum()} no date, "
          f"{(_excl_out['exclusion_reason']=='DATE_OUTSIDE_SPRINT').sum()} outside sprint)")
    return len(df_out)


def append_r25_full_burndown(engine, burn_df, tickets_df) -> dict:
    """
    Append 'Full Team' scope_type rows to r25_burndown and write r25_sprint_tickets.
    Call materialise_r25_burndown first (it creates the tables and writes Committed rows).

    burn_df    : daily burndown rows — must already have scope_type='Full Team'
    tickets_df : one row per ticket in the full pool
    """
    burn_df.to_sql("r25_burndown",      con=engine, if_exists="append", index=False)
    tickets_df.to_sql("r25_sprint_tickets", con=engine, if_exists="append", index=False)
    print(f"[ETL] r25_burndown (Full Team): {len(burn_df)} rows")
    print(f"[ETL] r25_sprint_tickets: {len(tickets_df)} rows")
    return {"burndown_rows": len(burn_df), "ticket_rows": len(tickets_df)}


def materialise_backlog_burndown(engine,
                                  track_from=None,
                                  track_to=None,
                                  target: int = 261) -> int:
    """
    Compute the prod-incident backlog burndown and write to `backlog_burndown`.

    Columns: date, remaining, opened, closed, net, target, ideal_remaining

    track_from / track_to: datetime.date; defaults to 2026-01-01 → 2026-04-30.
    Returns number of rows written.
    """
    import datetime as _dt

    if track_from is None:
        track_from = _dt.date(2026, 1, 1)
    if track_to is None:
        track_to = _dt.date(2026, 4, 30)

    issues = pd.read_sql(
        "SELECT `key`, status, created, closure_date, resolved "
        "FROM issues "
        "WHERE issue_type='Incident' AND environment_type='Production'",
        con=engine,
    )
    issues["created"] = pd.to_datetime(issues["created"], errors="coerce")

    closed_statuses = {"Closed", "Cancelled"}
    issues["_is_closed"] = issues["status"].isin(closed_statuses)
    issues["_resolved_at"] = pd.NaT
    for col in ["closure_date", "resolved"]:
        if col in issues.columns:
            issues["_resolved_at"] = issues["_resolved_at"].fillna(
                pd.to_datetime(issues[col], errors="coerce")
            )

    days    = pd.date_range(track_from, track_to, freq="D")
    n_days  = len(days)
    # baseline = open tickets at start of window
    start_ts = pd.Timestamp(track_from)
    end_ts   = pd.Timestamp(track_to) + pd.Timedelta(hours=23, minutes=59)

    baseline_open = len(issues[
        (issues["created"] < start_ts) &
        (~issues["_is_closed"] | (issues["_resolved_at"] >= start_ts))
    ])

    rows = []
    for i, day in enumerate(days):
        d_end = pd.Timestamp(day) + pd.Timedelta(hours=23, minutes=59)
        remaining = len(issues[
            (issues["created"] <= d_end) &
            (~issues["_is_closed"] | (issues["_resolved_at"] > d_end))
        ])
        opened = len(issues[
            (issues["created"] >= pd.Timestamp(day)) &
            (issues["created"] <= d_end)
        ])
        closed = len(issues[
            issues["_resolved_at"].notna() &
            (issues["_resolved_at"] >= pd.Timestamp(day)) &
            (issues["_resolved_at"] <= d_end)
        ])
        ideal = round(
            baseline_open - (baseline_open - target) * (i / (n_days - 1)), 2
        ) if n_days > 1 else float(target)

        rows.append({
            "date":            day.date(),
            "remaining":       remaining,
            "opened":          opened,
            "closed":          closed,
            "net":             closed - opened,
            "target":          target,
            "ideal_remaining": ideal,
        })

    df_out = pd.DataFrame(rows)

    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS backlog_burndown"))
        conn.execute(text("""
            CREATE TABLE backlog_burndown (
                `date`           DATE NOT NULL,
                remaining        INT,
                opened           INT,
                closed           INT,
                net              INT,
                target           INT,
                ideal_remaining  FLOAT,
                PRIMARY KEY (`date`)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """))
    df_out.to_sql("backlog_burndown", con=engine, if_exists="append", index=False)
    print(f"[ETL] backlog_burndown: {len(df_out)} rows (target={target})")
    return len(df_out)


def materialise_r25_team_commitment(
    engine,
    assignee_df: pd.DataFrame,
    squad_df: pd.DataFrame,
    tickets_df: pd.DataFrame,
) -> dict:
    """
    Persist team commitment data to three DB tables:

      r25_team_assignee  — one row per team member with commitment metrics
      r25_team_squad     — one row per squad with aggregated metrics
      r25_team_tickets   — one row per scope ticket with delivery classification

    Parameters
    ----------
    assignee_df : DataFrame with columns:
        display_name, jira_name, squad,
        engaged_tickets, engaged_sp,
        delivered_tickets, delivered_sp,
        not_delivered_tickets, not_delivered_sp,
        commitment_pct
    squad_df : DataFrame with columns:
        squad, members,
        engaged_tickets, engaged_sp,
        delivered_tickets, delivered_sp,
        not_delivered_tickets, not_delivered_sp,
        commitment_pct
    tickets_df : DataFrame with columns:
        key, summary, status, assignee, display_name, squad,
        story_points (_pts), issue_type, priority,
        is_delivered, is_not_delivered

    Returns dict with row counts per table.
    """
    with engine.begin() as conn:
        # ── r25_team_assignee ─────────────────────────────────────────────────
        conn.execute(text("DROP TABLE IF EXISTS r25_team_assignee"))
        conn.execute(text("""
            CREATE TABLE r25_team_assignee (
                display_name         VARCHAR(120) NOT NULL,
                squad                VARCHAR(120),
                engaged_tickets      INT,
                engaged_sp           FLOAT,
                delivered_tickets    INT,
                delivered_sp         FLOAT,
                not_delivered_tickets INT,
                not_delivered_sp     FLOAT,
                commitment_pct       FLOAT,
                commitment_sp_pct    FLOAT,
                PRIMARY KEY (display_name)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """))

        # ── r25_team_squad ────────────────────────────────────────────────────
        conn.execute(text("DROP TABLE IF EXISTS r25_team_squad"))
        conn.execute(text("""
            CREATE TABLE r25_team_squad (
                squad                VARCHAR(120) NOT NULL,
                members              INT,
                engaged_tickets      INT,
                engaged_sp           FLOAT,
                delivered_tickets    INT,
                delivered_sp         FLOAT,
                not_delivered_tickets INT,
                not_delivered_sp     FLOAT,
                commitment_pct       FLOAT,
                commitment_sp_pct    FLOAT,
                PRIMARY KEY (squad)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """))

        # ── r25_team_tickets ──────────────────────────────────────────────────
        conn.execute(text("DROP TABLE IF EXISTS r25_team_tickets"))
        conn.execute(text("""
            CREATE TABLE r25_team_tickets (
                `key`               VARCHAR(30)  NOT NULL,
                summary             TEXT,
                status              VARCHAR(80),
                assignee            VARCHAR(120),
                display_name        VARCHAR(120),
                squad               VARCHAR(120),
                story_points        FLOAT,
                issue_type          VARCHAR(80),
                priority            VARCHAR(40),
                is_delivered        TINYINT(1),
                is_not_delivered    TINYINT(1),
                qualification_date  DATETIME,
                resolved            DATETIME,
                closure_date        DATETIME,
                exclusion_reason    VARCHAR(30),
                PRIMARY KEY (`key`)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """))

    assignee_df.to_sql("r25_team_assignee", con=engine, if_exists="append", index=False)
    squad_df.to_sql("r25_team_squad",    con=engine, if_exists="append", index=False)
    tickets_df.to_sql("r25_team_tickets", con=engine, if_exists="append", index=False)

    counts = {
        "r25_team_assignee": len(assignee_df),
        "r25_team_squad":    len(squad_df),
        "r25_team_tickets":  len(tickets_df),
    }
    print(f"[ETL] team commitment: {counts}")
    return counts


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

def run_etl(file_path: str, mode: str = "replace") -> pd.DataFrame:
    """
    mode: 'replace' (initial full load) | 'upsert' (incremental update)
    """
    print(f"[ETL] Reading {file_path} ...")
    df_raw = pd.read_excel(file_path, sheet_name=0)
    print(f"[ETL] Raw shape: {df_raw.shape}")

    df = clean_data(df_raw)
    print(f"[ETL] Cleaned shape: {df.shape}")

    engine = get_engine()
    if mode == "replace":
        initial_load(df, engine)
    else:
        upsert(df, engine)

    return df


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "data/Extract.xlsx"
    mode = sys.argv[2] if len(sys.argv) > 2 else "replace"
    run_etl(path, mode)
