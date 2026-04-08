"""
Release Lifecycle ETL — parse Release_lifecycle_R25.xlsx and load into DB.
"""
import io as _io
import datetime as _dt

import pandas as pd
from sqlalchemy import text


def _parse_xl_date(v):
    """Parse a cell value that may be a datetime, Excel serial, or date string."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        raise ValueError(f"Empty date cell: {v!r}")
    if isinstance(v, (_dt.datetime, _dt.date)):
        return pd.Timestamp(v)
    if isinstance(v, (int, float)):
        # Excel date serial (Windows epoch 1899-12-30)
        return pd.Timestamp("1899-12-30") + pd.Timedelta(days=int(v))
    s = str(v).strip()
    for dayfirst in (True, False):
        try:
            return pd.to_datetime(s, dayfirst=dayfirst)
        except Exception:
            continue
    raise ValueError(f"Cannot parse date: {v!r}")


def load_release_lifecycle(file_bytes, engine) -> dict:
    """
    Parse Release_lifecycle_R25.xlsx (from bytes) and load into:
      - r25_scope          (key, squad, scope_sprint, scope_points,
                            scope_status, jira_sprint, committed)
      - r25_team_avail     (squad, name, cap_prod, transverse)
      - r25_sprint_meta    (sprint_name, duration_days, sprint_start, sprint_end,
                            cap_planifiee, velocite_reele, sp_vs_jh)
      - r25_assignee_squad (assignee_name, squad)

    Returns a summary dict with row counts.
    """
    buf = _io.BytesIO(file_bytes) if not isinstance(file_bytes, _io.BytesIO) else file_bytes

    # ── Sheet 1: Scope UPDATE ─────────────────────────────────────────────────
    raw_scope = pd.read_excel(buf, sheet_name="Scope UPDATE", header=0)
    raw_scope.columns = [str(c).strip() for c in raw_scope.columns]

    # The last two columns hold the authoritative assignee→squad mapping.
    # Extract ALL rows BEFORE key filtering (team-roster rows often have no Key).
    _last_col = raw_scope.columns[-1]   # e.g. 'assignee' (col AQ)

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
    team["name"]        = team["name"].astype(str).str.strip()
    team["squad"]       = team["squad"].astype(str).str.strip().replace({"nan": "—"})
    team["cap_prod"]    = pd.to_numeric(team["cap_prod"], errors="coerce").fillna(0)
    team["transverse"]  = pd.to_numeric(team["transverse"], errors="coerce").fillna(0)
    team["contingence"] = pd.to_numeric(team["contingence"], errors="coerce").fillna(0)
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
    scope.to_sql("r25_scope",          con=engine, if_exists="append", index=False)
    team.to_sql("r25_team_avail",      con=engine, if_exists="append", index=False)
    sprint_meta.to_sql("r25_sprint_meta", con=engine, if_exists="append", index=False)

    print(f"[ETL] r25_scope: {len(scope)} rows | r25_team_avail: {len(team)} rows | "
          f"r25_assignee_squad: {len(assignee_squad)} rows")
    return {
        "scope_rows":         len(scope),
        "team_rows":          len(team),
        "assignee_squad_rows": len(assignee_squad),
    }
