from __future__ import annotations

import math
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

import pandas as pd


METRIC_SYNONYMS = {
    "收账": ["收账", "收款", "回款", "到账", "收/退款", "实收", "回笼"],
    "收入": ["收入", "营收", "确认收入", "销售额", "合同额", "计划收入", "签约"],
    "成本": ["成本", "费用", "支出"],
    "利润": ["利润", "毛利", "净利", "盈利"],
    "开票": ["开票", "发票"],
    "现金流": ["现金流", "净现金流"],
}

DIMENSION_SYNONYMS = {
    "部门": ["部门", "团队", "组织", "负责部门", "院", "公司"],
    "项目": ["项目", "项目编号", "项目名称"],
    "客户": ["客户", "客商", "客商类别", "单位"],
    "供应商": ["供应商", "分包商"],
}

CHART_KEYWORDS = {
    "bar": ["柱状图", "柱图", "条形图", "直方柱"],
    "line": ["折线图", "线图", "趋势图"],
    "pie": ["饼图", "环图", "占比图"],
    "scatter": ["散点图"],
    "area": ["面积图"],
    "histogram": ["直方图"],
    "box": ["箱线图", "盒须图"],
    "funnel": ["漏斗图"],
    "treemap": ["矩形树图", "树图"],
}

CN_NUM = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def _score_field(field: str, keywords: List[str]) -> float:
    low = field.lower()
    score = 0.0
    for kw in keywords:
        kw_low = kw.lower()
        if kw_low == low:
            score += 10
        elif kw_low in low:
            score += 5
        else:
            score += SequenceMatcher(None, kw_low, low).ratio()
    return score



def _resolve_field(name: Optional[str], fields: List[str]) -> Optional[str]:
    if not name or not fields:
        return None
    if name in fields:
        return name
    low_name = name.lower()
    for f in fields:
        if low_name == f.lower():
            return f
    for f in fields:
        if low_name in f.lower() or f.lower() in low_name:
            return f
    ranked = sorted(fields, key=lambda f: SequenceMatcher(None, low_name, f.lower()).ratio(), reverse=True)
    best = ranked[0] if ranked else None
    if best and SequenceMatcher(None, low_name, best.lower()).ratio() >= 0.45:
        return best
    return None



def _find_field_by_keywords(fields: List[str], keywords: List[str]) -> Optional[str]:
    if not fields:
        return None
    ranked = sorted(fields, key=lambda f: _score_field(f, keywords), reverse=True)
    return ranked[0] if ranked and _score_field(ranked[0], keywords) > 0 else None



def _rank_numeric_fields_for_domain(question: str, fields: List[str], keywords: List[str], domain: str) -> List[str]:
    modifiers = [k for k in ["计划", "累计", "确认", "含税", "不含税", "开票", "应收", "应付", "净", "毛利", "现金流"] if k in question]
    scored = []
    for field in fields:
        score = _score_field(field, keywords)
        for mod in modifiers:
            if mod in field:
                score += 3
        if domain == "收账":
            if any(k in field for k in ["收款", "回款", "收/退款", "到账", "实收"]):
                score += 10
            if any(k in field for k in ["应收", "未收款"]):
                score -= 6
        if domain == "收入" and "计划" in question and "计划" in field:
            score += 8
        if domain == "收入" and "确认" in question and "确认" in field:
            score += 6
        if domain == "成本" and "成本" in field:
            score += 8
        if domain == "利润" and any(k in field for k in ["利润", "毛利", "净利"]):
            score += 8
        scored.append((field, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [field for field, _ in scored]



def _pick_metric(question: str, profile: Dict[str, Any]) -> Optional[str]:
    fields = profile["numeric_fields"]
    if not fields:
        return None
    for domain, kws in METRIC_SYNONYMS.items():
        if any(kw in question for kw in kws):
            ranked = _rank_numeric_fields_for_domain(question, fields, kws, domain)
            if ranked:
                return ranked[0]
    return fields[0]



def _pick_metrics(question: str, profile: Dict[str, Any]) -> List[str]:
    fields = profile["numeric_fields"]
    if not fields:
        return []

    picked: List[str] = []
    for domain, kws in METRIC_SYNONYMS.items():
        if any(kw in question for kw in kws):
            ranked = _rank_numeric_fields_for_domain(question, fields, kws, domain)
            if ranked:
                best = ranked[0]
                if best not in picked:
                    picked.append(best)

    # 含税 / 不含税 双指标场景
    if "含税" in question and ("不含税" in question or "不含" in question):
        base_field = picked[0] if picked else _pick_metric(question, profile)
        if base_field:
            tax_kw = [k for k in ["计划", "累计", "确认", "收入", "成本", "收款", "回款", "利润"] if k in base_field or k in question]
            tax_candidates = [f for f in fields if "含税" in f]
            non_tax_candidates = [f for f in fields if "不含税" in f]
            if tax_candidates:
                tax_best = _find_field_by_keywords(tax_candidates, tax_kw or [base_field])
                if tax_best and tax_best not in picked:
                    picked.append(tax_best)
            if non_tax_candidates:
                non_tax_best = _find_field_by_keywords(non_tax_candidates, tax_kw or [base_field])
                if non_tax_best and non_tax_best not in picked:
                    picked.append(non_tax_best)

    if not picked:
        picked.append(fields[0])
    return picked[:3]



def _pick_dimension(question: str, profile: Dict[str, Any]) -> Optional[str]:
    fields = profile["categorical_fields"] + profile["text_fields"]
    if not fields:
        return None
    for _, kws in DIMENSION_SYNONYMS.items():
        if any(kw in question for kw in kws):
            field = _find_field_by_keywords(fields, kws)
            if field:
                return field
    return fields[0]



def _pick_time_field(question: str, profile: Dict[str, Any]) -> Optional[str]:
    if not profile["date_fields"]:
        return None
    for field in profile["date_fields"]:
        if any(k in field for k in ["收", "回款", "开票", "收入", "确认"]):
            if any(k in question for k in ["趋势", "按月", "按天", "按年", "时间", "月份", "年度", "季度"]):
                return field
    return profile["date_fields"][0]



def _request_all_categories(question: str) -> bool:
    all_keywords = [
        "所有", "全部", "全量", "完整", "全部门", "所有部门", "全部项目", "所有项目",
        "全部数据", "所有数据", "查看全部", "全部信息", "所有信息", "统计所有"
    ]
    return any(kw in question for kw in all_keywords)



def _extract_top_n(question: str, default: Optional[int] = None) -> Optional[int]:
    m = re.search(r"前\s*(\d+)", question)
    if m:
        return max(1, int(m.group(1)))
    m = re.search(r"top\s*(\d+)", question.lower())
    if m:
        return max(1, int(m.group(1)))
    m = re.search(r"前([一二三四五六七八九十])", question)
    if m:
        return CN_NUM.get(m.group(1), default or 10)
    if _request_all_categories(question):
        return None
    return default



def _extract_chart_types(question: str) -> List[str]:
    found: List[str] = []
    for chart_type, kws in CHART_KEYWORDS.items():
        if any(kw in question for kw in kws):
            found.append(chart_type)
    return found



def _pick_sort_order(question: str) -> str:
    if any(k in question for k in ["最低", "最差", "最小", "倒数", "最后"]):
        return "asc"
    return "desc"



def _normalize_chart_plan(chart: Dict[str, Any], profile: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
    all_fields = profile["all_fields"]
    numeric_fields = profile["numeric_fields"]
    date_fields = profile["date_fields"]
    dim_fields = profile["categorical_fields"] + profile["text_fields"]

    normalized = dict(chart)
    normalized["type"] = chart.get("type", "bar")
    normalized["dimension"] = _resolve_field(chart.get("dimension") or plan.get("dimension"), dim_fields)
    normalized["metric"] = _resolve_field(chart.get("metric") or plan.get("metric"), numeric_fields)
    metrics = chart.get("metrics") or plan.get("metrics") or []
    normalized["metrics"] = [_resolve_field(m, numeric_fields) for m in metrics]
    normalized["metrics"] = [m for m in normalized["metrics"] if m]
    if normalized["metric"] and normalized["metric"] not in normalized["metrics"]:
        normalized["metrics"] = [normalized["metric"]] + normalized["metrics"]
    normalized["time_field"] = _resolve_field(chart.get("time_field") or plan.get("time_field"), date_fields)
    normalized["x_metric"] = _resolve_field(chart.get("x_metric"), numeric_fields)
    normalized["y_metric"] = _resolve_field(chart.get("y_metric"), numeric_fields)
    normalized["label_field"] = _resolve_field(chart.get("label_field") or normalized.get("dimension"), all_fields)
    raw_top_n = chart.get("top_n", plan.get("top_n"))
    normalized["top_n"] = int(raw_top_n) if raw_top_n not in (None, "", 0, "0") else None
    plan_subject = str(plan.get("subject") or "")
    if chart.get("return_all") or plan.get("return_all") or (_request_all_categories(plan_subject) and _extract_top_n(plan_subject, default=None) is None):
        if normalized["type"] not in {"scatter", "box"}:
            normalized["top_n"] = None
    normalized["sort_order"] = chart.get("sort_order") or plan.get("sort_order") or "desc"
    normalized["aggregation"] = chart.get("aggregation") or "sum"
    normalized["time_granularity"] = chart.get("time_granularity") or "month"
    return normalized



def build_fallback_plan(question: str, profile: Dict[str, Any]) -> Dict[str, Any]:
    metrics = _pick_metrics(question, profile)
    metric = metrics[0] if metrics else None
    dimension = _pick_dimension(question, profile)
    time_field = _pick_time_field(question, profile)
    explicit_chart_types = _extract_chart_types(question)
    top_n = _extract_top_n(question, default=None)
    sort_order = _pick_sort_order(question)

    need_trend = any(k in question for k in ["趋势", "按月", "按天", "按年", "变化", "走势"])
    need_ratio = any(k in question for k in ["占比", "结构", "构成", "分布"])
    need_correlation = any(k in question for k in ["关系", "相关", "对比关系"])
    need_distribution = any(k in question for k in ["分布", "离散", "区间"])

    charts: List[Dict[str, Any]] = []

    def add_chart(item: Dict[str, Any]) -> None:
        charts.append(item)

    # Explicit chart request: honor it first.
    if explicit_chart_types:
        for chart_type in explicit_chart_types:
            if chart_type in {"bar", "pie", "funnel", "treemap"} and dimension and metric:
                add_chart(
                    {
                        "type": chart_type,
                        "title": f"{metric}按{dimension}分析",
                        "dimension": dimension,
                        "metric": metric,
                        "metrics": metrics if chart_type == "bar" and len(metrics) > 1 else [metric],
                        "aggregation": "sum",
                        "top_n": top_n,
                        "sort_order": sort_order,
                    }
                )
            elif chart_type in {"line", "area"} and time_field and (metric or metrics):
                add_chart(
                    {
                        "type": chart_type,
                        "title": f"{metrics[0] if metrics else metric}时间趋势",
                        "time_field": time_field,
                        "metric": metric,
                        "metrics": metrics or ([metric] if metric else []),
                        "aggregation": "sum",
                        "time_granularity": "month",
                    }
                )
            elif chart_type == "scatter":
                numeric_fields = profile["numeric_fields"]
                x_metric = metrics[0] if len(metrics) >= 1 else (numeric_fields[0] if len(numeric_fields) >= 1 else None)
                y_metric = metrics[1] if len(metrics) >= 2 else (numeric_fields[1] if len(numeric_fields) >= 2 else None)
                if x_metric and y_metric:
                    add_chart(
                        {
                            "type": "scatter",
                            "title": f"{x_metric}与{y_metric}关系",
                            "x_metric": x_metric,
                            "y_metric": y_metric,
                            "label_field": dimension,
                            "top_n": min(top_n, 300) if top_n else 300,
                        }
                    )
            elif chart_type == "histogram" and metric:
                add_chart({"type": "histogram", "title": f"{metric}分布", "metric": metric})
            elif chart_type == "box" and metric:
                add_chart({"type": "box", "title": f"{metric}箱线分析", "metric": metric, "dimension": dimension})

    # No explicit chart request: infer by question.
    if not charts:
        if need_correlation and len(profile["numeric_fields"]) >= 2:
            x_metric = metrics[0]
            y_metric = metrics[1] if len(metrics) > 1 else profile["numeric_fields"][1]
            add_chart(
                {
                    "type": "scatter",
                    "title": f"{x_metric}与{y_metric}关系",
                    "x_metric": x_metric,
                    "y_metric": y_metric,
                    "label_field": dimension,
                    "top_n": min(top_n, 300) if top_n else 300,
                }
            )
        elif need_distribution and metric:
            add_chart({"type": "histogram", "title": f"{metric}分布", "metric": metric})
        elif need_trend and time_field and metric:
            add_chart(
                {
                    "type": "line",
                    "title": f"{metric}时间趋势",
                    "time_field": time_field,
                    "metrics": metrics or ([metric] if metric else []),
                    "aggregation": "sum",
                    "time_granularity": "month",
                }
            )
        elif need_ratio and dimension and metric:
            add_chart(
                {
                    "type": "pie",
                    "title": f"{metric}占比",
                    "dimension": dimension,
                    "metric": metric,
                    "aggregation": "sum",
                    "top_n": min(top_n, 12) if top_n else None,
                    "sort_order": sort_order,
                }
            )
        elif dimension and metric:
            add_chart(
                {
                    "type": "bar",
                    "title": f"{dimension}维度的{metric}对比",
                    "dimension": dimension,
                    "metric": metric,
                    "metrics": metrics,
                    "aggregation": "sum",
                    "top_n": top_n,
                    "sort_order": sort_order,
                }
            )

    # If user did not ask clearly, provide 2-3 useful views.
    if not explicit_chart_types and len(charts) <= 1:
        if dimension and metric and not any(c["type"] == "bar" for c in charts):
            add_chart(
                {
                    "type": "bar",
                    "title": f"{dimension}维度的{metric}对比",
                    "dimension": dimension,
                    "metric": metric,
                    "metrics": metrics,
                    "aggregation": "sum",
                    "top_n": top_n,
                    "sort_order": sort_order,
                }
            )
        if dimension and metric and need_ratio and not any(c["type"] == "pie" for c in charts):
            add_chart(
                {
                    "type": "pie",
                    "title": f"{metric}结构占比",
                    "dimension": dimension,
                    "metric": metric,
                    "aggregation": "sum",
                    "top_n": min(top_n, 8) if top_n else None,
                    "sort_order": sort_order,
                }
            )
        if time_field and metric and not any(c["type"] in {"line", "area"} for c in charts):
            add_chart(
                {
                    "type": "line",
                    "title": f"{metric}时间趋势",
                    "time_field": time_field,
                    "metric": metric,
                    "metrics": [metric],
                    "aggregation": "sum",
                    "time_granularity": "month",
                }
            )

    return {
        "subject": question or "自动分析",
        "metric": metric,
        "metrics": metrics,
        "dimension": dimension,
        "time_field": time_field,
        "top_n": top_n,
        "sort_order": sort_order,
        "return_all": top_n is None and _request_all_categories(question),
        "charts": charts[:4],
    }



def _to_numeric_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")
    return pd.to_numeric(
        series.astype(str).str.replace(",", "", regex=False).str.replace("%", "", regex=False),
        errors="coerce",
    )



def _aggregate_by_dimension_multi(
    df: pd.DataFrame,
    dimension: str,
    metrics: List[str],
    aggregation: str = "sum",
    top_n: Optional[int] = None,
    sort_metric: Optional[str] = None,
    sort_order: str = "desc",
) -> pd.DataFrame:
    use_cols = [dimension] + metrics
    temp = df[use_cols].copy()
    for m in metrics:
        temp[m] = _to_numeric_series(temp[m])
    temp = temp.dropna(subset=[dimension])
    temp = temp.dropna(subset=metrics, how="all")
    if temp.empty:
        return pd.DataFrame(columns=use_cols)

    agg_map = {m: aggregation if aggregation in {"sum", "mean", "count"} else "sum" for m in metrics}
    agg_df = temp.groupby(dimension, dropna=False).agg(agg_map).reset_index()
    sort_by = sort_metric or metrics[0]
    ascending = sort_order == "asc"
    agg_df = agg_df.sort_values(sort_by, ascending=ascending)
    if top_n and top_n > 0:
        agg_df = agg_df.head(top_n)
    return agg_df



def _aggregate_over_time_multi(
    df: pd.DataFrame,
    time_field: str,
    metrics: List[str],
    aggregation: str = "sum",
    granularity: str = "month",
) -> pd.DataFrame:
    use_cols = [time_field] + metrics
    temp = df[use_cols].copy()
    temp[time_field] = pd.to_datetime(temp[time_field], errors="coerce")
    for m in metrics:
        temp[m] = _to_numeric_series(temp[m])
    temp = temp.dropna(subset=[time_field])
    temp = temp.dropna(subset=metrics, how="all")
    if temp.empty:
        return pd.DataFrame(columns=use_cols)

    if granularity == "year":
        temp["_bucket"] = temp[time_field].dt.to_period("Y").astype(str)
    elif granularity == "day":
        temp["_bucket"] = temp[time_field].dt.to_period("D").astype(str)
    else:
        temp["_bucket"] = temp[time_field].dt.to_period("M").astype(str)

    agg_map = {m: aggregation if aggregation in {"sum", "mean", "count"} else "sum" for m in metrics}
    agg_df = temp.groupby("_bucket").agg(agg_map).reset_index().rename(columns={"_bucket": time_field})
    return agg_df.sort_values(time_field)



def _safe_float(value: Any) -> float:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return 0.0
        return float(value)
    except Exception:
        return 0.0



def _build_bar_like_chart(chart_type: str, agg_df: pd.DataFrame, normalized: Dict[str, Any], dimension: str, metrics: List[str]) -> Dict[str, Any]:
    title = normalized.get("title") or f"{dimension}分析"
    return {
        "type": chart_type,
        "title": title,
        "x_field": dimension,
        "y_fields": metrics,
        "table": agg_df.to_dict(orient="records"),
    }



def apply_analysis_plan(df: pd.DataFrame, profile: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
    charts_output: List[Dict[str, Any]] = []
    stats: Dict[str, Any] = {}
    chart_plans = plan.get("charts", [])

    if not chart_plans:
        plan = build_fallback_plan(plan.get("subject", "自动分析"), profile)
        chart_plans = plan.get("charts", [])

    normalized_plans = [_normalize_chart_plan(chart, profile, plan) for chart in chart_plans[:4]]

    for normalized in normalized_plans:
        chart_type = normalized.get("type")

        if chart_type in {"bar", "pie", "funnel", "treemap"}:
            dimension = normalized.get("dimension")
            metrics = normalized.get("metrics") or ([normalized.get("metric")] if normalized.get("metric") else [])
            metrics = [m for m in metrics if m]
            if not dimension or not metrics:
                continue
            agg_df = _aggregate_by_dimension_multi(
                df,
                dimension=dimension,
                metrics=metrics,
                aggregation=normalized.get("aggregation", "sum"),
                top_n=normalized.get("top_n"),
                sort_metric=metrics[0],
                sort_order=normalized.get("sort_order", "desc"),
            )
            if agg_df.empty:
                continue
            chart_spec = _build_bar_like_chart(chart_type, agg_df, normalized, dimension, metrics)
            charts_output.append(chart_spec)
            stats[normalized.get("title", chart_type)] = {
                "top_dimension": str(agg_df.iloc[0][dimension]),
                "top_metric": metrics[0],
                "top_value": _safe_float(agg_df.iloc[0][metrics[0]]),
                "item_count": int(len(agg_df)),
            }

        elif chart_type in {"line", "area"}:
            time_field = normalized.get("time_field")
            metrics = normalized.get("metrics") or ([normalized.get("metric")] if normalized.get("metric") else [])
            metrics = [m for m in metrics if m]
            if not time_field or not metrics:
                continue
            agg_df = _aggregate_over_time_multi(
                df,
                time_field=time_field,
                metrics=metrics,
                aggregation=normalized.get("aggregation", "sum"),
                granularity=normalized.get("time_granularity", "month"),
            )
            if agg_df.empty:
                continue
            charts_output.append(
                {
                    "type": chart_type,
                    "title": normalized.get("title") or f"{metrics[0]}趋势",
                    "x_field": time_field,
                    "y_fields": metrics,
                    "table": agg_df.to_dict(orient="records"),
                }
            )
            stats[normalized.get("title", chart_type)] = {
                "metric": metrics[0],
                "start": _safe_float(agg_df.iloc[0][metrics[0]]),
                "end": _safe_float(agg_df.iloc[-1][metrics[0]]),
                "periods": int(len(agg_df)),
            }

        elif chart_type == "scatter":
            x_metric = normalized.get("x_metric")
            y_metric = normalized.get("y_metric")
            label_field = normalized.get("label_field")
            if not x_metric or not y_metric:
                continue
            use_cols = [x_metric, y_metric] + ([label_field] if label_field else [])
            temp = df[use_cols].copy()
            temp[x_metric] = _to_numeric_series(temp[x_metric])
            temp[y_metric] = _to_numeric_series(temp[y_metric])
            temp = temp.dropna(subset=[x_metric, y_metric])
            if temp.empty:
                continue
            scatter_limit = normalized.get("top_n") or 300
            temp = temp.head(min(scatter_limit, 500)).reset_index(drop=True)
            charts_output.append(
                {
                    "type": "scatter",
                    "title": normalized.get("title") or f"{x_metric}与{y_metric}关系",
                    "x_field": x_metric,
                    "y_field": y_metric,
                    "label_field": label_field,
                    "table": temp.to_dict(orient="records"),
                }
            )
            stats[normalized.get("title", chart_type)] = {
                "x_metric": x_metric,
                "y_metric": y_metric,
                "point_count": int(len(temp)),
            }

        elif chart_type == "histogram":
            metric = normalized.get("metric") or (normalized.get("metrics") or [None])[0]
            if not metric:
                continue
            temp = df[[metric]].copy()
            temp[metric] = _to_numeric_series(temp[metric])
            temp = temp.dropna(subset=[metric])
            if temp.empty:
                continue
            charts_output.append(
                {
                    "type": "histogram",
                    "title": normalized.get("title") or f"{metric}分布",
                    "metric": metric,
                    "table": temp.head(2000).to_dict(orient="records"),
                }
            )
            stats[normalized.get("title", chart_type)] = {
                "metric": metric,
                "count": int(len(temp)),
                "min": _safe_float(temp[metric].min()),
                "max": _safe_float(temp[metric].max()),
            }

        elif chart_type == "box":
            metric = normalized.get("metric") or (normalized.get("metrics") or [None])[0]
            dimension = normalized.get("dimension")
            if not metric:
                continue
            use_cols = [metric] + ([dimension] if dimension else [])
            temp = df[use_cols].copy()
            temp[metric] = _to_numeric_series(temp[metric])
            temp = temp.dropna(subset=[metric])
            if dimension:
                temp = temp.dropna(subset=[dimension])
            if temp.empty:
                continue
            if dimension:
                top_dims = (
                    temp.groupby(dimension)[metric]
                    .sum()
                    .sort_values(ascending=False)
                    .head(normalized.get("top_n") or 10)
                    .index.tolist()
                )
                temp = temp[temp[dimension].isin(top_dims)]
            charts_output.append(
                {
                    "type": "box",
                    "title": normalized.get("title") or f"{metric}箱线分析",
                    "metric": metric,
                    "dimension": dimension,
                    "table": temp.head(2000).to_dict(orient="records"),
                }
            )
            stats[normalized.get("title", chart_type)] = {
                "metric": metric,
                "count": int(len(temp)),
            }

    key_findings: List[str] = []
    for _, item in stats.items():
        if item.get("top_dimension"):
            key_findings.append(
                f"排名第一的是 {item['top_dimension']}，{item.get('top_metric', '指标')}约为 {item.get('top_value', 0):,.2f}。"
            )
        if "start" in item and "end" in item:
            direction = "上升" if item["end"] >= item["start"] else "下降"
            key_findings.append(f"趋势整体呈{direction}，期初约 {item['start']:,.2f}，期末约 {item['end']:,.2f}。")
        if "min" in item and "max" in item:
            key_findings.append(f"数值分布范围约在 {item['min']:,.2f} 到 {item['max']:,.2f} 之间。")

    summary = plan.get("subject") or "已完成基础分析"
    suggestion = "建议结合业务口径确认字段含义；若你希望展示全部类别，请在需求中明确写上“所有/全部/全量”，若只看部分结果，请写明前N、排序方向和图表类型。"

    return {
        "summary": summary,
        "charts": charts_output,
        "stats": stats,
        "key_findings": key_findings[:4],
        "suggestion": suggestion,
    }
