"""
Backlog Burndown tab — production incident backlog tracking.
"""
import datetime as _dt

import numpy as _np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from etl import materialise_backlog_burndown
from app.components import (
    kpi_card, sec, chart,
    DXC_PURPLE_LITE, DXC_GREY, DXC_GREY_LIGHT, CHART_THEME, _GRID,
)
from app.loaders import _engine


def render(df_all: pd.DataFrame):
    st.markdown("#### Production Incident Backlog Burndown")
    st.markdown(
        "Tracks daily resolution progress across **all production incidents**. "
        "New tickets created each day increase the remaining count; resolved tickets decrease it."
    )

    _bc1, _bc2, _bc3 = st.columns(3)
    with _bc1:
        _bl_start = st.date_input("Track from", value=_dt.date(2026, 1, 1), key="bl_start")
    with _bc2:
        _bl_end = st.date_input("Track to", value=_dt.date(2026, 4, 30), key="bl_end")
    with _bc3:
        _bl_target = st.number_input(
            "Target open tickets", min_value=0, max_value=10000,
            value=261, step=10, key="bl_target",
        )

    if _bl_end <= _bl_start:
        st.error("End date must be after start date.")
        return

    _bl_df = df_all[
        (df_all["issue_type"] == "Incident") &
        (df_all["environment_type"] == "Production")
    ].copy()

    _closed_statuses = {"Closed", "Cancelled"}
    _bl_df["_resolved_at"] = pd.NaT
    for _c in ["closure_date", "resolved"]:
        if _c in _bl_df.columns:
            _bl_df["_resolved_at"] = _bl_df["_resolved_at"].fillna(_bl_df[_c])
    _bl_df["_is_closed"] = _bl_df["status"].isin(_closed_statuses)

    _start_ts = pd.Timestamp(_bl_start)
    _end_ts   = pd.Timestamp(_bl_end) + pd.Timedelta(hours=23, minutes=59)
    _today_ts = pd.Timestamp(_dt.date.today())

    _days = pd.date_range(start=_bl_start, end=_bl_end, freq="D")
    _remaining, _opened_pd, _closed_pd = [], [], []
    for _day in _days:
        _d_end = _day + pd.Timedelta(hours=23, minutes=59)
        _open  = _bl_df[
            (_bl_df["created"] <= _d_end) &
            (~_bl_df["_is_closed"] | (_bl_df["_resolved_at"] > _d_end))
        ]
        _remaining.append(len(_open))
        _opened_pd.append(len(_bl_df[(_bl_df["created"] >= _day) & (_bl_df["created"] <= _d_end)]))
        _closed_pd.append(
            len(_bl_df[_bl_df["_resolved_at"].notna() &
                       (_bl_df["_resolved_at"] >= _day) &
                       (_bl_df["_resolved_at"] <= _d_end)])
        )

    _burn_df = pd.DataFrame({
        "Date": _days, "Remaining": _remaining,
        "Opened": _opened_pd, "Closed": _closed_pd,
    })
    _actual = _burn_df[_burn_df["Date"] <= _today_ts].copy()

    _forecast_date, _daily_rate, _forecast_df = None, None, pd.DataFrame(columns=["Date", "Forecast"])
    if len(_actual) >= 7:
        _recent    = _actual.tail(14)
        _x         = _np.arange(len(_recent))
        _y         = _recent["Remaining"].values.astype(float)
        _slope, _intercept = _np.polyfit(_x, _y, 1)
        _daily_rate = -_slope
        if _slope < 0:
            _days_needed = (_recent["Remaining"].iloc[-1] - _bl_target) / (-_slope)
            if _days_needed > 0:
                _forecast_date = (_recent["Date"].iloc[-1] + pd.Timedelta(days=int(_days_needed))).date()
        _fc_days = pd.date_range(_actual["Date"].iloc[-1], _days[-1], freq="D")
        _fc_vals = [max(0, float(_actual["Remaining"].iloc[-1]) + _slope * i) for i in range(len(_fc_days))]
        _forecast_df = pd.DataFrame({"Date": _fc_days, "Forecast": _fc_vals})

    _current_open = int(_actual["Remaining"].iloc[-1]) if len(_actual) else 0
    _gap          = _current_open - _bl_target
    _net_progress = int(_actual["Closed"].sum() - _actual["Opened"].sum()) if len(_actual) else 0

    _bk1, _bk2, _bk3, _bk4, _bk5 = st.columns(5)
    with _bk1: kpi_card("Currently Open", f"{_current_open:,}",
                         color="#C62828" if _current_open > _bl_target else "#4CAF50")
    with _bk2: kpi_card("Target", f"{_bl_target:,} by {_bl_end.strftime('%d %b')}")
    with _bk3: kpi_card("Gap to Target", f"{_gap:+,}",
                         color="#C62828" if _gap > 0 else "#4CAF50")
    with _bk4: kpi_card("Net Resolved (period)", f"{_net_progress:+,}",
                         color="#4CAF50" if _net_progress > 0 else "#C62828")
    with _bk5:
        if _forecast_date:
            kpi_card("Projected Date", _forecast_date.strftime("%d %b %Y"),
                     color="#4CAF50" if _forecast_date <= _bl_end else "#C62828")
        elif _daily_rate is not None and _daily_rate <= 0:
            kpi_card("Projected Date", "Not improving", color="#C62828")
        else:
            kpi_card("Projected Date", "—")

    st.markdown("---")
    sec("Daily Open Incidents — Net Remaining")

    _fig_bl = go.Figure()
    _fig_bl.add_trace(go.Scatter(
        x=[_days[0], _days[-1]],
        y=[_actual["Remaining"].iloc[0] if len(_actual) else _bl_target, _bl_target],
        mode="lines", name=f"Target ({_bl_target:,})",
        line=dict(color="#4CAF50", width=2, dash="dot"),
    ))
    if len(_forecast_df) > 1:
        _fig_bl.add_trace(go.Scatter(
            x=_forecast_df["Date"], y=_forecast_df["Forecast"],
            mode="lines", name="Trend (14-day)",
            line=dict(color=DXC_GREY_LIGHT, width=2, dash="dash"),
        ))
    _fig_bl.add_trace(go.Scatter(
        x=_actual["Date"], y=_actual["Remaining"],
        mode="lines+markers", name="Actual Open",
        line=dict(color=DXC_PURPLE_LITE, width=3),
        marker=dict(size=4),
        fill="tozeroy", fillcolor="rgba(109,32,119,0.10)",
        hovertemplate="%{x|%d %b}<br>Open: %{y:,}<extra></extra>",
    ))
    if len(_actual):
        _today_x = str(_actual["Date"].iloc[-1].date())
        _fig_bl.add_shape(type="line", x0=_today_x, x1=_today_x,
                          y0=0, y1=1, yref="paper",
                          line=dict(color=DXC_GREY, width=1, dash="dash"))
        _fig_bl.add_annotation(x=_today_x, y=1, yref="paper",
                               text="Today", showarrow=False,
                               font=dict(color=DXC_GREY_LIGHT, size=11),
                               xanchor="left", yanchor="top")
    _fig_bl.update_layout(**{
        **CHART_THEME, "height": 420,
        "yaxis": dict(title="Open Incidents", gridcolor=_GRID),
        "hovermode": "x unified",
        "legend": dict(orientation="h", y=1.05, x=0),
    })
    chart(_fig_bl)

    st.markdown("---")
    sec("Daily Opened vs Closed")
    _fig_oc = go.Figure()
    _fig_oc.add_trace(go.Bar(
        x=_actual["Date"], y=_actual["Opened"],
        name="Opened", marker_color="#C62828", opacity=0.85,
    ))
    _fig_oc.add_trace(go.Bar(
        x=_actual["Date"], y=-_actual["Closed"],
        name="Closed", marker_color="#4CAF50", opacity=0.85,
    ))
    _fig_oc.update_layout(**{
        **CHART_THEME, "barmode": "relative", "height": 280,
        "yaxis": dict(title="Tickets", gridcolor=_GRID),
        "hovermode": "x unified",
        "legend": dict(orientation="h", y=1.05, x=0),
    })
    chart(_fig_oc)

    st.markdown("---")
    sec("By Assignee")
    _bl_open_now    = _bl_df[
        (_bl_df["created"] <= _today_ts) &
        (~_bl_df["_is_closed"] | (_bl_df["_resolved_at"] > _today_ts))
    ].copy()
    _bl_closed_period = _bl_df[
        _bl_df["_resolved_at"].notna() &
        (_bl_df["_resolved_at"] >= _start_ts) &
        (_bl_df["_resolved_at"] <= _today_ts)
    ].copy()

    _col_open, _col_closed = st.columns(2)
    with _col_open:
        st.caption(f"Currently open — {len(_bl_open_now):,} incidents")
        _open_by = (_bl_open_now.groupby("assignee", dropna=True).size()
                    .reset_index(name="open").sort_values("open", ascending=False).head(15))
        _fig_op = go.Figure(go.Bar(
            x=_open_by["open"], y=_open_by["assignee"], orientation="h",
            marker_color=DXC_PURPLE_LITE,
            text=_open_by["open"], textposition="outside",
        ))
        _fig_op.update_layout(**{**CHART_THEME, "height": 440,
                                 "xaxis": dict(gridcolor=_GRID),
                                 "yaxis": dict(autorange="reversed"),
                                 "margin": dict(t=10, b=10, l=10, r=60)})
        chart(_fig_op)

    with _col_closed:
        st.caption(f"Closed in period — {len(_bl_closed_period):,} incidents")
        _closed_by = (_bl_closed_period.groupby("assignee", dropna=True).size()
                      .reset_index(name="closed").sort_values("closed", ascending=False).head(15))
        _fig_cl = go.Figure(go.Bar(
            x=_closed_by["closed"], y=_closed_by["assignee"], orientation="h",
            marker_color="#4CAF50",
            text=_closed_by["closed"], textposition="outside",
        ))
        _fig_cl.update_layout(**{**CHART_THEME, "height": 440,
                                 "xaxis": dict(gridcolor=_GRID),
                                 "yaxis": dict(autorange="reversed"),
                                 "margin": dict(t=10, b=10, l=10, r=60)})
        chart(_fig_cl)

    st.markdown("---")
    _col_age, _col_prio = st.columns(2)
    with _col_age:
        sec("Age of Open Tickets")
        _bl_open_now["_age_days"] = (_today_ts - _bl_open_now["created"]).dt.days
        _bins = [0, 7, 30, 60, 90, 180, 9999]
        _lbls = ["< 1 week", "1–4 weeks", "1–2 months", "2–3 months", "3–6 months", "> 6 months"]
        _bl_open_now["_age_bucket"] = pd.cut(_bl_open_now["_age_days"], bins=_bins, labels=_lbls, right=False)
        _age_c = _bl_open_now.groupby("_age_bucket", observed=True).size().reset_index(name="count")
        _age_colors = ["#4CAF50", DXC_PURPLE_LITE, "#E65100", "#C62828", "#7B1FA2", "#37474F"]
        _fig_age = go.Figure(go.Bar(
            x=_age_c["_age_bucket"].astype(str), y=_age_c["count"],
            marker_color=_age_colors[:len(_age_c)],
            text=_age_c["count"], textposition="outside",
        ))
        _fig_age.update_layout(**{**CHART_THEME, "height": 300, "yaxis": dict(gridcolor=_GRID)})
        chart(_fig_age)

    with _col_prio:
        sec("Open Tickets by Priority")
        _prio_c = (_bl_open_now.groupby("priority", dropna=True).size()
                   .reset_index(name="count").sort_values("count", ascending=True))
        _pcmap  = {"Critical": "#C62828", "High": "#E65100",
                   "Medium": DXC_PURPLE_LITE, "Low": DXC_GREY}
        _fig_pr = go.Figure(go.Bar(
            x=_prio_c["count"], y=_prio_c["priority"], orientation="h",
            marker_color=[_pcmap.get(p, DXC_GREY) for p in _prio_c["priority"]],
            text=_prio_c["count"], textposition="outside",
        ))
        _fig_pr.update_layout(**{**CHART_THEME, "height": 300,
                                 "xaxis": dict(gridcolor=_GRID),
                                 "margin": dict(t=10, b=10, l=10, r=60)})
        chart(_fig_pr)

    with st.expander("Daily breakdown table"):
        _tbl_df = _actual[["Date", "Remaining", "Opened", "Closed"]].copy()
        _tbl_df["Net"]  = _tbl_df["Closed"] - _tbl_df["Opened"]
        _tbl_df["Date"] = _tbl_df["Date"].dt.strftime("%Y-%m-%d")
        st.dataframe(_tbl_df.sort_values("Date", ascending=False),
                     use_container_width=True, hide_index=True)

    st.markdown("---")
    sec("Export to Database")
    st.caption(
        "Saves the daily backlog burndown series to the **backlog_burndown** table — "
        "connect this in PowerBI for the production incident burndown chart."
    )
    if st.button("Save Backlog Burndown to DB", type="primary", key="save_backlog_db"):
        with st.spinner("Saving…"):
            try:
                _n = materialise_backlog_burndown(
                    _engine(),
                    track_from=_bl_start,
                    track_to=_bl_end,
                    target=int(_bl_target),
                )
                st.success(f"Saved — {_n} daily rows written to backlog_burndown.")
            except Exception as _ex:
                st.error(f"DB write failed: {_ex}")
