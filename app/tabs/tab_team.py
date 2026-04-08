"""
Team Commitment tab — R25 sprint commitment analysis per assignee and squad.
"""
import datetime as _dt_team

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from etl import materialise_r25_team_commitment
from app.components import (
    kpi_card, sec, chart,
    DXC_PURPLE, DXC_PURPLE_LITE, DXC_TEXT, DXC_GREY, CHART_THEME, _GRID,
)
from app.loaders import (
    _engine, load_team_availability, load_r25_scope, load_r25_assignee_squad, _name_score,
)

DELIVERED_STATUSES = {
    "closed", "qualification test", "ready for staging",
    "ready for exceptions", "ready for qa", "ready for sprint",
    "cancelled", "canceled", "on hold", "plan investigation", "work approved",
    "ready for acceptance", "waiting for customer",
}
NOT_DELIVERED_STATUSES = {
    "acknowledge", "analysis", "dev in progress", "estimation", "in progress",
}


def _normalise_squad(s):
    if not s or str(s).strip().lower() in ("", "nan", "none"):
        return "—"
    s  = str(s).strip()
    sl = s.lower()
    if sl in ("transverse",):
        return "—"
    if s.upper() == "DSN/FLUX FINANCIER" or "flux financier" in sl or ("flux" in sl and "dsn" in sl):
        return "DSN/FLUX FINANCIER"
    if "pr" in sl and "voyance" in sl:
        return "Risk & Protection"
    if "risk" in sl and "protection" in sl:
        return "Risk & Protection"
    if "contrat" in sl or "sant" in sl:
        return "Health & Contracts & Persons"
    if "health" in sl and ("contract" in sl or "person" in sl):
        return "Health & Contracts & Persons"
    if "editique" in sl or "\u00e9ditique" in sl:
        return "Printing"
    if "comptab" in sl or "compta" in sl:
        return "Accounting/PDM/BI"
    if "accounting" in sl or "pdm" in sl:
        return "Accounting/PDM/BI"
    return s


def _commitment(delivered, not_delivered):
    denom = delivered + not_delivered
    return round(delivered / denom * 100, 1) if denom > 0 else 0.0


def render(df: pd.DataFrame):
    st.markdown("#### Team Commitment — R25")

    try:
        avail_df, sprint_info = load_team_availability()
        scope_df_t            = load_r25_scope()
        scope_keys_t          = scope_df_t["key"].tolist()
        assignee_squad_df     = load_r25_assignee_squad()
    except Exception as _e:
        st.error(f"Could not load Release Lifecycle file: {_e}")
        st.stop()

    _db_cols = ["key", "status", "story_points", "qualification_date",
                "resolved", "closure_date", "assignee", "expected_sprint",
                "issue_type", "project", "summary", "priority"]
    _df_all = df[[c for c in _db_cols if c in df.columns]].copy()
    _df_all["_pts"]              = pd.to_numeric(_df_all["story_points"], errors="coerce").fillna(0)
    _df_all["_status_lower"]     = _df_all["status"].str.lower().str.strip().fillna("")
    _df_all["_is_delivered"]     = _df_all["_status_lower"].isin(DELIVERED_STATUSES)
    _df_all["_is_not_delivered"] = _df_all["_status_lower"].isin(NOT_DELIVERED_STATUSES)
    _df_m = _df_all[_df_all["key"].isin(scope_keys_t)].copy()

    _T_DEFAULT_START = sprint_info.get("start") or _dt_team.date(2026, 3, 8)
    _T_DEFAULT_END   = sprint_info.get("end")   or _dt_team.date(2026, 4, 4)

    _tc1, _tc2 = st.columns(2)
    with _tc1:
        _team_sprint_start = st.date_input(
            "Sprint Start",
            value=st.session_state.get("burn_start", _T_DEFAULT_START),
            key="team_sprint_start",
        )
    with _tc2:
        _team_sprint_end = st.date_input(
            "Sprint End",
            value=st.session_state.get("burn_end", _T_DEFAULT_END),
            key="team_sprint_end",
        )

    _sp_start = pd.Timestamp(_team_sprint_start)
    _sp_end   = pd.Timestamp(_team_sprint_end) + pd.Timedelta(hours=23, minutes=59)
    st.markdown("---")

    # ── Name matching ─────────────────────────────────────────────────────────
    _all_scope_assignees = _df_all["assignee"].dropna().unique().tolist()
    _unique_avail_names  = avail_df["name"].drop_duplicates().tolist()

    _pair_scores = []
    for _jn in _all_scope_assignees:
        for _an in _unique_avail_names:
            _s = _name_score(_jn, _an)
            if _s >= 0.65:
                _pair_scores.append({"jira": _jn, "avail": _an, "score": _s})

    _jira_to_avail: dict = {}
    for _p in sorted(_pair_scores, key=lambda x: -x["score"]):
        if _p["jira"] not in _jira_to_avail:
            _jira_to_avail[_p["jira"]] = _p["avail"]

    _avail_to_jiras: dict = {}
    for _jn, _an in _jira_to_avail.items():
        _avail_to_jiras.setdefault(_an, []).append(_jn)

    _matched_jira_names = set(_jira_to_avail.keys())

    # ── Squad lookup ──────────────────────────────────────────────────────────
    _jn_squad_map: dict = {}

    # Level 1: scope ticket key→squad
    _scope_key_squad: dict = {}
    if "squad" in scope_df_t.columns:
        for _, _sr in scope_df_t[["key", "squad"]].iterrows():
            _sq = _normalise_squad(_sr["squad"])
            if _sq != "—":
                _scope_key_squad[_sr["key"]] = _sq
        _scope_jn_df = _df_all[["key", "assignee"]].copy()
        _scope_jn_df["squad"] = _scope_jn_df["key"].map(_scope_key_squad)
        for _jn in _matched_jira_names:
            _squads = _scope_jn_df[_scope_jn_df["assignee"] == _jn]["squad"].dropna()
            if not _squads.empty:
                _jn_squad_map[_jn] = _squads.mode().iloc[0]

    # Level 2: AQ roster
    if not assignee_squad_df.empty:
        _sa_squad: dict = {}
        for _, _sr in assignee_squad_df.iterrows():
            _raw_name = str(_sr["assignee_name"]).strip()
            _sq = _normalise_squad(_sr["squad"])
            if not _raw_name or _raw_name.lower() in ("nan", "none", "") or _sq == "—":
                continue
            _sa_squad.setdefault(_raw_name, _sq)
        for _raw_name, _sq in _sa_squad.items():
            _best_jn, _best_score = None, 0.0
            for _jn in _matched_jira_names:
                _sc = _name_score(_raw_name, _jn)
                if _sc > _best_score:
                    _best_score, _best_jn = _sc, _jn
            if _best_jn and _best_score >= 0.55 and _best_jn not in _jn_squad_map:
                _jn_squad_map[_best_jn] = _sq

    # Level 3: availability sheet
    _avail_name_squad_lookup = {
        row["name"]: _normalise_squad(row.get("squad", "—"))
        for _, row in avail_df.iterrows()
    }
    for _an, _jiras in _avail_to_jiras.items():
        for _jn in _jiras:
            if _jn not in _jn_squad_map:
                _sq = _avail_name_squad_lookup.get(_an, "—")
                if _sq != "—":
                    _jn_squad_map[_jn] = _sq

    # Supplementary: scope ticket owners not in availability sheet
    _scope_extra_jn_squad: dict = {}
    if _scope_key_squad:
        _scope_ticket_assignees = (
            _df_all[_df_all["key"].isin(scope_keys_t)]["assignee"].dropna().unique()
        )
        for _jn in _scope_ticket_assignees:
            if _jn in _matched_jira_names or _jn in _jn_squad_map:
                continue
            _keys = _df_all[_df_all["assignee"] == _jn]["key"].tolist()
            for _k in _keys:
                if _k in _scope_key_squad:
                    _scope_extra_jn_squad[_jn] = _scope_key_squad[_k]
                    break

    _combined_squad_map = {**_scope_extra_jn_squad, **_jn_squad_map}
    _all_team_jn = _matched_jira_names | set(_scope_extra_jn_squad.keys())

    # ── Scope pool ────────────────────────────────────────────────────────────
    _scope_pool = _df_m[_df_m["assignee"].isin(_all_team_jn)].copy()
    _scope_pool["squad"] = _scope_pool["assignee"].map(_combined_squad_map).fillna("—")
    _scope_pool["display_name"] = _scope_pool["assignee"].map(
        {_jn: _jira_to_avail.get(_jn, _jn) for _jn in _all_team_jn}
    ).fillna(_scope_pool["assignee"])

    # ── Per-assignee metrics ──────────────────────────────────────────────────
    _assignee_rows = []
    for _jn in sorted(_all_team_jn):
        _tix = _scope_pool[_scope_pool["assignee"] == _jn]
        if _tix.empty:
            continue
        _eng_t   = len(_tix)
        _eng_sp  = float(_tix["_pts"].sum())
        _del_t   = int(_tix["_is_delivered"].sum())
        _del_sp  = float(_tix[_tix["_is_delivered"]]["_pts"].sum())
        _ndel_t  = int(_tix["_is_not_delivered"].sum())
        _ndel_sp = float(_tix[_tix["_is_not_delivered"]]["_pts"].sum())
        _assignee_rows.append({
            "display_name":          _jira_to_avail.get(_jn, _jn),
            "jira_name":             _jn,
            "squad":                 _combined_squad_map.get(_jn, "—"),
            "engaged_tickets":       _eng_t,
            "engaged_sp":            _eng_sp,
            "delivered_tickets":     _del_t,
            "delivered_sp":          _del_sp,
            "not_delivered_tickets": _ndel_t,
            "not_delivered_sp":      _ndel_sp,
            "commitment_pct":        _commitment(_del_t, _ndel_t),
            "commitment_sp_pct":     _commitment(_del_sp, _ndel_sp),
        })
    _assignee_df = pd.DataFrame(_assignee_rows)

    # ── Per-squad metrics ─────────────────────────────────────────────────────
    _squad_rows = []
    _sq_pool_valid = _scope_pool[_scope_pool["squad"] != "—"].copy()
    for _sq, _grp in _sq_pool_valid.groupby("squad"):
        _squad_rows.append({
            "squad":                 _sq,
            "members":               _grp["assignee"].nunique(),
            "engaged_tickets":       len(_grp),
            "engaged_sp":            float(_grp["_pts"].sum()),
            "delivered_tickets":     int(_grp["_is_delivered"].sum()),
            "delivered_sp":          float(_grp[_grp["_is_delivered"]]["_pts"].sum()),
            "not_delivered_tickets": int(_grp["_is_not_delivered"].sum()),
            "not_delivered_sp":      float(_grp[_grp["_is_not_delivered"]]["_pts"].sum()),
            "commitment_pct":        _commitment(int(_grp["_is_delivered"].sum()),
                                                 int(_grp["_is_not_delivered"].sum())),
            "commitment_sp_pct":     _commitment(float(_grp[_grp["_is_delivered"]]["_pts"].sum()),
                                                 float(_grp[_grp["_is_not_delivered"]]["_pts"].sum())),
        })
    _squad_df = (
        pd.DataFrame(_squad_rows).sort_values("commitment_pct", ascending=False).reset_index(drop=True)
        if _squad_rows else pd.DataFrame()
    )

    # ── Team totals ───────────────────────────────────────────────────────────
    _total_eng_t   = int(_sq_pool_valid["_is_delivered"].count()) if not _sq_pool_valid.empty else 0
    _total_eng_sp  = float(_sq_pool_valid["_pts"].sum()) if not _sq_pool_valid.empty else 0
    _total_del_t   = int(_sq_pool_valid["_is_delivered"].sum()) if not _sq_pool_valid.empty else 0
    _total_del_sp  = float(_sq_pool_valid[_sq_pool_valid["_is_delivered"]]["_pts"].sum()) if not _sq_pool_valid.empty else 0
    _total_ndel_t  = int(_sq_pool_valid["_is_not_delivered"].sum()) if not _sq_pool_valid.empty else 0
    _total_ndel_sp = float(_sq_pool_valid[_sq_pool_valid["_is_not_delivered"]]["_pts"].sum()) if not _sq_pool_valid.empty else 0
    _team_commit   = _commitment(_total_del_t, _total_ndel_t)

    # ── Sprint banner ─────────────────────────────────────────────────────────
    _team_n_days = (_team_sprint_end - _team_sprint_start).days + 1
    _sb1, _sb2, _sb3, _sb4, _sb5 = st.columns(5)
    with _sb1: kpi_card("Sprint", "R25")
    with _sb2: kpi_card("Duration", f"{_team_n_days} days")
    with _sb3: kpi_card("Dates",
                         f"{_team_sprint_start.strftime('%d %b')} → "
                         f"{_team_sprint_end.strftime('%d %b %Y')}")
    with _sb4: kpi_card("Engaged SP", f"{_total_eng_sp:.0f} SP")
    with _sb5: kpi_card("Team Commitment", f"{_team_commit:.1f}%",
                         color="#4CAF50" if _team_commit >= 80 else "#E65100")

    st.markdown("---")
    st.caption(
        "Commitment % = Delivered / (Delivered + Not Delivered) × 100  "
        "— OTHER-status tickets are engaged but excluded from the denominator."
    )
    _k1, _k2, _k3, _k4, _k5, _k6 = st.columns(6)
    with _k1: kpi_card("Engaged Tickets", str(_total_eng_t))
    with _k2: kpi_card("Engaged SP", f"{_total_eng_sp:.0f}")
    with _k3: kpi_card("Delivered (T)", str(_total_del_t), color="#4CAF50")
    with _k4: kpi_card("Delivered SP", f"{_total_del_sp:.0f}", color="#4CAF50")
    with _k5: kpi_card("Not Delivered (T)", str(_total_ndel_t), color="#E65100")
    with _k6: kpi_card("Commitment (T)", f"{_team_commit:.1f}%",
                        color="#4CAF50" if _team_commit >= 80 else "#E65100")

    st.markdown("---")

    # ── Squad summary ─────────────────────────────────────────────────────────
    sec("Squad Commitment Summary")
    if _squad_df.empty:
        st.info("No squad data available.")
    else:
        _sq_tbl = _squad_df[[
            "squad", "members", "engaged_tickets", "engaged_sp",
            "delivered_tickets", "delivered_sp",
            "not_delivered_tickets", "not_delivered_sp", "commitment_pct",
        ]].copy()
        _sq_total = pd.DataFrame([{
            "squad":                 "TOTAL",
            "members":               _sq_tbl["members"].sum(),
            "engaged_tickets":       _sq_tbl["engaged_tickets"].sum(),
            "engaged_sp":            _sq_tbl["engaged_sp"].sum(),
            "delivered_tickets":     _sq_tbl["delivered_tickets"].sum(),
            "delivered_sp":          _sq_tbl["delivered_sp"].sum(),
            "not_delivered_tickets": _sq_tbl["not_delivered_tickets"].sum(),
            "not_delivered_sp":      _sq_tbl["not_delivered_sp"].sum(),
            "commitment_pct":        _commitment(
                int(_sq_tbl["delivered_tickets"].sum()),
                int(_sq_tbl["not_delivered_tickets"].sum()),
            ),
        }])
        _sq_tbl = pd.concat([_sq_tbl, _sq_total], ignore_index=True)
        _sq_tbl = _sq_tbl.rename(columns={
            "squad": "Squad", "members": "Members",
            "engaged_tickets": "Engaged (T)", "engaged_sp": "Engaged SP",
            "delivered_tickets": "Delivered (T)", "delivered_sp": "Delivered SP",
            "not_delivered_tickets": "Not Delivered (T)", "not_delivered_sp": "Not Delivered SP",
            "commitment_pct": "Commitment %",
        })

        def _sq_commit_color(val):
            if val == "TOTAL":
                return "font-weight:bold"
            c = "#4CAF50" if val >= 80 else ("#E65100" if val >= 50 else "#C62828")
            return f"background-color:{c};color:white;font-weight:bold;border-radius:4px"

        st.dataframe(
            _sq_tbl.style.applymap(_sq_commit_color, subset=["Commitment %"]),
            use_container_width=True, hide_index=True,
        )
        st.markdown("<br>", unsafe_allow_html=True)

        _sq_sorted = _squad_df.sort_values("commitment_pct", ascending=False)
        _sq_fig = go.Figure()
        _sq_fig.add_trace(go.Bar(
            x=_sq_sorted["squad"], y=_sq_sorted["delivered_sp"],
            name="Delivered SP",
            marker=dict(color="#4CAF50", line=dict(color="white", width=1)),
            text=[f"<b>{v:.0f}</b>" for v in _sq_sorted["delivered_sp"]],
            textposition="inside", textfont=dict(color="white", size=12),
            hovertemplate="<b>%{x}</b><br>Delivered: %{y:.0f} SP (%{customdata} tickets)<extra></extra>",
            customdata=_sq_sorted["delivered_tickets"],
        ))
        _sq_fig.add_trace(go.Bar(
            x=_sq_sorted["squad"], y=_sq_sorted["not_delivered_sp"],
            name="Not Delivered SP",
            marker=dict(color="#E65100", line=dict(color="white", width=1)),
            text=[f"<b>{v:.0f}</b>" for v in _sq_sorted["not_delivered_sp"]],
            textposition="inside", textfont=dict(color="white", size=12),
            hovertemplate="<b>%{x}</b><br>Not Delivered: %{y:.0f} SP (%{customdata} tickets)<extra></extra>",
            customdata=_sq_sorted["not_delivered_tickets"],
        ))
        _sq_fig.add_trace(go.Scatter(
            x=_sq_sorted["squad"],
            y=_sq_sorted["engaged_sp"] * 1.06,
            mode="text",
            text=[f"<b>{p:.0f}%</b>" for p in _sq_sorted["commitment_pct"]],
            textfont=dict(size=14, color=DXC_PURPLE),
            showlegend=False, hoverinfo="skip",
        ))
        _sq_fig.update_layout(**{
            **CHART_THEME, "barmode": "stack", "height": 400, "bargap": 0.35,
            "xaxis": dict(gridcolor=_GRID, tickfont=dict(size=12, color=DXC_TEXT)),
            "yaxis": dict(title="Story Points", gridcolor=_GRID, zeroline=False),
            "legend": dict(orientation="h", y=1.08, x=0.5, xanchor="center",
                           font=dict(size=12, color=DXC_TEXT)),
            "margin": dict(t=50, b=30, l=20, r=20),
        })
        chart(_sq_fig)

    st.markdown("---")

    # ── Assignee breakdown ────────────────────────────────────────────────────
    sec("Assignee Commitment Breakdown")
    st.caption(
        "Green = delivered · Orange = not yet delivered · "
        "**Commitment %** = Delivered / (Delivered + Not Delivered) × 100 (tickets) · "
        "OTHER-status tickets shown in Engaged but excluded from the % denominator."
    )
    if _assignee_df.empty:
        st.info("No assignee data available.")
    else:
        _a_tbl = _assignee_df[[
            "display_name", "squad",
            "engaged_tickets", "engaged_sp",
            "delivered_tickets", "delivered_sp",
            "not_delivered_tickets", "not_delivered_sp",
            "commitment_pct", "commitment_sp_pct",
        ]].copy()
        _a_tbl.columns = [
            "Name", "Squad",
            "Engaged (T)", "Engaged SP",
            "Delivered (T)", "Delivered SP",
            "Not Delivered (T)", "Not Delivered SP",
            "Commitment % (T)", "Commitment % (SP)",
        ]
        _a_tbl = _a_tbl.sort_values("Commitment % (T)", ascending=False).reset_index(drop=True)
        st.dataframe(
            _a_tbl.style.background_gradient(
                subset=["Commitment % (T)", "Commitment % (SP)"], cmap="RdYlGn", vmin=0, vmax=100
            ),
            use_container_width=True, hide_index=True,
        )
        st.markdown("<br>", unsafe_allow_html=True)

        _a_sorted = _assignee_df.sort_values("commitment_pct", ascending=True)
        _af = go.Figure()
        _af.add_trace(go.Bar(
            x=_a_sorted["delivered_sp"], y=_a_sorted["display_name"],
            orientation="h", name="Delivered SP",
            marker=dict(color="#4CAF50", line=dict(width=0)),
            text=[f"{v:.0f}" for v in _a_sorted["delivered_sp"]],
            textposition="inside", textfont=dict(color="white", size=11),
            hovertemplate="<b>%{y}</b><br>Delivered: %{x:.0f} SP (%{customdata} tickets)<extra></extra>",
            customdata=_a_sorted["delivered_tickets"],
        ))
        _af.add_trace(go.Bar(
            x=_a_sorted["not_delivered_sp"], y=_a_sorted["display_name"],
            orientation="h", name="Not Delivered SP",
            marker=dict(color="#E65100", line=dict(width=0)),
            text=[f"{v:.0f}" for v in _a_sorted["not_delivered_sp"]],
            textposition="inside", textfont=dict(color="white", size=11),
            hovertemplate="<b>%{y}</b><br>Not Delivered: %{x:.0f} SP (%{customdata} tickets)<extra></extra>",
            customdata=_a_sorted["not_delivered_tickets"],
        ))
        _af.add_trace(go.Scatter(
            x=_a_sorted["engaged_sp"] * 1.03, y=_a_sorted["display_name"],
            mode="text",
            text=[f"<b>{p:.0f}%</b>" for p in _a_sorted["commitment_pct"]],
            textfont=dict(size=11, color=DXC_PURPLE),
            showlegend=False, hoverinfo="skip",
        ))
        _af.update_layout(**{
            **CHART_THEME, "barmode": "stack",
            "height": max(400, len(_a_sorted) * 38),
            "xaxis": dict(title="Story Points", gridcolor=_GRID),
            "yaxis": dict(tickfont=dict(size=11)),
            "legend": dict(orientation="h", y=1.04, x=0),
            "margin": dict(t=20, b=10, l=10, r=80),
        })
        chart(_af)

    st.markdown("---")

    # ── Ticket drill-down ─────────────────────────────────────────────────────
    sec("Ticket Drill-down")
    st.caption(
        "Scope tickets per assignee, classified by current status.  "
        "Green background = delivered · Orange = not delivered."
    )

    def _cell_status_style(val):
        sl = str(val).lower().strip()
        if sl in DELIVERED_STATUSES:
            return "background-color:#e8f5e9;color:#1b5e20"
        if sl in NOT_DELIVERED_STATUSES:
            return "background-color:#fff3e0;color:#bf360c"
        return "background-color:#f3e5f5;color:#4a148c"

    _drill_squads = sorted(s for s in _scope_pool["squad"].dropna().unique() if s != "—")
    for _dsq in _drill_squads:
        _sq_tix     = _scope_pool[_scope_pool["squad"] == _dsq]
        _sq_del     = int(_sq_tix["_is_delivered"].sum())
        _sq_eng     = len(_sq_tix)
        _sq_commit_pct = round(_sq_del / _sq_eng * 100) if _sq_eng > 0 else 0

        with st.expander(
            f"{_dsq}  —  {_sq_del}/{_sq_eng} delivered  ({_sq_commit_pct}%)", expanded=False
        ):
            for _jn in sorted(_sq_tix["assignee"].unique()):
                _p_tix        = _sq_tix[_sq_tix["assignee"] == _jn].copy()
                _p_name       = _jira_to_avail.get(_jn, _jn)
                _p_del        = int(_p_tix["_is_delivered"].sum())
                _p_eng        = len(_p_tix)
                _p_commit_pct = round(_p_del / _p_eng * 100) if _p_eng > 0 else 0
                _p_del_sp     = float(_p_tix[_p_tix["_is_delivered"]]["_pts"].sum())
                _p_eng_sp     = float(_p_tix["_pts"].sum())
                st.markdown(
                    f"**{_p_name}** &nbsp;·&nbsp; "
                    f"{_p_del}/{_p_eng} tickets &nbsp;·&nbsp; "
                    f"{_p_del_sp:.0f}/{_p_eng_sp:.0f} SP &nbsp;·&nbsp; "
                    f"**{_p_commit_pct}% commitment**"
                )
                _show_cols = [c for c in ["key", "summary", "status", "_pts", "issue_type", "priority"]
                              if c in _p_tix.columns]
                _tix_show = _p_tix[_show_cols].rename(columns={
                    "key": "Key", "summary": "Summary", "status": "Status",
                    "_pts": "SP", "issue_type": "Type", "priority": "Priority",
                }).reset_index(drop=True)
                st.dataframe(
                    _tix_show.style.applymap(_cell_status_style, subset=["Status"]),
                    use_container_width=True, hide_index=True,
                )
                st.markdown("<br>", unsafe_allow_html=True)

    st.markdown("---")

    # ── Export to DB ──────────────────────────────────────────────────────────
    sec("Export to Database")
    st.caption(
        "Writes three tables to the DB: **r25_team_assignee**, **r25_team_squad**, "
        "**r25_team_tickets** — connect these in PowerBI for commitment charts."
    )

    def _do_save_team_db():
        _tickets_out = _scope_pool[[
            c for c in ["key", "summary", "status", "assignee", "display_name",
                         "squad", "_pts", "issue_type", "priority",
                         "_is_delivered", "_is_not_delivered",
                         "qualification_date", "resolved", "closure_date"]
            if c in _scope_pool.columns
        ]].rename(columns={
            "_pts":              "story_points",
            "_is_delivered":     "is_delivered",
            "_is_not_delivered": "is_not_delivered",
        }).copy()
        for _bc in ["is_delivered", "is_not_delivered"]:
            if _bc in _tickets_out.columns:
                _tickets_out[_bc] = _tickets_out[_bc].astype(int)

        _t_sp_s = pd.Timestamp(_team_sprint_start)
        _t_sp_e = pd.Timestamp(_team_sprint_end) + pd.Timedelta(hours=23, minutes=59)
        _DELIVERED_SET = DELIVERED_STATUSES
        _t_is_done  = _tickets_out["status"].str.lower().str.strip().isin(_DELIVERED_SET)
        _date_cols_t = [c for c in ["qualification_date", "resolved", "closure_date"]
                        if c in _tickets_out.columns]
        _any_date   = pd.concat(
            [pd.to_datetime(_tickets_out[c], errors="coerce") for c in _date_cols_t], axis=1
        ).min(axis=1)
        _in_sprint  = pd.concat([
            pd.to_datetime(_tickets_out[c], errors="coerce").where(
                lambda s: s.notna() & (s >= _t_sp_s) & (s <= _t_sp_e)
            ) for c in _date_cols_t
        ], axis=1).min(axis=1)
        _has_in_sprint = _in_sprint.notna()

        def _excl_reason(row_idx):
            if not _t_is_done.iloc[row_idx]:
                return None
            if _has_in_sprint.iloc[row_idx]:
                return None
            if pd.isna(_any_date.iloc[row_idx]):
                return None
            return "DATE_OUTSIDE_SPRINT"

        _tickets_out["exclusion_reason"] = [_excl_reason(i) for i in range(len(_tickets_out))]
        _assignee_out = _assignee_df.drop(columns=["jira_name"], errors="ignore")
        _squad_out    = _squad_df.copy()

        return materialise_r25_team_commitment(
            _engine(), _assignee_out, _squad_out, _tickets_out,
        )

    _btn_col1, _btn_col2 = st.columns([2, 2])
    with _btn_col1:
        if st.button("Save team commitment to DB", type="primary", key="save_team_db"):
            if _assignee_df.empty:
                st.warning("No data to save — load the Release Lifecycle file first.")
            else:
                try:
                    _counts = _do_save_team_db()
                    st.success(
                        f"Saved — "
                        f"{_counts['r25_team_assignee']} assignees · "
                        f"{_counts['r25_team_squad']} squads · "
                        f"{_counts['r25_team_tickets']} tickets"
                    )
                except Exception as _ex:
                    st.error(f"DB write failed: {_ex}")

    with _btn_col2:
        if st.button("Refresh DB tables", key="refresh_team_db",
                     help="Re-run the save with current data (use after a Jira sync)"):
            if _assignee_df.empty:
                st.warning("No data to refresh — load the Release Lifecycle file first.")
            else:
                try:
                    _counts = _do_save_team_db()
                    st.success(
                        f"Refreshed — "
                        f"{_counts['r25_team_assignee']} assignees · "
                        f"{_counts['r25_team_squad']} squads · "
                        f"{_counts['r25_team_tickets']} tickets"
                    )
                except Exception as _ex:
                    st.error(f"DB refresh failed: {_ex}")

    st.markdown("---")

    # ── Debug panel ───────────────────────────────────────────────────────────
    with st.expander("Debug — Name Matching & Squad Assignments", expanded=False):
        _score_lookup = {(_p["avail"], _p["jira"]): round(_p["score"], 2) for _p in _pair_scores}
        _debug_rows = []
        for _an in _unique_avail_names:
            _jiras   = _avail_to_jiras.get(_an, [])
            _scores  = [str(_score_lookup.get((_an, _jn), "?")) for _jn in _jiras]
            _squad_d = next((_jn_squad_map.get(_jn) for _jn in _jiras if _jn in _jn_squad_map), "—")
            _a_row   = next((r for r in _assignee_rows if r["display_name"] == _an), {})
            _debug_rows.append({
                "Avail Name":           _an,
                "Matched Jira Name(s)": ", ".join(_jiras) if _jiras else "— no match —",
                "Score(s)":             ", ".join(_scores) if _scores else "—",
                "Squad":                _squad_d,
                "Engaged Tickets":      _a_row.get("engaged_tickets", 0),
                "Delivered SP":         round(_a_row.get("delivered_sp", 0.0), 1),
                "Commitment %":         _a_row.get("commitment_pct", 0.0),
            })
        st.dataframe(pd.DataFrame(_debug_rows), use_container_width=True, hide_index=True)
