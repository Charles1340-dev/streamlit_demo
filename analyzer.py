from __future__ import annotations

import math
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

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

VALID_CHART_TYPES = set(CHART_KEYWORDS.keys())
VALID_SORT_ORDERS = {"asc", "desc"}
VALID_AGGREGATIONS = {"sum", "mean", "count"}
VALID_TIME_GRANULARITIES = {"day", "month", "year"}
COUNT_METRIC = "记录数"
CHART_REQUIREMENTS = {
    "bar": "需要至少 1 个分类字段和 1 个可聚合指标。",
    "line": "需要至少 1 个日期字段和 1 个可聚合指标。",
    "pie": "需要至少 1 个分类字段和 1 个可聚合指标。",
    "scatter": "需要至少 2 个数值字段，分别作为 X 轴和 Y 轴。",
    "area": "需要至少 1 个日期字段和 1 个可聚合指标。",
    "histogram": "需要至少 1 个数值字段。",
    "box": "需要至少 1 个数值字段。",
    "funnel": "需要至少 1 个分类字段和 1 个可聚合指标。",
    "treemap": "需要至少 1 个分类字段和 1 个可聚合指标。",
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
DEFAULT_MAX_CHARTS = 4
MAX_REQUESTED_CHARTS = 4


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


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _resolve_metric(name: Optional[str], numeric_fields: List[str]) -> Optional[str]:
    if name == COUNT_METRIC:
        return COUNT_METRIC
    return _resolve_field(name, numeric_fields)



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


def _coerce_top_n(value: Any) -> Optional[int]:
    if value in (None, "", 0, "0"):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return max(1, number)



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


def _extract_chart_count(question: str, default: int = DEFAULT_MAX_CHARTS) -> int:
    q = (question or "").strip()
    if not q:
        return default
    match = re.search(r"(\d+)\s*(个|张)?\s*(?:[\u4e00-\u9fa5]{0,6})?\s*(图表|图)", q)
    if match:
        return max(1, min(int(match.group(1)), MAX_REQUESTED_CHARTS))
    match = re.search(r"([一二三四五六七八九十])\s*(个|张)?\s*(?:[\u4e00-\u9fa5]{0,6})?\s*(图表|图)", q)
    if match:
        return max(1, min(CN_NUM.get(match.group(1), default), MAX_REQUESTED_CHARTS))
    if any(token in q for token in ["最适合的图表", "多图分析", "多维分析", "综合分析"]):
        return MAX_REQUESTED_CHARTS
    return default



def _extract_chart_types(question: str) -> List[str]:
    found: List[str] = []
    for chart_type, kws in CHART_KEYWORDS.items():
        if any(kw in question for kw in kws):
            found.append(chart_type)
    return found


def _is_chart_supported(chart_type: str, profile: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    has_dimension = bool(profile["categorical_fields"] or profile["text_fields"])
    has_numeric = bool(profile["numeric_fields"])
    has_time = bool(profile["date_fields"])
    numeric_count = len(profile["numeric_fields"])

    if chart_type in {"bar", "pie", "funnel", "treemap"}:
        supported = has_dimension and (has_numeric or has_dimension or has_time)
    elif chart_type in {"line", "area"}:
        supported = has_time and (has_numeric or has_dimension or has_time)
    elif chart_type == "scatter":
        supported = numeric_count >= 2
    elif chart_type == "histogram":
        supported = has_numeric
    elif chart_type == "box":
        supported = has_numeric
    else:
        supported = False

    if supported:
        return True, None
    return False, CHART_REQUIREMENTS.get(chart_type, "当前数据不满足该图表类型的生成条件。")



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
    if normalized["type"] not in VALID_CHART_TYPES:
        normalized["type"] = "bar"
    normalized["dimension"] = _resolve_field(chart.get("dimension") or plan.get("dimension"), dim_fields)
    normalized["metric"] = _resolve_metric(chart.get("metric") or plan.get("metric"), numeric_fields)
    metrics = chart.get("metrics") or plan.get("metrics") or []
    normalized["metrics"] = [_resolve_metric(m, numeric_fields) for m in metrics]
    normalized["metrics"] = _dedupe([m for m in normalized["metrics"] if m])
    if normalized["metric"] and normalized["metric"] not in normalized["metrics"]:
        normalized["metrics"] = [normalized["metric"]] + normalized["metrics"]
    normalized["time_field"] = _resolve_field(chart.get("time_field") or plan.get("time_field"), date_fields)
    normalized["x_metric"] = _resolve_field(chart.get("x_metric"), numeric_fields)
    normalized["y_metric"] = _resolve_field(chart.get("y_metric"), numeric_fields)
    normalized["label_field"] = _resolve_field(chart.get("label_field") or normalized.get("dimension"), all_fields)
    raw_top_n = chart.get("top_n", plan.get("top_n"))
    normalized["top_n"] = _coerce_top_n(raw_top_n)
    plan_subject = str(plan.get("subject") or "")
    if chart.get("return_all") or plan.get("return_all") or (_request_all_categories(plan_subject) and _extract_top_n(plan_subject, default=None) is None):
        if normalized["type"] not in {"scatter", "box"}:
            normalized["top_n"] = None
    normalized["sort_order"] = chart.get("sort_order") or plan.get("sort_order") or "desc"
    if normalized["sort_order"] not in VALID_SORT_ORDERS:
        normalized["sort_order"] = "desc"
    normalized["aggregation"] = chart.get("aggregation") or "sum"
    if normalized["aggregation"] not in VALID_AGGREGATIONS:
        normalized["aggregation"] = "sum"
    normalized["time_granularity"] = chart.get("time_granularity") or "month"
    if normalized["time_granularity"] not in VALID_TIME_GRANULARITIES:
        normalized["time_granularity"] = "month"
    return normalized


def validate_analysis_plan(
    plan: Dict[str, Any],
    profile: Dict[str, Any],
    default_subject: str = "",
) -> Tuple[Dict[str, Any], List[str]]:
    subject = str(plan.get("subject") or default_subject or "自动分析")
    requested_chart_types = _extract_chart_types(subject)
    requested_chart_count = _extract_chart_count(subject)
    normalized_plan = {
        "subject": subject,
        "metric": _resolve_metric(plan.get("metric"), profile["numeric_fields"]),
        "metrics": _dedupe([_resolve_metric(item, profile["numeric_fields"]) for item in plan.get("metrics", []) if item]),
        "dimension": _resolve_field(plan.get("dimension"), profile["categorical_fields"] + profile["text_fields"]),
        "time_field": _resolve_field(plan.get("time_field"), profile["date_fields"]),
        "top_n": _coerce_top_n(plan.get("top_n")),
        "sort_order": plan.get("sort_order") if plan.get("sort_order") in VALID_SORT_ORDERS else "desc",
        "return_all": bool(plan.get("return_all")),
        "requested_chart_types": requested_chart_types,
        "requested_chart_count": requested_chart_count,
        "unavailable_chart_types": [],
        "charts": [],
    }
    if normalized_plan["metric"] and normalized_plan["metric"] not in normalized_plan["metrics"]:
        normalized_plan["metrics"] = [normalized_plan["metric"]] + normalized_plan["metrics"]

    warnings: List[str] = []
    chart_plans = plan.get("charts") or []
    if not isinstance(chart_plans, list):
        chart_plans = []
        warnings.append("分析计划里的图表配置格式不正确，已改用兜底规则重新生成。")

    for chart in chart_plans[:requested_chart_count]:
        if not isinstance(chart, dict):
            warnings.append("发现无法识别的图表配置，已自动跳过。")
            continue
        normalized_chart = _normalize_chart_plan(chart, profile, normalized_plan)
        if requested_chart_types and normalized_chart["type"] not in requested_chart_types:
            normalized_plan["unavailable_chart_types"].append(
                {
                    "type": normalized_chart["type"],
                    "reason": f"用户明确要求的是 {'/'.join(requested_chart_types)} 图，当前计划返回了 {normalized_chart['type']} 图。",
                }
            )
            continue
        is_supported, reason = _is_chart_supported(normalized_chart["type"], profile)
        if not is_supported:
            normalized_plan["unavailable_chart_types"].append(
                {"type": normalized_chart["type"], "reason": reason}
            )
            continue
        normalized_plan["charts"].append(normalized_chart)

    if normalized_plan["charts"]:
        first_chart = normalized_plan["charts"][0]
        if not normalized_plan["dimension"]:
            normalized_plan["dimension"] = first_chart.get("dimension")
        if not normalized_plan["time_field"]:
            normalized_plan["time_field"] = first_chart.get("time_field")
        if not normalized_plan["metric"]:
            normalized_plan["metric"] = first_chart.get("metric") or first_chart.get("x_metric")
        if not normalized_plan["metrics"]:
            normalized_plan["metrics"] = first_chart.get("metrics") or ([first_chart.get("metric")] if first_chart.get("metric") else [])

    if len(normalized_plan["charts"]) < requested_chart_count:
        fallback_plan = build_fallback_plan(normalized_plan["subject"], profile)
        existing_keys = {
            (
                item.get("type"),
                item.get("title"),
                item.get("dimension"),
                item.get("time_field"),
                item.get("metric"),
                tuple(item.get("metrics") or []),
            )
            for item in normalized_plan["charts"]
        }
        for chart in fallback_plan.get("charts", []):
            normalized_chart = _normalize_chart_plan(chart, profile, fallback_plan)
            if requested_chart_types and normalized_chart["type"] not in requested_chart_types:
                continue
            key = (
                normalized_chart.get("type"),
                normalized_chart.get("title"),
                normalized_chart.get("dimension"),
                normalized_chart.get("time_field"),
                normalized_chart.get("metric"),
                tuple(normalized_chart.get("metrics") or []),
            )
            if key in existing_keys:
                continue
            is_supported, reason = _is_chart_supported(normalized_chart["type"], profile)
            if not is_supported:
                if reason:
                    normalized_plan["unavailable_chart_types"].append({"type": normalized_chart["type"], "reason": reason})
                continue
            normalized_plan["charts"].append(normalized_chart)
            existing_keys.add(key)
            if len(normalized_plan["charts"]) >= requested_chart_count:
                break

    if len(normalized_plan["charts"]) < requested_chart_count:
        warnings.append(
            f"当前数据条件下最多可稳定生成 {len(normalized_plan['charts'])} 个图表，未能完全满足你要求的 {requested_chart_count} 个图表。"
        )

    if not normalized_plan["charts"] and requested_chart_types:
        unavailable = normalized_plan["unavailable_chart_types"]
        for chart_type in requested_chart_types:
            if not any(item["type"] == chart_type for item in unavailable):
                supported, reason = _is_chart_supported(chart_type, profile)
                if not supported:
                    unavailable.append({"type": chart_type, "reason": reason})
        for item in unavailable:
            warnings.append(f"无法生成你指定的{item['type']}图：{item['reason']}")

    if not normalized_plan["charts"] and not requested_chart_types:
        fallback_plan = build_fallback_plan(normalized_plan["subject"], profile)
        normalized_plan["metric"] = fallback_plan.get("metric")
        normalized_plan["metrics"] = fallback_plan.get("metrics", [])
        normalized_plan["dimension"] = fallback_plan.get("dimension")
        normalized_plan["time_field"] = fallback_plan.get("time_field")
        normalized_plan["top_n"] = fallback_plan.get("top_n")
        normalized_plan["sort_order"] = fallback_plan.get("sort_order", "desc")
        normalized_plan["return_all"] = fallback_plan.get("return_all", False)
        normalized_plan["requested_chart_types"] = fallback_plan.get("requested_chart_types", [])
        normalized_plan["unavailable_chart_types"] = fallback_plan.get("unavailable_chart_types", [])
        normalized_plan["requested_chart_count"] = fallback_plan.get("requested_chart_count", requested_chart_count)
        normalized_plan["charts"] = [
            _normalize_chart_plan(chart, profile, fallback_plan)
            for chart in fallback_plan.get("charts", [])[: normalized_plan["requested_chart_count"]]
        ]
        warnings.append("原始计划缺少有效图表，已自动切换为本地规则生成的分析计划。")

    if not normalized_plan["metrics"] and normalized_plan["metric"]:
        normalized_plan["metrics"] = [normalized_plan["metric"]]

    if not normalized_plan["metrics"] and profile["numeric_fields"]:
        normalized_plan["metric"] = profile["numeric_fields"][0]
        normalized_plan["metrics"] = [profile["numeric_fields"][0]]
        warnings.append("未明确识别到指标字段，已使用首个数值字段继续分析。")
    elif not normalized_plan["metrics"] and (profile["categorical_fields"] or profile["text_fields"] or profile["date_fields"]):
        normalized_plan["metric"] = COUNT_METRIC
        normalized_plan["metrics"] = [COUNT_METRIC]
        warnings.append("未发现可用数值字段，已自动改用记录数统计，确保仍可输出图表。")

    return normalized_plan, warnings



def build_fallback_plan(question: str, profile: Dict[str, Any]) -> Dict[str, Any]:
    metrics = _pick_metrics(question, profile)
    metric = metrics[0] if metrics else None
    has_numeric_metric = bool(metric)
    if not has_numeric_metric:
        metrics = [COUNT_METRIC]
        metric = COUNT_METRIC
    dimension = _pick_dimension(question, profile)
    time_field = _pick_time_field(question, profile)
    explicit_chart_types = _extract_chart_types(question)
    requested_chart_count = _extract_chart_count(question)
    top_n = _extract_top_n(question, default=None)
    sort_order = _pick_sort_order(question)

    need_trend = any(k in question for k in ["趋势", "按月", "按天", "按年", "变化", "走势"])
    need_ratio = any(k in question for k in ["占比", "结构", "构成", "分布"])
    need_correlation = any(k in question for k in ["关系", "相关", "对比关系"])
    need_distribution = any(k in question for k in ["分布", "离散", "区间"])

    charts: List[Dict[str, Any]] = []
    unavailable_chart_types: List[Dict[str, str]] = []

    def add_chart(item: Dict[str, Any]) -> None:
        chart_type = item.get("type")
        title = item.get("title")
        if any(existing.get("type") == chart_type and existing.get("title") == title for existing in charts):
            return
        charts.append(item)

    def add_dimension_views(target_dimension: Optional[str], target_metric: Optional[str], target_metrics: List[str]) -> None:
        if not target_dimension or not target_metric:
            return
        add_chart(
            {
                "type": "bar",
                "title": f"{target_dimension}维度的{target_metric}对比",
                "dimension": target_dimension,
                "metric": target_metric,
                "metrics": target_metrics or [target_metric],
                "aggregation": "sum" if has_numeric_metric else "count",
                "top_n": top_n,
                "sort_order": sort_order,
            }
        )
        add_chart(
            {
                "type": "pie",
                "title": f"{target_metric}结构占比",
                "dimension": target_dimension,
                "metric": target_metric,
                "aggregation": "sum" if has_numeric_metric else "count",
                "top_n": min(top_n, 8) if top_n else 8,
                "sort_order": sort_order,
            }
        )
        add_chart(
            {
                "type": "treemap",
                "title": f"{target_dimension}结构分层",
                "dimension": target_dimension,
                "metric": target_metric,
                "aggregation": "sum" if has_numeric_metric else "count",
                "top_n": min(top_n, 15) if top_n else 15,
                "sort_order": sort_order,
            }
        )

    def add_time_views(target_time_field: Optional[str], target_metric: Optional[str], target_metrics: List[str]) -> None:
        if not target_time_field or not target_metric:
            return
        add_chart(
            {
                "type": "line",
                "title": f"{target_metric}时间趋势",
                "time_field": target_time_field,
                "metric": target_metric,
                "metrics": target_metrics or [target_metric],
                "aggregation": "sum" if has_numeric_metric else "count",
                "time_granularity": "month",
            }
        )
        add_chart(
            {
                "type": "area",
                "title": f"{target_metric}累计走势",
                "time_field": target_time_field,
                "metric": target_metric,
                "metrics": [target_metric],
                "aggregation": "sum" if has_numeric_metric else "count",
                "time_granularity": "month",
            }
        )

    def add_distribution_views(target_metric: Optional[str], target_dimension: Optional[str]) -> None:
        if not target_metric or target_metric == COUNT_METRIC:
            return
        add_chart({"type": "histogram", "title": f"{target_metric}分布", "metric": target_metric})
        add_chart({"type": "box", "title": f"{target_metric}箱线分析", "metric": target_metric, "dimension": target_dimension})

    def add_relationship_view(target_metrics: List[str], target_dimension: Optional[str]) -> None:
        numeric_fields = profile["numeric_fields"]
        x_metric = target_metrics[0] if len(target_metrics) >= 1 else (numeric_fields[0] if len(numeric_fields) >= 1 else None)
        y_metric = target_metrics[1] if len(target_metrics) >= 2 else (numeric_fields[1] if len(numeric_fields) >= 2 else None)
        if x_metric and y_metric and x_metric != y_metric:
            add_chart(
                {
                    "type": "scatter",
                    "title": f"{x_metric}与{y_metric}关系",
                    "x_metric": x_metric,
                    "y_metric": y_metric,
                    "label_field": target_dimension,
                    "top_n": min(top_n, 300) if top_n else 300,
                }
            )

    def expand_charts_to_requested_count(allowed_types: Optional[List[str]] = None) -> None:
        allowed = set(allowed_types or [])

        def allows(chart_type: str) -> bool:
            return not allowed or chart_type in allowed

        dimension_pool = _dedupe([item for item in [dimension] + profile["categorical_fields"] + profile["text_fields"] if item])
        metric_pool = _dedupe([item for item in metrics + profile["numeric_fields"] if item and item != COUNT_METRIC])[:5]
        metric_or_count_pool = metric_pool or [COUNT_METRIC]

        for target_dimension in dimension_pool:
            for target_metric in metric_or_count_pool:
                if allows("bar"):
                    add_chart(
                        {
                            "type": "bar",
                            "title": f"{target_dimension}维度的{target_metric}对比",
                            "dimension": target_dimension,
                            "metric": target_metric,
                            "metrics": [target_metric],
                            "aggregation": "sum" if target_metric != COUNT_METRIC else "count",
                            "top_n": top_n,
                            "sort_order": sort_order,
                        }
                    )
                if allows("pie"):
                    add_chart(
                        {
                            "type": "pie",
                            "title": f"{target_dimension}维度的{target_metric}占比",
                            "dimension": target_dimension,
                            "metric": target_metric,
                            "aggregation": "sum" if target_metric != COUNT_METRIC else "count",
                            "top_n": min(top_n, 8) if top_n else 8,
                            "sort_order": sort_order,
                        }
                    )
                if allows("treemap"):
                    add_chart(
                        {
                            "type": "treemap",
                            "title": f"{target_dimension}维度的{target_metric}层级结构",
                            "dimension": target_dimension,
                            "metric": target_metric,
                            "aggregation": "sum" if target_metric != COUNT_METRIC else "count",
                            "top_n": min(top_n, 15) if top_n else 15,
                            "sort_order": sort_order,
                        }
                    )
                if len(charts) >= requested_chart_count:
                    return

        if time_field:
            for target_metric in metric_or_count_pool:
                if allows("line"):
                    add_chart(
                        {
                            "type": "line",
                            "title": f"{target_metric}时间趋势",
                            "time_field": time_field,
                            "metric": target_metric,
                            "metrics": [target_metric],
                            "aggregation": "sum" if target_metric != COUNT_METRIC else "count",
                            "time_granularity": "month",
                        }
                    )
                if allows("area"):
                    add_chart(
                        {
                            "type": "area",
                            "title": f"{target_metric}时间面积趋势",
                            "time_field": time_field,
                            "metric": target_metric,
                            "metrics": [target_metric],
                            "aggregation": "sum" if target_metric != COUNT_METRIC else "count",
                            "time_granularity": "month",
                        }
                    )
                if len(charts) >= requested_chart_count:
                    return

        for target_metric in metric_pool:
            if allows("histogram"):
                add_chart({"type": "histogram", "title": f"{target_metric}分布", "metric": target_metric})
            if allows("box"):
                add_chart({"type": "box", "title": f"{target_metric}箱线分析", "metric": target_metric, "dimension": dimension})
            if len(charts) >= requested_chart_count:
                return

        for i, x_metric in enumerate(metric_pool):
            for y_metric in metric_pool[i + 1 :]:
                if allows("scatter"):
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
                if len(charts) >= requested_chart_count:
                    return

    # Explicit chart request: honor it first.
    if explicit_chart_types:
        for chart_type in explicit_chart_types:
            supported, reason = _is_chart_supported(chart_type, profile)
            if not supported:
                unavailable_chart_types.append({"type": chart_type, "reason": reason or "当前数据无法生成该图表。"})
                continue
            if chart_type in {"bar", "pie", "funnel", "treemap"} and dimension and metric:
                add_chart(
                    {
                        "type": chart_type,
                        "title": f"{metric}按{dimension}分析",
                        "dimension": dimension,
                        "metric": metric,
                        "metrics": metrics if chart_type == "bar" and len(metrics) > 1 else [metric],
                        "aggregation": "sum" if has_numeric_metric else "count",
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
                        "aggregation": "sum" if has_numeric_metric else "count",
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

        if len(charts) < requested_chart_count:
            expand_charts_to_requested_count(explicit_chart_types)

    # No explicit chart request: infer by question.
    if not charts and not explicit_chart_types:
        if need_correlation:
            add_relationship_view(metrics, dimension)
        if need_distribution:
            add_distribution_views(metric, dimension)
        if need_trend:
            add_time_views(time_field, metric, metrics)
        if need_ratio:
            add_dimension_views(dimension, metric, metrics)
        if not charts:
            add_dimension_views(dimension, metric, metrics)
            add_time_views(time_field, metric, metrics)
            add_distribution_views(metric, dimension)
            add_relationship_view(metrics, dimension)

    # If user did not ask clearly, provide a broader set of useful views.
    if not explicit_chart_types:
        add_dimension_views(dimension, metric, metrics)
        add_time_views(time_field, metric, metrics)
        add_distribution_views(metric, dimension)
        add_relationship_view(metrics, dimension)

    if not charts and dimension and not explicit_chart_types:
        add_chart(
            {
                "type": "bar",
                "title": f"{dimension}分布",
                "dimension": dimension,
                "metric": COUNT_METRIC,
                "metrics": [COUNT_METRIC],
                "aggregation": "count",
                "top_n": top_n or 12,
                "sort_order": sort_order,
            }
        )
    elif not charts and time_field and not explicit_chart_types:
        add_chart(
            {
                "type": "line",
                "title": "记录数时间趋势",
                "time_field": time_field,
                "metric": COUNT_METRIC,
                "metrics": [COUNT_METRIC],
                "aggregation": "count",
                "time_granularity": "month",
            }
        )
    elif not charts and profile["numeric_fields"] and not explicit_chart_types:
        base_metric = profile["numeric_fields"][0]
        add_chart({"type": "histogram", "title": f"{base_metric}分布", "metric": base_metric})

    if len(charts) < requested_chart_count:
        expand_charts_to_requested_count(explicit_chart_types if explicit_chart_types else None)

    selected_charts = charts[:requested_chart_count]

    return {
        "subject": question or "自动分析",
        "metric": metric,
        "metrics": metrics,
        "dimension": dimension,
        "time_field": time_field,
        "top_n": top_n,
        "sort_order": sort_order,
        "return_all": top_n is None and _request_all_categories(question),
        "requested_chart_types": explicit_chart_types,
        "requested_chart_count": requested_chart_count,
        "unavailable_chart_types": unavailable_chart_types,
        "charts": selected_charts,
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
    raw_metrics = [m for m in metrics if m != COUNT_METRIC]
    use_cols = [dimension] + raw_metrics
    temp = df[use_cols].copy()
    for m in raw_metrics:
        temp[m] = _to_numeric_series(temp[m])
    temp = temp.dropna(subset=[dimension])
    if raw_metrics:
        temp = temp.dropna(subset=raw_metrics, how="all")
    if temp.empty:
        return pd.DataFrame(columns=[dimension] + metrics)

    grouped = temp.groupby(dimension, dropna=False)
    agg_df = grouped.size().reset_index(name=COUNT_METRIC) if COUNT_METRIC in metrics else grouped.size().reset_index(name="_tmp_count")

    for metric in raw_metrics:
        if aggregation == "mean":
            agg_df[metric] = grouped[metric].mean().values
        elif aggregation == "count":
            agg_df[metric] = grouped[metric].count().values
        else:
            agg_df[metric] = grouped[metric].sum().values

    if COUNT_METRIC not in metrics and "_tmp_count" in agg_df.columns:
        agg_df = agg_df.drop(columns=["_tmp_count"])

    sort_by = sort_metric or metrics[0]
    ascending = sort_order == "asc"
    agg_df = agg_df.sort_values(sort_by, ascending=ascending)
    if top_n and top_n > 0:
        agg_df = agg_df.head(top_n)
    return agg_df[[dimension] + metrics]



def _aggregate_over_time_multi(
    df: pd.DataFrame,
    time_field: str,
    metrics: List[str],
    aggregation: str = "sum",
    granularity: str = "month",
) -> pd.DataFrame:
    raw_metrics = [m for m in metrics if m != COUNT_METRIC]
    use_cols = [time_field] + raw_metrics
    temp = df[use_cols].copy()
    temp[time_field] = pd.to_datetime(temp[time_field], errors="coerce")
    for m in raw_metrics:
        temp[m] = _to_numeric_series(temp[m])
    temp = temp.dropna(subset=[time_field])
    if raw_metrics:
        temp = temp.dropna(subset=raw_metrics, how="all")
    if temp.empty:
        return pd.DataFrame(columns=[time_field] + metrics)

    if granularity == "year":
        temp["_bucket"] = temp[time_field].dt.to_period("Y").astype(str)
    elif granularity == "day":
        temp["_bucket"] = temp[time_field].dt.to_period("D").astype(str)
    else:
        temp["_bucket"] = temp[time_field].dt.to_period("M").astype(str)

    grouped = temp.groupby("_bucket")
    agg_df = grouped.size().reset_index(name=COUNT_METRIC) if COUNT_METRIC in metrics else grouped.size().reset_index(name="_tmp_count")
    for metric in raw_metrics:
        if aggregation == "mean":
            agg_df[metric] = grouped[metric].mean().values
        elif aggregation == "count":
            agg_df[metric] = grouped[metric].count().values
        else:
            agg_df[metric] = grouped[metric].sum().values

    if COUNT_METRIC not in metrics and "_tmp_count" in agg_df.columns:
        agg_df = agg_df.drop(columns=["_tmp_count"])
    agg_df = agg_df.rename(columns={"_bucket": time_field})
    return agg_df.sort_values(time_field)[[time_field] + metrics]



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


def _build_last_resort_chart(df: pd.DataFrame, profile: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    dimension = _pick_dimension("", profile)
    if dimension:
        agg_df = (
            df[[dimension]]
            .dropna(subset=[dimension])
            .groupby(dimension)
            .size()
            .reset_index(name=COUNT_METRIC)
            .sort_values(COUNT_METRIC, ascending=False)
            .head(12)
        )
        if not agg_df.empty:
            return {
                "type": "bar",
                "title": f"{dimension}分布概览",
                "x_field": dimension,
                "y_fields": [COUNT_METRIC],
                "table": agg_df.to_dict(orient="records"),
            }

    if profile["date_fields"]:
        time_field = profile["date_fields"][0]
        temp = df[[time_field]].copy()
        temp[time_field] = pd.to_datetime(temp[time_field], errors="coerce")
        temp = temp.dropna(subset=[time_field])
        if not temp.empty:
            agg_df = (
                temp.assign(_bucket=temp[time_field].dt.to_period("M").astype(str))
                .groupby("_bucket")
                .size()
                .reset_index(name=COUNT_METRIC)
                .rename(columns={"_bucket": time_field})
                .sort_values(time_field)
            )
            return {
                "type": "line",
                "title": "记录数时间趋势",
                "x_field": time_field,
                "y_fields": [COUNT_METRIC],
                "table": agg_df.to_dict(orient="records"),
            }

    if profile["numeric_fields"]:
        metric = profile["numeric_fields"][0]
        temp = df[[metric]].copy()
        temp[metric] = _to_numeric_series(temp[metric])
        temp = temp.dropna(subset=[metric])
        if not temp.empty:
            return {
                "type": "histogram",
                "title": f"{metric}分布",
                "metric": metric,
                "table": temp.head(2000).to_dict(orient="records"),
            }

    return None



def apply_analysis_plan(df: pd.DataFrame, profile: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
    charts_output: List[Dict[str, Any]] = []
    stats: Dict[str, Any] = {}
    plan, warnings = validate_analysis_plan(plan, profile, plan.get("subject", "自动分析"))
    normalized_plans = plan.get("charts", [])
    substitute_chart_used = False

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

    if not charts_output:
        fallback_chart = _build_last_resort_chart(df, profile)
        if fallback_chart:
            if plan.get("requested_chart_types"):
                fallback_chart["title"] = f"替代图表：{fallback_chart['title']}"
                warnings.append("当前数据无法满足你指定的图表类型，下面提供的是替代概览图。")
                substitute_chart_used = True
            else:
                warnings.append("原计划未生成有效图表，已自动输出数据概览图，避免结果为空。")
            charts_output.append(fallback_chart)

    summary = plan.get("subject") or "已完成基础分析"
    executive_brief = "本次分析已生成可用于汇报的图表和摘要，可先关注排名、趋势与分布，再结合业务背景确认原因。"
    management_takeaways = [
        "建议优先围绕图表中的头部类别、变化趋势和结构差异组织汇报主线。",
        "如果需要正式汇报材料，可进一步补充同比、环比或目标达成口径。",
    ]
    risks = ["当前分析基于字段识别和自动聚合生成，涉及复杂业务口径时建议结合原始定义复核。"]
    suggestion = "建议结合业务口径确认字段含义；若你希望展示全部类别，请在需求中明确写上“所有/全部/全量”，若只看部分结果，请写明前N、排序方向和图表类型。"

    return {
        "summary": summary,
        "executive_brief": executive_brief,
        "charts": charts_output,
        "stats": stats,
        "key_findings": key_findings[:4],
        "management_takeaways": management_takeaways,
        "risks": risks,
        "suggestion": suggestion,
        "warnings": warnings,
        "substitute_chart_used": substitute_chart_used,
    }
