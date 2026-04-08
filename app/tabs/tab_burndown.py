"""
Burndown tab — committed scope burndown + full-team burndown.
"""
import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from etl import materialise_r25_burndown, append_r25_full_burndown
from app.components import (
    kpi_card, sec, chart,
    DXC_PURPLE, DXC_PURPLE_LITE, DXC_GREY, DXC_GREY_LIGHT, CHART_THEME, _GRID,
)
from app.loaders import (
    _engine, load_r25_scope, load_team_availability, _name_score,
)

QUICK_START = datetime.date(2026, 3, 8)
QUICK_END   = datetime.date(2026, 4, 4)

_DELIVERED_STATUSES = {
    "closed", "qualification test", "ready for staging",
    "ready for exceptions", "ready for qa", "ready for sprint",
    "cancelled", "canceled", "on hold", "plan investigation", "work approved",
    "ready for acceptance", "waiting for customer",
}


def render(df_all: pd.DataFrame, df: pd.DataFrame):
    st.markdown("#### Sprint Burndown — R25 Committed Scope")

    try:
        scope_df   = load_r25_scope()
        scope_keys = scope_df["key"].tolist()
    except Exception as e:
        st.error(f"Could not load scope file: {e}")
        st.stop()

    db_cols = ["key", "summary", "issue_type", "priority", "status",
               "story_points", "is_resolved", "resolved", "closure_date",
               "qualification_date", "assignee"]
    df_db   = df_all[[c for c in db_cols if c in df_all.columns]].copy()
    df_db   = df_db[df_db["key"].isin(scope_keys)]

    df_merged = scope_df.merge(df_db, on="key", how="left")
    df_merged["_points"] = pd.to_numeric(df_merged["story_points"], errors="coerce") \
        .fillna(pd.to_numeric(df_merged["scope_points"], errors="coerce"))

    _date_cols = [c for c in ["qualification_date", "resolved", "closure_date"]
                  if c in df_merged.columns]

    # Sprint date selector
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

    _sp_start_ts = pd.Timestamp(sprint_start)
    _sp_end_ts   = pd.Timestamp(sprint_end) + pd.Timedelta(hours=23, minutes=59)

    _is_done = df_merged["status"].str.lower().str.strip().isin(_DELIVERED_STATUSES) \
               if "status" in df_merged.columns \
               else pd.Series(False, index=df_merged.index)

    for _dc in _date_cols:
        _ts = pd.to_datetime(df_merged[_dc], errors="coerce")
        df_merged[_dc + "_ts"] = _ts
        df_merged[_dc + "_in"] = _ts.where(_ts.notna() & (_ts >= _sp_start_ts) & (_ts <= _sp_end_ts))

    df_merged["_resolved_at"] = pd.concat(
        [df_merged[_dc + "_in"] for _dc in _date_cols], axis=1
    ).min(axis=1)
    df_merged["_any_date"] = pd.concat(
        [df_merged[_dc + "_ts"] for _dc in _date_cols], axis=1
    ).min(axis=1)
    df_merged["_resolved_at"] = df_merged["_resolved_at"].where(_is_done, pd.NaT)

    _no_date_mask = _is_done & df_merged["_resolved_at"].isna() & df_merged["_any_date"].isna()
    df_merged.loc[_no_date_mask, "_resolved_at"] = _sp_end_ts

    _bd_excluded = df_merged[_is_done & df_merged["_resolved_at"].isna()].copy()
    _bd_excluded["exclusion_reason"] = "DATE_OUTSIDE_SPRINT"

    if sprint_end <= sprint_start:
        st.error("End date must be after start date.")
        return

    # ── Burndown mode ──────────────────────────────────────────────────────────
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
    n_days  = len(days)
    burn_df["Ideal"] = [
        total_work * (1 - i / (n_days - 1)) for i in range(n_days)
    ] if n_days > 1 else [0]

    resolved_in_sprint = df_merged[df_merged["_resolved_at"].notna()]["_weight"].sum()
    pct_done = resolved_in_sprint / total_work * 100 if total_work > 0 else 0

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
        _bdf["Date"]   = _bdf["Date"].dt.strftime("%Y-%m-%d")
        for col in ["Remaining", "Ideal", "Burned Today"]:
            _bdf[col] = _bdf[col].round(1)
        st.dataframe(_bdf[["Date", "Remaining", "Ideal", "Burned Today", "% Done"]],
                     use_container_width=True, hide_index=True)

    # ── Solved tickets ─────────────────────────────────────────────────────────
    st.markdown("---")
    _solved = df_merged[df_merged["_resolved_at"].notna()].copy().sort_values("_resolved_at")
    sec(f"Solved Tickets ({len(_solved)} / {len(df_merged)})")
    if _solved.empty:
        st.info("No tickets marked as solved within the sprint window.")
    else:
        _sol_cols = [c for c in ["key", "summary", "assignee", "status",
                                  "_points", "_resolved_at", "qualification_date",
                                  "resolved", "closure_date"] if c in _solved.columns]
        _sol_display = _solved[_sol_cols].rename(columns={
            "_points": "story_points", "_resolved_at": "completed_at",
        })
        for _dc in ["completed_at", "qualification_date", "resolved", "closure_date"]:
            if _dc in _sol_display.columns:
                _sol_display[_dc] = pd.to_datetime(_sol_display[_dc], errors="coerce").dt.strftime("%Y-%m-%d")
        _sol_page_size    = 15
        _sol_total_pages  = max(1, -(-len(_sol_display) // _sol_page_size))
        _sol_page = st.number_input(
            f"Page (1 – {_sol_total_pages})",
            min_value=1, max_value=_sol_total_pages, value=1, step=1, key="sol_page",
        )
        _sol_start = (_sol_page - 1) * _sol_page_size
        st.dataframe(
            _sol_display.iloc[_sol_start: _sol_start + _sol_page_size],
            use_container_width=True, hide_index=True,
        )
        st.caption(f"Showing {min(_sol_start + 1, len(_sol_display))}–"
                   f"{min(_sol_start + _sol_page_size, len(_sol_display))} "
                   f"of {len(_sol_display)} solved tickets")

    if not _bd_excluded.empty:
        st.markdown("---")
        with st.expander(
            f"⚠️ {len(_bd_excluded)} delivered ticket(s) excluded from burndown "
            "— all dates fall outside the sprint window",
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
                             "exclusion_reason"] if c in _bd_excluded.columns
            ]].copy()
            for _dc in ["qualification_date", "resolved", "closure_date"]:
                if _dc in _excl_show.columns:
                    _excl_show[_dc] = pd.to_datetime(_excl_show[_dc], errors="coerce").dt.strftime("%Y-%m-%d")
            st.dataframe(_excl_show, use_container_width=True, hide_index=True)

    # ── Scope issues table ─────────────────────────────────────────────────────
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

    # ── Out of scope ───────────────────────────────────────────────────────────
    st.markdown("---")
    sec("R25 Issues NOT in Committed Scope")
    st.caption(
        "Issues found in Jira with an R25 sprint assignment that are **not** in the "
        "committed scope file."
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

    # ── Full team burndown ─────────────────────────────────────────────────────
    st.markdown("---")
    sec("Burndown — All Tickets Resolved During Sprint")
    st.caption(
        "Shows every Jira ticket with a delivered status whose **earliest date within "
        "the sprint** (qualification → resolved → closure) falls inside the sprint window. "
        "Not limited to committed scope — filtered to team members only."
    )

    _DELIVERED_ALL = _DELIVERED_STATUSES
    _all_db_cols = ["key", "summary", "issue_type", "priority", "status",
                    "story_points", "assignee", "created",
                    "qualification_date", "resolved", "closure_date"]
    _all_df = df_all[[c for c in _all_db_cols if c in df_all.columns]].copy()

    _avail_df_bd, _ = load_team_availability()
    _avail_names_bd  = _avail_df_bd["name"].drop_duplicates().tolist()
    _all_assignees   = _all_df["assignee"].dropna().unique().tolist()
    _team_jira_names = set()
    for _jn in _all_assignees:
        for _an in _avail_names_bd:
            if _name_score(_jn, _an) >= 0.65:
                _team_jira_names.add(_jn)
                break
    _team_df = _all_df[_all_df["assignee"].isin(_team_jira_names)].copy()

    _scope_db_cols  = ["key", "summary", "issue_type", "priority", "status",
                       "story_points", "assignee", "created",
                       "qualification_date", "resolved", "closure_date"]
    _scope_from_db  = df_all[df_all["key"].isin(scope_keys)][
        [c for c in _scope_db_cols if c in df_all.columns]
    ].copy()

    _combined = pd.concat([_scope_from_db, _team_df], ignore_index=True) \
                  .drop_duplicates(subset="key", keep="first")
    _combined = _combined.merge(scope_df[["key", "scope_points"]], on="key", how="left")
    _combined["story_points"] = pd.to_numeric(_combined["story_points"], errors="coerce") \
        .fillna(pd.to_numeric(_combined.get("scope_points", pd.Series(dtype=float)), errors="coerce"))
    _combined["in_scope"] = _combined["key"].isin(scope_keys)

    _all_sp_s  = pd.Timestamp(sprint_start)
    _all_sp_e  = pd.Timestamp(sprint_end) + pd.Timedelta(hours=23, minutes=59)
    _all_date_cols = [c for c in ["qualification_date", "resolved", "closure_date"]
                      if c in _combined.columns]
    for _adc in _all_date_cols:
        _ts = pd.to_datetime(_combined[_adc], errors="coerce")
        _combined[_adc + "_in"] = _ts.where(_ts.notna() & (_ts >= _all_sp_s) & (_ts <= _all_sp_e))

    _combined["_resolved_at"] = pd.concat(
        [_combined[_adc + "_in"] for _adc in _all_date_cols], axis=1
    ).min(axis=1)

    _combined_is_done = _combined["status"].str.lower().str.strip().isin(_DELIVERED_ALL) \
                        if "status" in _combined.columns \
                        else pd.Series(False, index=_combined.index)
    _combined["_resolved_at"] = _combined["_resolved_at"].where(_combined_is_done, pd.NaT)

    # For committed scope tickets: no date at all → push to sprint end (same as burndown 1)
    _combined["_any_date_ft"] = pd.concat(
        [pd.to_datetime(_combined[_adc], errors="coerce") for _adc in _all_date_cols], axis=1
    ).min(axis=1)
    _no_date_scope = (
        _combined["in_scope"] &
        _combined_is_done &
        _combined["_resolved_at"].isna() &
        _combined["_any_date_ft"].isna()
    )
    _combined.loc[_no_date_scope, "_resolved_at"] = _all_sp_e

    _combined["_weight"] = pd.to_numeric(_combined["story_points"], errors="coerce").fillna(0) \
                           if burn_mode == "Story Points" else 1.0

    # Full team burndown:
    # - Committed scope: all tickets (done+no date → sprint end, done+date in sprint → that date,
    #                    done+date outside sprint → _resolved_at is NaT, still in pool)
    # - Extra team tickets: only those done with a date within the sprint window
    _scope_pool_all = _combined[_combined["in_scope"]].copy()
    _extra_resolved = _combined[~_combined["in_scope"] & _combined["_resolved_at"].notna()].copy()
    _full_pool      = pd.concat([_scope_pool_all, _extra_resolved], ignore_index=True)

    _all_total      = _full_pool["_weight"].sum()
    _all_resolved_n = _full_pool["_resolved_at"].notna().sum()

    _all_days      = pd.date_range(start=sprint_start, end=sprint_end, freq="D")
    _all_remaining = []
    for _aday in _all_days:
        _aday_end = pd.Timestamp(_aday) + pd.Timedelta(hours=23, minutes=59)
        _done_by  = _full_pool[_full_pool["_resolved_at"].notna() &
                               (_full_pool["_resolved_at"] <= _aday_end)]["_weight"].sum()
        _all_remaining.append(_all_total - _done_by)

    _all_burn_df = pd.DataFrame({"Date": _all_days, "Remaining": _all_remaining})
    _all_n       = len(_all_days)
    _all_burn_df["Ideal"] = [
        _all_total * (1 - i / (_all_n - 1)) for i in range(_all_n)
    ] if _all_n > 1 else [0]

    _all_pct = _all_resolved_n / len(_full_pool) * 100 if len(_full_pool) > 0 else 0
    _ak1, _ak2, _ak3, _ak4 = st.columns(4)
    with _ak1: kpi_card("Total Pool", f"{len(_full_pool)} tickets")
    with _ak2: kpi_card("Committed Scope", f"{len(_scope_pool_all)} tickets")
    with _ak3: kpi_card("Extra (out of scope)", f"{len(_extra_resolved)} tickets")
    with _ak4: kpi_card("Resolved", f"{_all_resolved_n} ({_all_pct:.0f}%)",
                        color=DXC_PURPLE_LITE if _all_pct >= 80 else "#E65100")

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

    # ── Save to DB ─────────────────────────────────────────────────────────────
    st.markdown("---")
    if st.button("Save Sprint Burndowns to DB (Committed + Full Team)", key="save_full_burn"):
        with st.spinner("Saving…"):
            materialise_r25_burndown(_engine())

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

            _DELIVERED_SET_SAVE = _DELIVERED_STATUSES
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

    # ── Full ticket list ───────────────────────────────────────────────────────
    st.markdown("---")
    sec(f"Full Ticket List ({len(_full_pool)} tickets)")
    _tbl_assignees = ["All"] + sorted(_full_pool["assignee"].dropna().unique().tolist())
    _tbl_scope_filter    = st.radio("Scope", ["All", "In Scope", "Out of Scope"],
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
                               "story_points", "in_scope", "_resolved_at",
                               "created", "qualification_date", "resolved", "closure_date"]
                 if c in _tbl_df.columns]
    _tbl_display = _tbl_df[_tbl_cols].rename(
        columns={"_resolved_at": "completed_at", "in_scope": "In Scope"}
    ).copy()
    for _dc in ["completed_at", "created", "qualification_date", "resolved", "closure_date"]:
        if _dc in _tbl_display.columns:
            _tbl_display[_dc] = pd.to_datetime(_tbl_display[_dc], errors="coerce").dt.strftime("%Y-%m-%d")
    st.dataframe(
        _tbl_display.sort_values("completed_at", na_position="last"),
        use_container_width=True, hide_index=True,
    )
