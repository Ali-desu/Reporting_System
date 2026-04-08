"""
Team commitment materialisation — persist assignee/squad/ticket tables to DB.
"""
import pandas as pd
from sqlalchemy import text


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
        display_name, squad,
        engaged_tickets, engaged_sp,
        delivered_tickets, delivered_sp,
        not_delivered_tickets, not_delivered_sp,
        commitment_pct, commitment_sp_pct
    squad_df : DataFrame with columns:
        squad, members,
        engaged_tickets, engaged_sp,
        delivered_tickets, delivered_sp,
        not_delivered_tickets, not_delivered_sp,
        commitment_pct, commitment_sp_pct
    tickets_df : DataFrame with columns:
        key, summary, status, assignee, display_name, squad,
        story_points, issue_type, priority,
        is_delivered, is_not_delivered,
        qualification_date, resolved, closure_date, exclusion_reason

    Returns dict with row counts per table.
    """
    with engine.begin() as conn:
        # ── r25_team_assignee ─────────────────────────────────────────────────
        conn.execute(text("DROP TABLE IF EXISTS r25_team_assignee"))
        conn.execute(text("""
            CREATE TABLE r25_team_assignee (
                display_name          VARCHAR(120) NOT NULL,
                squad                 VARCHAR(120),
                engaged_tickets       INT,
                engaged_sp            FLOAT,
                delivered_tickets     INT,
                delivered_sp          FLOAT,
                not_delivered_tickets INT,
                not_delivered_sp      FLOAT,
                commitment_pct        FLOAT,
                commitment_sp_pct     FLOAT,
                PRIMARY KEY (display_name)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """))

        # ── r25_team_squad ────────────────────────────────────────────────────
        conn.execute(text("DROP TABLE IF EXISTS r25_team_squad"))
        conn.execute(text("""
            CREATE TABLE r25_team_squad (
                squad                 VARCHAR(120) NOT NULL,
                members               INT,
                engaged_tickets       INT,
                engaged_sp            FLOAT,
                delivered_tickets     INT,
                delivered_sp          FLOAT,
                not_delivered_tickets INT,
                not_delivered_sp      FLOAT,
                commitment_pct        FLOAT,
                commitment_sp_pct     FLOAT,
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
    squad_df.to_sql("r25_team_squad",       con=engine, if_exists="append", index=False)
    tickets_df.to_sql("r25_team_tickets",   con=engine, if_exists="append", index=False)

    counts = {
        "r25_team_assignee": len(assignee_df),
        "r25_team_squad":    len(squad_df),
        "r25_team_tickets":  len(tickets_df),
    }
    print(f"[ETL] team commitment: {counts}")
    return counts
