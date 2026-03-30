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
                target_release                   VARCHAR(100),
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
    scope = raw_scope[["Key", "expected sprint", "Story point", "statut",
                        "expected sprint Jira", "Committed (Yes/No)"]].copy()
    scope.columns = ["key", "scope_sprint", "scope_points",
                     "scope_status", "jira_sprint", "committed"]
    scope["key"] = scope["key"].astype(str).str.strip()
    scope = scope[
        scope["key"].notna() & (scope["key"] != "nan") & (scope["key"] != "")
    ].copy()
    scope["scope_points"] = pd.to_numeric(scope["scope_points"], errors="coerce")
    for col in ["scope_sprint", "scope_status", "jira_sprint", "committed"]:
        scope[col] = scope[col].astype(str).str.strip().replace({"nan": None, "": None})

    # ── Sheet 2: Team availibility ─────────────────────────────────────────────
    buf.seek(0)
    raw_team = pd.read_excel(buf, sheet_name="Team availibility", header=None)

    # Sprint metadata from fixed cells
    sprint_duration = float(raw_team.iloc[0, 13]) if pd.notna(raw_team.iloc[0, 13]) else 15.0
    cap_planifiee   = float(raw_team.iloc[0, 19]) if pd.notna(raw_team.iloc[0, 19]) else None
    velocite_reele  = float(raw_team.iloc[1, 19]) if pd.notna(raw_team.iloc[1, 19]) else None
    sp_vs_jh        = float(raw_team.iloc[23, 13]) if pd.notna(raw_team.iloc[23, 13]) else None

    try:
        start_dt = pd.to_datetime(raw_team.iloc[0, 16])
        end_dt   = pd.to_datetime(str(raw_team.iloc[1, 16]), dayfirst=True)
        if start_dt > end_dt:
            start_dt = pd.Timestamp(start_dt.year, start_dt.day, start_dt.month)
        sprint_start = start_dt.date()
        sprint_end   = end_dt.date()
    except Exception:
        import datetime as _dt
        sprint_start = _dt.date(2026, 3, 8)
        sprint_end   = _dt.date(2026, 3, 27)

    team = raw_team.iloc[1:22, [0, 1, 6, 7]].copy()
    team.columns = ["squad", "name", "contingence", "cap_prod"]
    team = team[team["name"].notna() & (team["name"].astype(str).str.strip() != "nan")].copy()
    team["name"]       = team["name"].astype(str).str.strip()
    team["squad"]      = team["squad"].astype(str).str.strip().replace({"nan": "—"})
    team["cap_prod"]   = pd.to_numeric(team["cap_prod"], errors="coerce").fillna(0)
    team["contingence"]= pd.to_numeric(team["contingence"], errors="coerce").fillna(0)
    team = team[["squad", "name", "cap_prod"]].reset_index(drop=True)

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
        conn.execute(text("DROP TABLE IF EXISTS r25_scope"))
        conn.execute(text("""
            CREATE TABLE r25_scope (
                `key`         VARCHAR(100) NOT NULL,
                scope_sprint  VARCHAR(200),
                scope_points  FLOAT,
                scope_status  VARCHAR(100),
                jira_sprint   VARCHAR(200),
                committed     VARCHAR(20),
                PRIMARY KEY (`key`)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """))

        conn.execute(text("DROP TABLE IF EXISTS r25_team_avail"))
        conn.execute(text("""
            CREATE TABLE r25_team_avail (
                id       INT NOT NULL AUTO_INCREMENT,
                squad    VARCHAR(100),
                name     VARCHAR(200),
                cap_prod FLOAT,
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

    scope.to_sql("r25_scope",      con=engine, if_exists="append", index=False)
    team.to_sql("r25_team_avail",  con=engine, if_exists="append", index=False)
    sprint_meta.to_sql("r25_sprint_meta", con=engine, if_exists="append", index=False)

    print(f"[ETL] r25_scope: {len(scope)} rows | r25_team_avail: {len(team)} rows")
    return {"scope_rows": len(scope), "team_rows": len(team)}


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
