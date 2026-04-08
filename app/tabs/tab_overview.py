"""
Overview tab — KPI banner and top-level charts.
"""
import pandas as pd
import plotly.express as px
import streamlit as st

from app.components import (
    kpi_card, sec, chart, shorten,
    DXC_PURPLE, DXC_PURPLE_LITE, DXC_GREY_LIGHT, DXC_GREY,
    DXC_PALETTE, PRIORITY_COLORS,
)


def render(df: pd.DataFrame):
    total      = len(df)
    n_resolved = int(df["is_resolved"].sum()) if "is_resolved" in df else 0
    n_open     = total - n_resolved
    n_critical = int((df["priority"] == "Critical").sum())
    avg_days   = pd.to_numeric(df["resolution_days"], errors="coerce").mean() \
                 if "resolution_days" in df else 0

    sla_df  = df[df.get("sla_justified", pd.Series()).isin(["Yes", "No"])] \
              if "sla_justified" in df.columns else pd.DataFrame()
    sla_pct = (sla_df["sla_justified"] == "Yes").sum() / len(sla_df) * 100 \
              if len(sla_df) > 0 else 0
    res_rate = n_resolved / total * 100

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1: kpi_card("Total Issues",   f"{total:,}")
    with c2: kpi_card("Open",           f"{n_open:,}",           color="#E65100")
    with c3: kpi_card("Resolved",       f"{n_resolved:,}",       color=DXC_PURPLE_LITE,
                      sub=f"{res_rate:.1f}% resolution rate")
    with c4: kpi_card("Critical",       f"{n_critical:,}",       color="#C62828")
    with c5: kpi_card("SLA Met",        f"{sla_pct:.1f}%",
                      color=DXC_PURPLE_LITE if sla_pct >= 80 else DXC_GREY_LIGHT,
                      sub=f"from {len(sla_df):,} evaluated")
    with c6: kpi_card("Avg Resolution", f"{avg_days:.1f}d",      color=DXC_PURPLE_LITE)

    st.markdown("---")

    r1c1, r1c2 = st.columns(2)
    with r1c1:
        sec("Issues by Type")
        counts = df["issue_type"].value_counts().reset_index()
        counts.columns = ["Type", "Count"]
        fig = px.pie(counts, values="Count", names="Type", hole=0.42,
                     color_discrete_sequence=DXC_PALETTE)
        fig.update_traces(textposition="inside", textinfo="percent+label")
        fig.update_layout(showlegend=False)
        chart(fig)

    with r1c2:
        sec("Issues by Priority")
        pri = (df["priority"].value_counts()
               .reindex(["Critical", "High", "Medium", "Low"]).dropna()
               .reset_index())
        pri.columns = ["Priority", "Count"]
        fig = px.bar(pri, x="Priority", y="Count", color="Priority",
                     color_discrete_map=PRIORITY_COLORS, text="Count")
        fig.update_traces(textposition="outside")
        fig.update_layout(showlegend=False)
        chart(fig)

    r2c1, r2c2 = st.columns(2)
    with r2c1:
        sec("Top 10 Statuses")
        stat = df["status"].value_counts().head(10).reset_index()
        stat.columns = ["Status", "Count"]
        fig = px.bar(stat, x="Count", y="Status", orientation="h",
                     color="Count", color_continuous_scale=[[0, "#1F1F1F"], [1, "#6D2077"]],
                     text="Count")
        fig.update_traces(textposition="outside")
        fig.update_layout(yaxis=dict(autorange="reversed"), coloraxis_showscale=False)
        chart(fig)

    with r2c2:
        sec("Issues by Project")
        proj = df["project"].value_counts().reset_index()
        proj.columns = ["Project", "Count"]
        proj["Project"] = proj["Project"].apply(lambda s: shorten(s, 45))
        fig = px.bar(proj, x="Count", y="Project", orientation="h",
                     color="Count", color_continuous_scale=[[0, "#1F1F1F"], [1, "#9B26AF"]],
                     text="Count")
        fig.update_traces(textposition="outside")
        fig.update_layout(yaxis=dict(autorange="reversed"), coloraxis_showscale=False)
        chart(fig)
