"""
Trends tab — time series charts.
"""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.components import (
    sec, chart,
    DXC_PURPLE, DXC_PALETTE, CHART_THEME, _GRID,
)


def render(df: pd.DataFrame):
    df_d = df[df["created"].notna()].copy() if "created" in df.columns else df.copy()

    sec("Issues Created per Month")
    monthly = (df_d.groupby("created_yearmonth").size()
               .reset_index(name="Count")
               .sort_values("created_yearmonth"))
    fig = px.area(monthly, x="created_yearmonth", y="Count",
                  color_discrete_sequence=[DXC_PURPLE], markers=True)
    fig.update_layout(yaxis=dict(title="Issues", gridcolor=_GRID))
    chart(fig)

    c1, c2 = st.columns(2)

    with c1:
        sec("Created vs Resolved per Month")
        cr_m = df_d.groupby("created_yearmonth").size().reset_index(name="Created")
        if "resolved" in df.columns:
            df_r = df[df["resolved"].notna()].copy()
            df_r["ym"] = df_r["resolved"].dt.to_period("M").astype(str)
            res_m = df_r.groupby("ym").size().reset_index(name="Resolved")
            res_m.rename(columns={"ym": "created_yearmonth"}, inplace=True)
            merged = (cr_m.merge(res_m, on="created_yearmonth", how="outer")
                         .fillna(0).sort_values("created_yearmonth"))
        else:
            merged = cr_m.copy()
            merged["Resolved"] = 0

        fig = go.Figure([
            go.Bar(name="Created",  x=merged["created_yearmonth"], y=merged["Created"],
                   marker_color=DXC_PURPLE),
            go.Bar(name="Resolved", x=merged["created_yearmonth"], y=merged["Resolved"],
                   marker_color="#4A7C59"),
        ])
        fig.update_layout(barmode="group", **CHART_THEME)
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        sec("Issues by Day of Week")
        dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday",
                     "Friday", "Saturday", "Sunday"]
        df_d["dow"] = df_d["created"].dt.day_name()
        dow = (df_d["dow"].value_counts()
               .reindex(dow_order).fillna(0)
               .reset_index())
        dow.columns = ["Day", "Count"]
        fig = px.bar(dow, x="Day", y="Count",
                     color="Count", color_continuous_scale=[[0, "#1F1F1F"], [1, "#6D2077"]],
                     text="Count")
        fig.update_traces(textposition="outside")
        fig.update_layout(coloraxis_showscale=False)
        chart(fig)

    sec("Issue Type Mix Over Time")
    type_m = (df_d.groupby(["created_yearmonth", "issue_type"])
              .size().reset_index(name="Count")
              .sort_values("created_yearmonth"))
    fig = px.area(type_m, x="created_yearmonth", y="Count", color="issue_type",
                  color_discrete_sequence=DXC_PALETTE)
    chart(fig)
