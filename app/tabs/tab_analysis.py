"""
Analysis tab — assignee, root cause, environment, product line, priority matrix.
"""
import pandas as pd
import plotly.express as px
import streamlit as st

from app.components import (
    sec, chart,
    DXC_PURPLE, DXC_PALETTE,
)


def render(df: pd.DataFrame):
    c1, c2 = st.columns(2)

    with c1:
        sec("Top 15 Assignees by Volume")
        top_a = df["assignee"].value_counts().head(15).reset_index()
        top_a.columns = ["Assignee", "Count"]
        fig = px.bar(top_a, x="Count", y="Assignee", orientation="h",
                     color="Count", color_continuous_scale=[[0, "#1F1F1F"], [1, "#6D2077"]],
                     text="Count")
        fig.update_traces(textposition="outside")
        fig.update_layout(yaxis=dict(autorange="reversed"), coloraxis_showscale=False)
        chart(fig)

    with c2:
        if "root_cause_origin" in df.columns:
            sec("Root Cause Origin")
            rco = df["root_cause_origin"].dropna().value_counts().reset_index()
            rco.columns = ["Root Cause", "Count"]
            fig = px.pie(rco, values="Count", names="Root Cause", hole=0.38,
                         color_discrete_sequence=DXC_PALETTE)
            fig.update_traces(textposition="inside", textinfo="percent+label")
            fig.update_layout(showlegend=False)
            chart(fig)

    c3, c4 = st.columns(2)

    with c3:
        if "environment_type" in df.columns:
            sec("Production vs Non-Production")
            env = df["environment_type"].value_counts().reset_index()
            env.columns = ["Environment", "Count"]
            fig = px.bar(env, x="Environment", y="Count", color="Environment",
                         color_discrete_sequence=[DXC_PURPLE, "#6D7278"], text="Count")
            fig.update_traces(textposition="outside")
            fig.update_layout(showlegend=False)
            chart(fig)

    with c4:
        if "product_line" in df.columns:
            sec("Product Line Distribution")
            pl = df["product_line"].dropna().value_counts().reset_index()
            pl.columns = ["Product Line", "Count"]
            fig = px.pie(pl, values="Count", names="Product Line", hole=0.4,
                         color_discrete_sequence=DXC_PALETTE)
            fig.update_traces(textposition="inside", textinfo="percent+label")
            fig.update_layout(showlegend=True)
            chart(fig)

    sec("Priority × Issue Type Matrix")
    pivot = (df.groupby(["priority", "issue_type"]).size()
               .unstack(fill_value=0)
               .reindex([p for p in ["Critical", "High", "Medium", "Low"]
                         if p in df["priority"].values]))
    fig = px.imshow(pivot, color_continuous_scale=[[0, "#1F1F1F"], [1, "#6D2077"]],
                    aspect="auto", text_auto=True)
    fig.update_layout(xaxis=dict(title="Issue Type"), yaxis=dict(title="Priority"))
    chart(fig)

    if "resolution_owner" in df.columns:
        sec("Resolution Owner Split")
        ro = df["resolution_owner"].dropna().value_counts().reset_index()
        ro.columns = ["Owner", "Count"]
        fig = px.bar(ro, x="Owner", y="Count", color="Owner",
                     color_discrete_sequence=[DXC_PURPLE, "#6D7278"], text="Count")
        fig.update_traces(textposition="outside")
        fig.update_layout(showlegend=False)
        chart(fig)
