from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import pandas as pd

from analyzer import apply_analysis_plan, build_fallback_plan, validate_analysis_plan
from llm_client import DeepSeekClient


CHART_TYPE_LABELS = {
    "bar": "柱状图",
    "line": "折线图",
    "pie": "饼图",
    "scatter": "散点图",
    "area": "面积图",
    "histogram": "直方图",
    "box": "箱线图",
    "funnel": "漏斗图",
    "treemap": "矩形树图",
}


@dataclass
class AnalysisRunResult:
    question: str
    plan: Dict[str, Any]
    result: Dict[str, Any]
    insights: Dict[str, Any]
    llm_error: str | None
    llm_error_display: str | None
    llm_used: bool
    plan_warnings: List[str]
    plan_source: str


def resolve_question(question: str) -> str:
    return (question or "").strip()


def build_client(api_key: str, model: str, base_url: str) -> DeepSeekClient:
    return DeepSeekClient(api_key=api_key, model=model, base_url=base_url)


def build_fallback_insights(result: Dict[str, Any]) -> Dict[str, Any]:
    summary = result.get("summary", "已完成基础分析。")
    findings = result.get("key_findings", [])
    management_takeaways = result.get("management_takeaways") or findings[:2]
    risks = result.get("risks") or ["当前解读基于字段识别与统计结果，建议结合业务口径进一步确认。"]
    return {
        "summary": summary,
        "executive_brief": result.get("executive_brief", summary),
        "key_findings": findings,
        "management_takeaways": management_takeaways,
        "risks": risks,
        "suggestion": result.get("suggestion", "建议结合业务口径进一步确认字段含义。"),
    }


def build_friendly_llm_error_message(error: str | None) -> str | None:
    text = (error or "").strip()
    if not text:
        return None

    lowered = text.lower()
    if any(token in lowered for token in ["502", "bad gateway", "gateway", "connect", "connection", "timeout", "timed out", "temporarily unavailable"]):
        return "大模型服务当前网络不稳定，系统已自动切换为本地规则分析。你可以稍后重试，或继续查看当前生成结果。"
    if any(token in lowered for token in ["401", "403", "authentication", "unauthorized", "api key", "incorrect api key"]):
        return "大模型连接鉴权失败，系统已自动切换为本地规则分析。请检查 API Key 或模型连接配置。"
    if any(token in lowered for token in ["rate limit", "429", "quota"]):
        return "大模型调用频率已达到上限，系统已自动切换为本地规则分析。请稍后再试。"
    return "大模型暂时不可用，系统已自动切换为本地规则分析。你可以稍后重试，或继续查看当前生成结果。"


def summarize_plan(plan: Dict[str, Any]) -> List[str]:
    summary: List[str] = []
    metric_line = "、".join(plan.get("metrics") or ([plan.get("metric")] if plan.get("metric") else []))
    if metric_line:
        summary.append(f"本次分析聚焦的指标：{metric_line}")
    if plan.get("dimension"):
        summary.append(f"主要对比维度：{plan['dimension']}")
    if plan.get("time_field"):
        summary.append(f"时间趋势字段：{plan['time_field']}")
    if plan.get("top_n") is not None:
        summary.append(f"结果展示范围：前 {plan['top_n']} 项")
    elif plan.get("return_all"):
        summary.append("结果展示范围：全部类别")
    if plan.get("sort_order"):
        summary.append(f"排序方向：{'升序' if plan['sort_order'] == 'asc' else '降序'}")
    if plan.get("charts"):
        chart_types = [CHART_TYPE_LABELS.get(chart.get("type", "-"), chart.get("type", "-")) for chart in plan["charts"]]
        summary.append(f"计划输出图表：{' / '.join(chart_types)}")
    return summary


def run_analysis(
    *,
    df: pd.DataFrame,
    profile: Dict[str, Any],
    question: str,
    file_name: str,
    client: DeepSeekClient,
) -> AnalysisRunResult:
    llm_error = None
    llm_error_display = None
    llm_used = False

    try:
        raw_plan = client.generate_analysis_plan(
            user_question=question,
            df_profile=profile,
            file_name=file_name,
        )
        llm_used = True
        plan_source = "llm"
    except Exception as exc:
        llm_error = str(exc)
        llm_error_display = build_friendly_llm_error_message(llm_error)
        raw_plan = build_fallback_plan(question, profile)
        plan_source = "fallback"

    plan, plan_warnings = validate_analysis_plan(raw_plan, profile, question)
    result = apply_analysis_plan(df, profile, plan)

    try:
        if not llm_used:
            raise RuntimeError("skip llm insights")
        insights = client.generate_insights(
            user_question=question,
            analysis_result=result,
            plan=plan,
        )
    except Exception:
        insights = build_fallback_insights(result)

    return AnalysisRunResult(
        question=question,
        plan=plan,
        result=result,
        insights=insights,
        llm_error=llm_error,
        llm_error_display=llm_error_display,
        llm_used=llm_used,
        plan_warnings=plan_warnings,
        plan_source=plan_source,
    )
