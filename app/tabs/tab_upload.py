"""
Upload tab — Jira sync, Extract file upload, Release Lifecycle upload,
and burndown refresh buttons.
"""
import datetime as _dt_ui
import io

import pandas as pd
import streamlit as st

from etl import (
    clean_data, initial_load, upsert,
    load_release_lifecycle,
    materialise_r25_burndown, materialise_backlog_burndown,
    fetch_jira_issues,
)
from app.loaders import (
    _engine, _table_exists, _rl_table_exists,
    load_data, load_r25_scope, load_r25_assignee_squad, load_team_availability,
)


def render(df_all: pd.DataFrame, has_data: bool):
    # ── Jira Sync ─────────────────────────────────────────────────────────────
    import os
    st.markdown("#### Sync from Jira")
    st.markdown(
        "Pull all **IRPAUTO** issues directly from Jira — no Excel export needed. "
        "Credentials are read from your `.env` file."
    )

    _jira_url   = os.getenv("JIRA_URL",        "https://dxc-insurance-delivery.atlassian.net")
    _jira_email = os.getenv("JIRA_EMAIL",       "")
    _jira_token = os.getenv("JIRA_API_TOKEN",   "")

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
            "⚠️ Full reload will fetch all ~55 000 issues (~10 min)." if _is_full else
            f"Incremental sync: issues updated on or after **{_since_date}**."
        )
        if st.button("⚡ Sync from Jira", type="primary", key="jira_sync_btn"):
            _mode_str  = "replace" if _is_full else "upsert"
            _since_str = None if _is_full else str(_since_date)
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

    # ── Upload Extract File ───────────────────────────────────────────────────
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
                    raw     = pd.read_excel(io.BytesIO(uploaded.read()), sheet_name=0)
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

    # ── Upload Release Lifecycle File ─────────────────────────────────────────
    st.markdown("#### Upload Release Lifecycle File")
    st.markdown(
        "Upload the **Release_lifecycle_R25.xlsx** file to load sprint scope and team "
        "availability into the database. This enables the **Burndown** and **Team** tabs."
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

    # ── Refresh Power BI Burndown Tables ─────────────────────────────────────
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

    # ── Database Snapshot ─────────────────────────────────────────────────────
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

        _db_page_size    = 50
        _db_total        = len(_db_view)
        _db_total_pages  = max(1, -(-_db_total // _db_page_size))
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
