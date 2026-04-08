"""
SLA & KPIs tab.
"""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.components import (
    kpi_card, sec, chart,
    DXC_PURPLE, DXC_PURPLE_LITE, DXC_GREY_LIGHT,
    PRIORITY_COLORS, CHART_THEME, _GRID,
)


def render(df: pd.DataFrame):
    sla_yes = int((df["sla_justified"] == "Yes").sum()) if "sla_justified" in df else 0
    sla_no  = int((df["sla_justified"] == "No").sum())  if "sla_justified" in df else 0
    sla_tot = sla_yes + sla_no
    sla_pct = sla_yes / sla_tot * 100 if sla_tot > 0 else 0

    kc1, kc2, kc3, kc4 = st.columns(4)
    with kc1: kpi_card("SLA Met",      f"{sla_yes:,}",    color=DXC_PURPLE_LITE)
    with kc2: kpi_card("SLA Breached", f"{sla_no:,}",     color="#C62828")
    with kc3: kpi_card("Compliance",   f"{sla_pct:.1f}%",
                       color=DXC_PURPLE_LITE if sla_pct >= 80 else DXC_GREY_LIGHT,
                       sub=f"based on {sla_tot:,} evaluated")
    with kc4:
        avg_r = pd.to_numeric(df["resolution_days"], errors="coerce").median() \
                if "resolution_days" in df else 0
        kpi_card("Median Resolution", f"{avg_r:.1f}d", color=DXC_PURPLE_LITE)

    st.markdown("---")
    c1, c2 = st.columns(2)

    with c1:
        sec("SLA Compliance by Issue Type")
        if "sla_justified" in df.columns:
            sla_t = (df[df["sla_justified"].isin(["Yes", "No"])]
                     .groupby(["issue_type", "sla_justified"])
                     .size().reset_index(name="Count"))
            fig = px.bar(sla_t, x="issue_type", y="Count", color="sla_justified",
                         color_discrete_map={"Yes": "#6D2077", "No": "#A0A4A8"},
                         barmode="stack")
            chart(fig)

    with c2:
        sec("SLA Compliance by Priority")
        if "sla_justified" in df.columns:
            sla_p = (df[df["sla_justified"].isin(["Yes", "No"])]
                     .groupby(["priority", "sla_justified"])
                     .size().reset_index(name="Count"))
            fig = px.bar(sla_p, x="priority", y="Count", color="sla_justified",
                         color_discrete_map={"Yes": "#6D2077", "No": "#A0A4A8"},
                         barmode="group",
                         category_orders={"priority": ["Critical", "High", "Medium", "Low"]})
            chart(fig)

    sec("Resolution Time Distribution (days)")
    if "resolution_days" in df.columns:
        df["resolution_days"] = pd.to_numeric(df["resolution_days"], errors="coerce")
        res_d = df[df["resolution_days"].between(0, 365, inclusive="right")].copy()
        if not res_d.empty:
            fig = px.histogram(res_d, x="resolution_days", nbins=60,
                               color="priority",
                               color_discrete_map=PRIORITY_COLORS,
                               marginal="box", opacity=0.85)
            fig.update_layout(bargap=0.05)
            chart(fig)

    kpi_minute_cols = [c for c in df.columns if c.endswith("_minutes") and "kpi" in c]
    if kpi_minute_cols:
        sec("KPI Time Summary")
        rows = []
        for col in kpi_minute_cols:
            label = (col.replace("kpi_", "").replace("_minutes", "").replace("_", " ").title())
            vals    = df[col].dropna()
            on_time = int((vals >= 0).sum())
            breached= int((vals < 0).sum())
            ok_vals = vals[vals >= 0]
            avg_h   = f"{ok_vals.mean() / 60:.1f}h" if len(ok_vals) > 0 else "—"
            med_h   = f"{ok_vals.median() / 60:.1f}h" if len(ok_vals) > 0 else "—"
            rows.append({"KPI": label, "On Time": on_time, "Breached": breached,
                         "Avg (On Time)": avg_h, "Median (On Time)": med_h})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        solve_col = "kpi_time_to_solve_minutes"
        if solve_col in df.columns:
            sec("KPI Time to Solve — On-time Rate")
            vals = df[solve_col].dropna()
            on   = int((vals >= 0).sum())
            tot  = len(vals)
            pct  = on / tot * 100 if tot > 0 else 0
            fig = go.Figure(go.Indicator(
                mode="gauge+number",
                value=pct,
                number={"suffix": "%", "font": {"color": DXC_PURPLE_LITE, "size": 48}},
                gauge=dict(
                    axis=dict(range=[0, 100], tickfont=dict(color="#cfd8dc")),
                    bar=dict(color=DXC_PURPLE),
                    steps=[
                        dict(range=[0, 60],   color="#1F1F1F"),
                        dict(range=[60, 80],  color="#2A1A2E"),
                        dict(range=[80, 100], color="#3D1142"),
                    ],
                    threshold=dict(line=dict(color=DXC_PURPLE_LITE, width=3), value=80),
                ),
            ))
            fig.update_layout(height=280, **CHART_THEME)
            st.plotly_chart(fig, use_container_width=True)
