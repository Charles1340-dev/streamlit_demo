from __future__ import annotations

from typing import Any, Dict

import pandas as pd
import plotly.express as px


PLOT_TEMPLATE = "plotly_white"
TEN_THOUSAND = 10000


def _is_numeric_like(series: pd.Series) -> bool:
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric.notna().mean() >= 0.8 if len(series) else False


def _looks_like_date_field(field_name: str | None, series: pd.Series) -> bool:
    if not field_name:
        return False
    lowered = field_name.lower()
    if any(keyword in lowered for keyword in ["日期", "时间", "月份", "年月", "date", "time", "month", "day", "year"]):
        return True
    sample = series.dropna().head(8)
    if sample.empty:
        return False
    parsed = pd.to_datetime(sample.astype(str), errors="coerce")
    return parsed.notna().mean() >= 0.75


def _to_chinese_date_text(value: Any) -> Any:
    if value is None or value == "":
        return value
    text = str(value).strip()
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return value
    if len(text) <= 7:
        return parsed.strftime("%Y年%m月")
    if any(token in text for token in [":", "T"]):
        return parsed.strftime("%Y年%m月%d日 %H:%M")
    return parsed.strftime("%Y年%m月%d日")


def _format_numeric_in_ten_thousand(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    return (numeric / TEN_THOUSAND).round(2)


def _prepare_chart_dataframe(df: pd.DataFrame, chart_spec: Dict[str, Any]) -> pd.DataFrame:
    prepared = df.copy()
    chart_type = chart_spec.get("type")
    x_field = chart_spec.get("x_field")
    y_fields = chart_spec.get("y_fields") or []
    y_field = chart_spec.get("y_field")
    metric = chart_spec.get("metric")

    if x_field and x_field in prepared.columns and _looks_like_date_field(x_field, prepared[x_field]):
        prepared[x_field] = prepared[x_field].map(_to_chinese_date_text)

    numeric_targets = {field for field in y_fields if field in prepared.columns}
    if y_field and y_field in prepared.columns:
        numeric_targets.add(y_field)
    if metric and metric in prepared.columns:
        numeric_targets.add(metric)
    if chart_type == "scatter" and x_field and x_field in prepared.columns and _is_numeric_like(prepared[x_field]):
        numeric_targets.add(x_field)

    for column in numeric_targets:
        prepared[column] = _format_numeric_in_ten_thousand(prepared[column])

    return prepared


def _apply_axis_labels(fig, chart_type: str, chart_spec: Dict[str, Any]) -> None:
    x_field = chart_spec.get("x_field")
    y_field = chart_spec.get("y_field")
    metric = chart_spec.get("metric")

    if chart_type in {"bar", "line", "area", "funnel"}:
        fig.update_yaxes(title_text="数值（万元）")
    elif chart_type == "scatter":
        fig.update_xaxes(title_text=f"{x_field}（万元）" if x_field else "横轴")
        fig.update_yaxes(title_text=f"{y_field}（万元）" if y_field else "数值（万元）")
    elif chart_type == "histogram":
        fig.update_xaxes(title_text=f"{metric}（万元）" if metric else "数值（万元）")
    elif chart_type == "box":
        if chart_spec.get("dimension"):
            fig.update_yaxes(title_text=f"{metric}（万元）" if metric else "数值（万元）")
        else:
            fig.update_yaxes(title_text="数值（万元）")


def _apply_common_layout(fig):
    fig.update_layout(
        template=PLOT_TEMPLATE,
        margin=dict(l=10, r=10, t=56, b=10),
        legend_title_text="",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def build_plotly_figure(chart_spec: Dict[str, Any]):
    chart_type = chart_spec.get("type")
    title = chart_spec.get("title", "图表")
    table = chart_spec.get("table", [])
    df = _prepare_chart_dataframe(pd.DataFrame(table), chart_spec)

    if chart_type in {"bar", "line", "area", "pie", "funnel", "treemap"} and df.empty:
        return _apply_common_layout(px.scatter(title=f"{title}（暂无数据）"))

    if chart_type == "pie":
        x_field = chart_spec.get("x_field")
        y_fields = chart_spec.get("y_fields") or []
        value_field = y_fields[0] if y_fields else None
        fig = px.pie(df, names=x_field, values=value_field, title=title)
        fig.update_traces(textposition="inside", texttemplate="%{label}<br>%{value:.2f}万")
        return _apply_common_layout(fig)

    if chart_type == "treemap":
        x_field = chart_spec.get("x_field")
        y_fields = chart_spec.get("y_fields") or []
        value_field = y_fields[0] if y_fields else None
        fig = px.treemap(df, path=[px.Constant("全部"), x_field], values=value_field, title=title)
        fig.update_traces(texttemplate="%{label}<br>%{value:.2f}万")
        return _apply_common_layout(fig)

    if chart_type == "funnel":
        x_field = chart_spec.get("x_field")
        y_fields = chart_spec.get("y_fields") or []
        value_field = y_fields[0] if y_fields else None
        fig = px.funnel(df, y=x_field, x=value_field, title=title)
        _apply_axis_labels(fig, chart_type, chart_spec)
        return _apply_common_layout(fig)

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
        _apply_axis_labels(fig, chart_type, chart_spec)
        return _apply_common_layout(fig)

    if chart_type == "scatter":
        if df.empty:
            return _apply_common_layout(px.scatter(title=f"{title}（暂无数据）"))
        x_field = chart_spec.get("x_field")
        y_field = chart_spec.get("y_field")
        label_field = chart_spec.get("label_field")
        fig = px.scatter(df, x=x_field, y=y_field, hover_name=label_field, title=title)
        _apply_axis_labels(fig, chart_type, chart_spec)
        return _apply_common_layout(fig)

    if chart_type == "histogram":
        metric = chart_spec.get("metric")
        fig = px.histogram(df, x=metric, nbins=30, title=title)
        _apply_axis_labels(fig, chart_type, chart_spec)
        return _apply_common_layout(fig)

    if chart_type == "box":
        metric = chart_spec.get("metric")
        dimension = chart_spec.get("dimension")
        if dimension and dimension in df.columns:
            fig = px.box(df, x=dimension, y=metric, title=title)
        else:
            fig = px.box(df, y=metric, title=title)
        _apply_axis_labels(fig, chart_type, chart_spec)
        return _apply_common_layout(fig)

    fig = px.bar(title=f"{title}（暂不支持的图表类型，已降级为柱图）")
    return _apply_common_layout(fig)
