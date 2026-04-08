"""
Sprint burndown materialisation — pre-compute daily series into DB tables.
"""
import pandas as pd
from sqlalchemy import text


# Statuses considered "delivered" for burndown counting
DELIVERED_STATUSES = {
    "closed", "qualification test", "ready for staging",
    "ready for exceptions", "ready for qa", "ready for sprint",
    "cancelled", "canceled", "on hold", "plan investigation", "work approved",
    "ready for acceptance", "waiting for customer",
}


def materialise_r25_burndown(engine, sprint_start=None, sprint_end=None) -> int:
    """
    Compute the R25 sprint burndown (scope-based) and write to `r25_burndown`.

    sprint_start / sprint_end: datetime.date objects; read from r25_sprint_meta if omitted.
    Returns number of rows written.
    """
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

    _sp_s = pd.Timestamp(sprint_start)
    _sp_e = pd.Timestamp(sprint_end) + pd.Timedelta(hours=23, minutes=59)

    _is_done = merged["status"].str.lower().str.strip().isin(DELIVERED_STATUSES) \
               if "status" in merged.columns \
               else pd.Series(False, index=merged.index)

    # Per date column: keep only if within sprint
    for _dc in _date_cols_e:
        _ts = pd.to_datetime(merged[_dc], errors="coerce")
        merged[_dc + "_ts"]  = _ts
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

    # ── Build exclusion info (DATE_OUTSIDE_SPRINT only) ────────────────────────
    _excluded = merged[_is_done & merged["_resolved_at"].isna()].copy()
    _excluded["exclusion_reason"] = "DATE_OUTSIDE_SPRINT"

    days          = pd.date_range(sprint_start, sprint_end, freq="D")
    total_pts     = float(merged["_pts"].sum())
    total_tickets = len(merged)
    n_days        = len(days)
    rows = []
    for i, day in enumerate(days):
        day_ts           = pd.Timestamp(day) + pd.Timedelta(hours=23, minutes=59)
        done_mask        = merged["_resolved_at"].notna() & (merged["_resolved_at"] <= day_ts)
        resolved_pts     = float(merged[done_mask]["_pts"].sum())
        resolved_tickets = int(done_mask.sum())
        ideal_pts     = round(total_pts     * (1 - i / (n_days - 1)), 4) if n_days > 1 else 0.0
        ideal_tickets = round(total_tickets * (1 - i / (n_days - 1)), 4) if n_days > 1 else 0.0
        rows.append({
            "date":                  day.date(),
            "total_pts":             round(total_pts, 2),
            "resolved_pts":          round(resolved_pts, 2),
            "remaining_pts":         round(total_pts - resolved_pts, 2),
            "ideal_pts":             ideal_pts,
            "pct_complete":          round(resolved_pts / total_pts * 100, 2) if total_pts else 0.0,
            "total_tickets":         total_tickets,
            "resolved_tickets":      resolved_tickets,
            "remaining_tickets":     total_tickets - resolved_tickets,
            "ideal_tickets":         ideal_tickets,
            "pct_complete_tickets":  round(resolved_tickets / total_tickets * 100, 2) if total_tickets else 0.0,
        })

    df_out = pd.DataFrame(rows)
    df_out["scope_type"] = "Committed"

    # ── Write tables (drop + recreate on each materialisation) ────────────────
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
    print(f"[ETL] DATE_OUTSIDE_SPRINT excluded: {len(_excluded)} tickets")
    return len(df_out)


def append_r25_full_burndown(engine, burn_df: pd.DataFrame, tickets_df: pd.DataFrame) -> dict:
    """
    Append 'Full Team' scope_type rows to r25_burndown and write r25_sprint_tickets.
    Call materialise_r25_burndown() first — it creates the tables and writes Committed rows.

    burn_df    : daily burndown rows, must have scope_type='Full Team'
    tickets_df : one row per ticket in the full pool
    """
    burn_df.to_sql("r25_burndown",       con=engine, if_exists="append", index=False)
    tickets_df.to_sql("r25_sprint_tickets", con=engine, if_exists="append", index=False)
    print(f"[ETL] r25_burndown (Full Team): {len(burn_df)} rows")
    print(f"[ETL] r25_sprint_tickets: {len(tickets_df)} rows")
    return {"burndown_rows": len(burn_df), "ticket_rows": len(tickets_df)}
