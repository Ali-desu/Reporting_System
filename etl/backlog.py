"""
Backlog burndown materialisation — prod-incident backlog daily series.
"""
import datetime as _dt

import pandas as pd
from sqlalchemy import text


def materialise_backlog_burndown(engine,
                                  track_from=None,
                                  track_to=None,
                                  target: int = 261) -> int:
    """
    Compute the prod-incident backlog burndown and write to `backlog_burndown`.

    track_from / track_to: datetime.date; defaults to 2026-01-01 → 2026-04-30.
    Returns number of rows written.
    """
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

    days   = pd.date_range(track_from, track_to, freq="D")
    n_days = len(days)

    start_ts = pd.Timestamp(track_from)

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
