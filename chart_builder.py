from __future__ import annotations

from typing import Any, Dict

import pandas as pd
import plotly.express as px



def build_plotly_figure(chart_spec: Dict[str, Any]):
    chart_type = chart_spec.get("type")
    title = chart_spec.get("title", "图表")
    table = chart_spec.get("table", [])
    df = pd.DataFrame(table)

    if chart_type in {"bar", "line", "area", "pie", "funnel", "treemap"} and df.empty:
        return px.scatter(title=f"{title}（暂无数据）")

    if chart_type == "pie":
        x_field = chart_spec.get("x_field")
        y_fields = chart_spec.get("y_fields") or []
        value_field = y_fields[0] if y_fields else None
        fig = px.pie(df, names=x_field, values=value_field, title=title)
        fig.update_layout(margin=dict(l=10, r=10, t=50, b=10))
        return fig

    if chart_type == "treemap":
        x_field = chart_spec.get("x_field")
        y_fields = chart_spec.get("y_fields") or []
        value_field = y_fields[0] if y_fields else None
        fig = px.treemap(df, path=[px.Constant("全部"), x_field], values=value_field, title=title)
        fig.update_layout(margin=dict(l=10, r=10, t=50, b=10))
        return fig

    if chart_type == "funnel":
        x_field = chart_spec.get("x_field")
        y_fields = chart_spec.get("y_fields") or []
        value_field = y_fields[0] if y_fields else None
        fig = px.funnel(df, y=x_field, x=value_field, title=title)
        fig.update_layout(margin=dict(l=10, r=10, t=50, b=10))
        return fig

    if chart_type in {"bar", "line", "area"}:
        x_field = chart_spec.get("x_field")
        y_fields = chart_spec.get("y_fields") or []
        if len(y_fields) > 1:
            long_df = df.melt(id_vars=[x_field], value_vars=y_fields, var_name="系列", value_name="值")
            if chart_type == "bar":
                fig = px.bar(long_df, x=x_field, y="值", color="系列", barmode="group", title=title)
            elif chart_type == "area":
                fig = px.area(long_df, x=x_field, y="值", color="系列", title=title)
            else:
                fig = px.line(long_df, x=x_field, y="值", color="系列", markers=True, title=title)
        else:
            y_field = y_fields[0] if y_fields else None
            if chart_type == "bar":
                fig = px.bar(df, x=x_field, y=y_field, title=title)
            elif chart_type == "area":
                fig = px.area(df, x=x_field, y=y_field, title=title)
            else:
                fig = px.line(df, x=x_field, y=y_field, markers=True, title=title)
        fig.update_layout(margin=dict(l=10, r=10, t=50, b=10))
        return fig

    if chart_type == "scatter":
        if df.empty:
            return px.scatter(title=f"{title}（暂无数据）")
        x_field = chart_spec.get("x_field")
        y_field = chart_spec.get("y_field")
        label_field = chart_spec.get("label_field")
        fig = px.scatter(df, x=x_field, y=y_field, hover_name=label_field, title=title)
        fig.update_layout(margin=dict(l=10, r=10, t=50, b=10))
        return fig

    if chart_type == "histogram":
        metric = chart_spec.get("metric")
        fig = px.histogram(df, x=metric, nbins=30, title=title)
        fig.update_layout(margin=dict(l=10, r=10, t=50, b=10))
        return fig

    if chart_type == "box":
        metric = chart_spec.get("metric")
        dimension = chart_spec.get("dimension")
        if dimension and dimension in df.columns:
            fig = px.box(df, x=dimension, y=metric, title=title)
        else:
            fig = px.box(df, y=metric, title=title)
        fig.update_layout(margin=dict(l=10, r=10, t=50, b=10))
        return fig

    fig = px.bar(title=f"{title}（暂不支持的图表类型，已降级为柱图）")
    fig.update_layout(margin=dict(l=10, r=10, t=50, b=10))
    return fig
