"""
Data cleaning, column mapping, and DB load helpers for Extract.xlsx files.
"""
import re
import pandas as pd
from sqlalchemy import text

# ── Column mapping: Extract Excel → DB column name ───────────────────────────
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


def _parse_kpi_minutes(val) -> float | None:
    """Convert KPI strings like '998h 31m' or '-2,891h 24m' to total minutes."""
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
    available = {k: v for k, v in COLUMNS_MAP.items() if k in df.columns}
    df = df[list(available.keys())].rename(columns=available).copy()

    if "key" in df.columns:
        df["key"] = df["key"].astype(str).str.strip()
        df = df[df["key"].notna() & (df["key"] != "") & (df["key"] != "nan")].copy()
        df = df.drop_duplicates(subset=["key"], keep="last")

    df.dropna(axis=1, how="all", inplace=True)

    for col in KPI_COLS:
        if col in df.columns:
            df[col + "_minutes"] = df[col].apply(_parse_kpi_minutes)
            df.drop(columns=[col], inplace=True)

    obj_cols = df.select_dtypes(include="object").columns
    for col in obj_cols:
        df[col] = df[col].astype(str).str.strip()
        df[col] = df[col].replace({"nan": None, "None": None, "": None})

    for col in DATE_COLS:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

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


def initial_load(df: pd.DataFrame, engine) -> int:
    """Drop + recreate the issues table with fresh data."""
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS issues"))
        conn.execute(text("""
            CREATE TABLE issues (
                `key`                            VARCHAR(100) NOT NULL,
                issue_type                       VARCHAR(200),
                summary                          TEXT,
                organizations                    VARCHAR(200),
                customer_reference_id            VARCHAR(500),
                environment_type                 VARCHAR(200),
                environment                      VARCHAR(500),
                component                        VARCHAR(500),
                assignee                         VARCHAR(500),
                reporter                         VARCHAR(500),
                priority                         VARCHAR(100),
                current_tier                     VARCHAR(200),
                status                           VARCHAR(200),
                created                          DATETIME,
                reproductibility                 VARCHAR(200),
                resolutions                      VARCHAR(500),
                root_cause_description           TEXT,
                impact_description               TEXT,
                resolution_description           TEXT,
                last_comment_datetime            DATETIME,
                client_priority                  VARCHAR(200),
                target_release                   TEXT,
                closure_date                     DATETIME,
                resolved                         DATETIME,
                count_ready_acceptance           FLOAT,
                count_ready_staging              FLOAT,
                start_date_time                  DATETIME,
                due_date                         DATETIME,
                product_line                     VARCHAR(200),
                occurrences                      FLOAT,
                sending_date                     DATETIME,
                sla_justified                    VARCHAR(20),
                out_of_sla_reason                TEXT,
                story_points                     FLOAT,
                root_cause_origin                VARCHAR(500),
                nombre_uo                        FLOAT,
                service_request_types            VARCHAR(500),
                enhancement_request_type         VARCHAR(500),
                project                          VARCHAR(500),
                qualification_date               DATETIME,
                resolution_owner                 VARCHAR(200),
                fix_versions                     VARCHAR(500),
                expected_sprint                  VARCHAR(500),
                original_expected_sprint         VARCHAR(500),
                baseline_standard_issue          VARCHAR(20),
                project_cf                       VARCHAR(500),
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
    """Delete existing keys then append — effectively upsert by key."""
    keys = df["key"].dropna().tolist()
    if not keys:
        return 0
    with engine.begin() as conn:
        batch = 500
        for i in range(0, len(keys), batch):
            chunk = keys[i: i + batch]
            placeholders = ",".join([f"'{k}'" for k in chunk])
            conn.execute(text(f"DELETE FROM issues WHERE `key` IN ({placeholders})"))
    df.to_sql("issues", con=engine, if_exists="append", index=False, chunksize=500)
    print(f"[ETL] Upserted {len(df):,} rows.")
    return len(df)
