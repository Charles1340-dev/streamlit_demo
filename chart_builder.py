from __future__ import annotations

from typing import Any, Dict

import pandas as pd
import plotly.express as px


PLOT_TEMPLATE = "plotly_white"
TEN_THOUSAND = 10000
HUNDRED_MILLION = 100000000


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


def _pick_display_unit(series: pd.Series) -> tuple[float, str]:
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return 1.0, ""
    max_abs = float(numeric.abs().max())
    if max_abs >= HUNDRED_MILLION:
        return float(HUNDRED_MILLION), "亿"
    if max_abs >= TEN_THOUSAND:
        return float(TEN_THOUSAND), "万"
    return 1.0, ""


def _scale_series(series: pd.Series, scale: float) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if scale == 1.0:
        return numeric.round(2)
    return (numeric / scale).round(2)


def _prepare_chart_dataframe(df: pd.DataFrame, chart_spec: Dict[str, Any]) -> tuple[pd.DataFrame, Dict[str, str]]:
    prepared = df.copy()
    chart_type = chart_spec.get("type")
    x_field = chart_spec.get("x_field")
    y_fields = chart_spec.get("y_fields") or []
    y_field = chart_spec.get("y_field")
    metric = chart_spec.get("metric")
    unit_map: Dict[str, str] = {}

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
        scale, unit = _pick_display_unit(prepared[column])
        prepared[column] = _scale_series(prepared[column], scale)
        unit_map[column] = unit

    return prepared, unit_map


def _apply_axis_labels(fig, chart_type: str, chart_spec: Dict[str, Any], unit_map: Dict[str, str]) -> None:
    x_field = chart_spec.get("x_field")
    y_field = chart_spec.get("y_field")
    metric = chart_spec.get("metric")
    y_fields = chart_spec.get("y_fields") or []

    def with_unit(label: str | None, unit: str) -> str | None:
        if not label:
            return None
        return f"{label}（{unit}）" if unit else label

    if chart_type in {"bar", "line", "area", "funnel"}:
        primary_field = y_fields[0] if y_fields else None
        fig.update_yaxes(title_text=with_unit("数值", unit_map.get(primary_field or "", "")) or "数值")
    elif chart_type == "scatter":
        fig.update_xaxes(title_text=with_unit(x_field or "横轴", unit_map.get(x_field or "", "")) or "横轴")
        fig.update_yaxes(title_text=with_unit(y_field or "数值", unit_map.get(y_field or "", "")) or "数值")
    elif chart_type == "histogram":
        fig.update_xaxes(title_text=with_unit(metric or "数值", unit_map.get(metric or "", "")) or "数值")
    elif chart_type == "box":
        if chart_spec.get("dimension"):
            fig.update_yaxes(title_text=with_unit(metric or "数值", unit_map.get(metric or "", "")) or "数值")
        else:
            fig.update_yaxes(title_text=with_unit("数值", unit_map.get(metric or "", "")) or "数值")


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
    df, unit_map = _prepare_chart_dataframe(pd.DataFrame(table), chart_spec)

    if chart_type in {"bar", "line", "area", "pie", "funnel", "treemap"} and df.empty:
        return _apply_common_layout(px.scatter(title=f"{title}（暂无数据）"))

    if chart_type == "pie":
        x_field = chart_spec.get("x_field")
        y_fields = chart_spec.get("y_fields") or []
        value_field = y_fields[0] if y_fields else None
        fig = px.pie(df, names=x_field, values=value_field, title=title)
        value_unit = unit_map.get(value_field or "", "")
        value_suffix = value_unit if value_unit else ""
        fig.update_traces(textposition="inside", texttemplate=f"%{{label}}<br>%{{value:.2f}}{value_suffix}")
        return _apply_common_layout(fig)

    if chart_type == "treemap":
        x_field = chart_spec.get("x_field")
        y_fields = chart_spec.get("y_fields") or []
        value_field = y_fields[0] if y_fields else None
        fig = px.treemap(df, path=[px.Constant("全部"), x_field], values=value_field, title=title)
        value_unit = unit_map.get(value_field or "", "")
        value_suffix = value_unit if value_unit else ""
        fig.update_traces(texttemplate=f"%{{label}}<br>%{{value:.2f}}{value_suffix}")
        return _apply_common_layout(fig)

    if chart_type == "funnel":
        x_field = chart_spec.get("x_field")
        y_fields = chart_spec.get("y_fields") or []
        value_field = y_fields[0] if y_fields else None
        fig = px.funnel(df, y=x_field, x=value_field, title=title)
        _apply_axis_labels(fig, chart_type, chart_spec, unit_map)
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
        _apply_axis_labels(fig, chart_type, chart_spec, unit_map)
        return _apply_common_layout(fig)

    if chart_type == "scatter":
        if df.empty:
            return _apply_common_layout(px.scatter(title=f"{title}（暂无数据）"))
        x_field = chart_spec.get("x_field")
        y_field = chart_spec.get("y_field")
        label_field = chart_spec.get("label_field")
        fig = px.scatter(df, x=x_field, y=y_field, hover_name=label_field, title=title)
        _apply_axis_labels(fig, chart_type, chart_spec, unit_map)
        return _apply_common_layout(fig)

    if chart_type == "histogram":
        metric = chart_spec.get("metric")
        fig = px.histogram(df, x=metric, nbins=30, title=title)
        _apply_axis_labels(fig, chart_type, chart_spec, unit_map)
        return _apply_common_layout(fig)

    if chart_type == "box":
        metric = chart_spec.get("metric")
        dimension = chart_spec.get("dimension")
        if dimension and dimension in df.columns:
            fig = px.box(df, x=dimension, y=metric, title=title)
        else:
            fig = px.box(df, y=metric, title=title)
        _apply_axis_labels(fig, chart_type, chart_spec, unit_map)
        return _apply_common_layout(fig)

    fig = px.bar(title=f"{title}（暂不支持的图表类型，已降级为柱图）")
    return _apply_common_layout(fig)
