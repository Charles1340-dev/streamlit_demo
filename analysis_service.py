from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import pandas as pd

from analyzer import apply_analysis_plan, build_fallback_plan, validate_analysis_plan
from llm_client import DeepSeekClient


DEFAULT_AUTO_QUESTION = "请自动生成一个经营数据概览，至少包含分类对比、结构占比和时间趋势。"


@dataclass
class AnalysisRunResult:
    question: str
    plan: Dict[str, Any]
    result: Dict[str, Any]
    insights: Dict[str, Any]
    llm_error: str | None
    llm_used: bool
    plan_warnings: List[str]
    plan_source: str


def resolve_question(question: str, auto_mode: bool) -> str:
    cleaned = (question or "").strip()
    if cleaned:
        return cleaned
    if auto_mode:
        return DEFAULT_AUTO_QUESTION
    return ""


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


def summarize_plan(plan: Dict[str, Any]) -> List[str]:
    summary: List[str] = []
    metric_line = "、".join(plan.get("metrics") or ([plan.get("metric")] if plan.get("metric") else []))
    if metric_line:
        summary.append(f"指标：{metric_line}")
    if plan.get("dimension"):
        summary.append(f"维度：{plan['dimension']}")
    if plan.get("time_field"):
        summary.append(f"时间字段：{plan['time_field']}")
    if plan.get("top_n") is not None:
        summary.append(f"展示范围：前 {plan['top_n']} 项")
    elif plan.get("return_all"):
        summary.append("展示范围：全部类别")
    if plan.get("sort_order"):
        summary.append(f"排序方向：{'升序' if plan['sort_order'] == 'asc' else '降序'}")
    if plan.get("charts"):
        chart_types = [chart.get("type", "-") for chart in plan["charts"]]
        summary.append(f"图表：{' / '.join(chart_types)}")
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
        llm_used=llm_used,
        plan_warnings=plan_warnings,
        plan_source=plan_source,
    )
