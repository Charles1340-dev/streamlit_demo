import json
import os
import traceback
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from analyzer import apply_analysis_plan, build_fallback_plan
from chart_builder import build_plotly_figure
from excel_parser import build_dataframe_profile, load_uploaded_table
from llm_client import DeepSeekClient

st.set_page_config(page_title="智能表格分析 Demo", page_icon="📊", layout="wide")


QUICK_QUESTIONS = [
    "找出回款最高的前10个部门，做成柱状图",
    "看各部门收入占比，做成饼图",
    "按月份看回款趋势，做成折线图",
    "分析收入、成本和利润情况，做成分组柱状图",
    "看收入和成本的关系，做成散点图",
    "看回款金额分布，做成直方图",
]


def _init_state() -> None:
    defaults = {
        "df": None,
        "profile": None,
        "analysis_result": None,
        "last_question": "",
        "file_name": "",
        "api_key_input": os.getenv("DEEPSEEK_API_KEY", ""),
        "model_name": "deepseek-chat",
        "base_url": "https://api.deepseek.com",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


_init_state()

st.title("📊 智能表格分析 Demo")
st.caption("上传 Excel/CSV，输入分析需求后，自动生成匹配的图表、表格和解释说明。")

with st.sidebar:
    st.subheader("运行说明")
    st.markdown(
        """
- 支持 `.xlsx` / `.xls` / `.csv`
- 默认读取第一个 Sheet
- 建议优先填写 DeepSeek API Key
- 若大模型调用失败，会自动切换到本地规则兜底
- 现在支持：柱图、折线图、饼图、散点图、面积图、直方图、箱线图、漏斗图、树图
        """
    )

    st.text_input(
        "DeepSeek API Key",
        key="api_key_input",
        type="password",
        help="建议直接粘贴平台生成的 sk- 开头 Key。",
    )
    st.text_input("模型名", key="model_name")
    st.text_input("Base URL", key="base_url")

    if st.session_state.api_key_input.strip() or os.getenv("DEEPSEEK_API_KEY"):
        st.success("大模型状态：已配置 API Key")
    else:
        st.warning("大模型状态：未配置 API Key，将走本地兜底")

    st.subheader("快捷提问")
    for q in QUICK_QUESTIONS:
        if st.button(q, key=f"quick_{q}", use_container_width=True):
            st.session_state.last_question = q

left, right = st.columns([1.0, 1.7])

with left:
    uploaded_file = st.file_uploader("上传表格文件", type=["xlsx", "xls", "csv"])

    if uploaded_file is not None:
        try:
            df, meta = load_uploaded_table(uploaded_file)
            profile = build_dataframe_profile(df)
            st.session_state.df = df
            st.session_state.profile = profile
            st.session_state.file_name = uploaded_file.name

            st.success(f"已加载文件：{uploaded_file.name}")
            st.write(f"**行数**：{len(df):,}  |  **列数**：{len(df.columns)}")
            if meta.get("sheet_name"):
                st.write(f"**Sheet**：{meta['sheet_name']}")

            with st.expander("数据预览", expanded=True):
                st.dataframe(df.head(10), use_container_width=True, height=260)

            with st.expander("字段识别结果", expanded=False):
                st.write("**数值字段**")
                st.write(profile["numeric_fields"] or ["未识别"])
                st.write("**日期字段**")
                st.write(profile["date_fields"] or ["未识别"])
                st.write("**分类字段**")
                st.write(profile["categorical_fields"] or ["未识别"])
        except Exception as exc:
            st.error(f"文件解析失败：{exc}")
            st.code(traceback.format_exc())

    question = st.text_area(
        "请输入分析需求",
        value=st.session_state.last_question,
        height=130,
        placeholder="例如：找出回款最高的前10个部门，做成柱状图；按月份看回款趋势，做成折线图；看收入和成本关系，做成散点图",
    )

    auto_mode = st.checkbox("无输入时自动生成默认分析", value=True)
    run = st.button("开始分析", type="primary", use_container_width=True)

with right:
    if run:
        df = st.session_state.df
        profile = st.session_state.profile

        if df is None or profile is None:
            st.warning("请先上传文件。")
        else:
            final_question = question.strip()
            if not final_question and auto_mode:
                final_question = "请自动生成一个经营数据概览，至少包含分类对比、结构占比和时间趋势。"

            if not final_question:
                st.warning("请输入分析需求，或勾选自动生成默认分析。")
            else:
                with st.spinner("正在分析，请稍候..."):
                    client = DeepSeekClient(
                        api_key=st.session_state.api_key_input,
                        model=st.session_state.model_name,
                        base_url=st.session_state.base_url,
                    )
                    plan: Dict[str, Any]
                    llm_error = None
                    llm_used = False

                    try:
                        plan = client.generate_analysis_plan(
                            user_question=final_question,
                            df_profile=profile,
                            file_name=st.session_state.file_name,
                        )
                        llm_used = True
                    except Exception as exc:
                        llm_error = str(exc)
                        plan = build_fallback_plan(final_question, profile)

                    result = apply_analysis_plan(df, profile, plan)

                    try:
                        if llm_used:
                            insights = client.generate_insights(
                                user_question=final_question,
                                analysis_result=result,
                                plan=plan,
                            )
                        else:
                            raise RuntimeError("skip llm insights")
                    except Exception:
                        insights = {
                            "summary": result.get("summary", "已完成基础分析。"),
                            "key_findings": result.get("key_findings", []),
                            "suggestion": result.get("suggestion", "建议结合业务口径进一步确认字段含义。"),
                        }

                    st.session_state.analysis_result = {
                        "question": final_question,
                        "plan": plan,
                        "result": result,
                        "insights": insights,
                        "llm_error": llm_error,
                        "llm_used": llm_used,
                    }

    analysis_result = st.session_state.analysis_result

    if analysis_result:
        if analysis_result.get("llm_used"):
            st.success("本次分析已调用大模型。")
        elif analysis_result.get("llm_error"):
            st.info(f"本次未成功调用大模型，已切换本地兜底分析：{analysis_result['llm_error']}")
            with st.expander("查看大模型调用错误详情", expanded=False):
                st.code(str(analysis_result['llm_error']))

        st.subheader("分析结果")
        st.write(f"**需求**：{analysis_result['question']}")

        chart_specs: List[Dict[str, Any]] = analysis_result["result"].get("charts", [])
        if not chart_specs:
            st.warning("没有生成可展示的图表，请尝试换一种更明确的描述方式。")
        else:
            for idx, chart in enumerate(chart_specs, start=1):
                st.markdown(f"### 图表 {idx}：{chart.get('title', '未命名图表')}")
                st.plotly_chart(build_plotly_figure(chart), use_container_width=True)
                table = chart.get("table") or []
                if table:
                    with st.expander(f"查看图表 {idx} 对应数据", expanded=(idx == 1)):
                        st.dataframe(pd.DataFrame(table), use_container_width=True, height=260)

        insights = analysis_result["insights"]
        st.subheader("AI 解释说明")
        st.markdown(f"**摘要**：{insights.get('summary', '-')}")

        findings = insights.get("key_findings", [])
        if findings:
            st.markdown("**关键发现**")
            for item in findings:
                st.write(f"- {item}")

        suggestion = insights.get("suggestion")
        if suggestion:
            st.markdown(f"**建议**：{suggestion}")

        with st.expander("查看分析计划 JSON", expanded=False):
            st.code(json.dumps(analysis_result["plan"], ensure_ascii=False, indent=2), language="json")

        with st.expander("查看结果数据摘要", expanded=False):
            st.code(json.dumps(analysis_result["result"].get("stats", {}), ensure_ascii=False, indent=2), language="json")
