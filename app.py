from __future__ import annotations

import json
import os
import traceback
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from analysis_service import build_client, resolve_question, run_analysis, summarize_plan
from chart_builder import build_plotly_figure
from excel_parser import build_dataframe_profile, load_uploaded_table

st.set_page_config(page_title="智能表格分析工作台", page_icon="📊", layout="wide")

APP_STYLE = """
<style>
    #MainMenu, header [data-testid="stToolbar"], .stDeployButton {
        display: none !important;
    }
    .stApp {
        background:
            radial-gradient(circle at 15% 18%, rgba(70, 197, 255, 0.16), transparent 24%),
            radial-gradient(circle at 82% 12%, rgba(84, 114, 248, 0.12), transparent 22%),
            radial-gradient(circle at 78% 88%, rgba(0, 209, 178, 0.10), transparent 20%),
            linear-gradient(180deg, #eef4fb 0%, #e9f0fb 40%, #f4f8fc 100%);
        color: #e8f1ff;
    }
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, rgba(247, 250, 255, 0.96), rgba(239, 245, 252, 0.96));
        border-right: 1px solid rgba(36, 75, 118, 0.08);
    }
    [data-testid="stSidebar"] * {
        color: #20324d;
    }
    .block-container {
        padding-top: 2.2rem;
        padding-bottom: 3rem;
        max-width: 1280px;
    }
    .hero-card, .panel-card, .metric-card {
        border-radius: 22px;
        border: 1px solid rgba(68, 104, 156, 0.14);
        background: linear-gradient(180deg, rgba(255, 255, 255, 0.92), rgba(244, 249, 255, 0.94));
        box-shadow: 0 18px 42px rgba(40, 75, 112, 0.10);
        backdrop-filter: blur(12px);
    }
    .hero-card {
        padding: 1.6rem 1.8rem;
        margin-bottom: 1rem;
        background:
            linear-gradient(135deg, rgba(19, 72, 135, 0.96), rgba(33, 109, 160, 0.94)),
            linear-gradient(90deg, rgba(255, 255, 255, 0.05), rgba(255, 255, 255, 0.02));
    }
    .hero-kicker {
        font-size: 0.85rem;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        color: #c9f1ff;
        margin-bottom: 0.4rem;
        font-weight: 700;
    }
    .hero-title {
        font-size: 2.3rem;
        line-height: 1.1;
        color: #ffffff;
        font-weight: 800;
        margin-bottom: 0.55rem;
    }
    .hero-subtitle {
        color: #e7f2ff;
        font-size: 1rem;
        margin-bottom: 0;
    }
    .panel-card {
        padding: 1.1rem 1.2rem 0.4rem 1.2rem;
        margin-bottom: 1rem;
        color: #20324d;
    }
    .section-title {
        color: #18365a;
        font-size: 1.55rem;
        font-weight: 800;
        margin: 0.2rem 0 1rem 0;
    }
    .section-desc {
        color: #6781a0;
        font-size: 0.96rem;
        margin-bottom: 0.9rem;
    }
    .metric-card {
        padding: 0.9rem 1rem;
        min-height: 152px;
        background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(243, 248, 255, 0.96));
    }
    .metric-label {
        color: #5e7391;
        font-size: 0.88rem;
        margin-bottom: 0.45rem;
    }
    .metric-value {
        color: #173250;
        font-size: 1.55rem;
        font-weight: 800;
        line-height: 1.1;
        margin-bottom: 0.35rem;
    }
    .metric-caption {
        color: #6f84a0;
        font-size: 0.88rem;
    }
    .metric-value.file-name {
        font-size: 1.05rem;
        line-height: 1.45;
        word-break: break-word;
    }
    .chart-chip {
        display: inline-block;
        padding: 0.32rem 0.62rem;
        margin: 0 0.45rem 0.45rem 0;
        border-radius: 999px;
        border: 1px solid rgba(76, 122, 182, 0.16);
        background: rgba(229, 239, 250, 0.95);
        color: #29486b;
        font-size: 0.84rem;
    }
    .stButton > button,
    [data-testid="baseButton-secondary"],
    [data-testid="baseButton-primary"] {
        background: linear-gradient(135deg, #1b75d0, #0f91b8) !important;
        color: #ffffff !important;
        border: 1px solid rgba(8, 72, 125, 0.18) !important;
        border-radius: 14px !important;
        font-weight: 700 !important;
        box-shadow: 0 8px 24px rgba(21, 101, 180, 0.18) !important;
    }
    .stButton > button:hover,
    [data-testid="baseButton-secondary"]:hover,
    [data-testid="baseButton-primary"]:hover {
        background: linear-gradient(135deg, #1566ba, #0c7ca0) !important;
        color: #ffffff !important;
    }
    .stDownloadButton > button {
        background: linear-gradient(135deg, #1b75d0, #0f91b8) !important;
        color: #ffffff !important;
    }
    .stTextInput input, .stTextArea textarea {
        background: rgba(255, 255, 255, 0.96) !important;
        color: #1f314c !important;
        border-radius: 14px !important;
    }
    .stSelectbox div[data-baseweb="select"] > div,
    .stMultiSelect div[data-baseweb="select"] > div {
        background: rgba(255, 255, 255, 0.96) !important;
        color: #1f314c !important;
    }
    [data-testid="stFileUploaderDropzone"] {
        background: linear-gradient(180deg, rgba(251, 254, 255, 0.98), rgba(238, 246, 255, 0.96)) !important;
        border: 2px dashed rgba(32, 126, 184, 0.38) !important;
    }
    [data-testid="stFileUploaderDropzone"] * {
        color: #2a4565 !important;
    }
    [data-testid="stFileUploaderDropzoneInstructions"] > div:first-child {
        visibility: hidden;
        position: relative;
    }
    [data-testid="stFileUploaderDropzoneInstructions"] > div:first-child::after {
        content: "将文件拖放到此处";
        visibility: visible;
        position: absolute;
        inset: 0;
        color: #29486b;
        font-weight: 700;
    }
    [data-testid="stFileUploaderDropzoneInstructions"] > div:nth-child(2) {
        visibility: hidden;
        position: relative;
    }
    [data-testid="stFileUploaderDropzoneInstructions"] > div:nth-child(2)::after {
        content: "支持 XLSX、XLS、CSV，单文件大小不超过 200MB";
        visibility: visible;
        position: absolute;
        inset: 0;
        color: #5c7390;
    }
    [data-testid="stBaseButton-secondary"] {
        color: transparent !important;
        position: relative;
    }
    [data-testid="stBaseButton-secondary"]::after {
        content: "选择文件";
        color: #5c7390;
        position: absolute;
        inset: 0;
        display: flex;
        align-items: center;
        justify-content: center;
    }
    .stMarkdown, .stCaption, .stText, p, label, h1, h2, h3 {
        color: #20324d !important;
    }
    .stAlert {
        border-radius: 16px !important;
    }
    .loading-shell {
        border-radius: 28px;
        padding: 3.2rem 2rem;
        background: linear-gradient(180deg, #3265f6 0%, #3d73ff 100%);
        box-shadow: 0 26px 60px rgba(41, 91, 207, 0.26);
        text-align: center;
        color: #ffffff;
        margin: 1rem 0 1.4rem 0;
    }
    .loading-ring {
        width: 92px;
        height: 92px;
        border-radius: 50%;
        margin: 0 auto 1.2rem auto;
        border: 4px solid rgba(255, 255, 255, 0.25);
        border-top-color: #ffffff;
        border-right-color: rgba(255,255,255,0.88);
        animation: spin 1.2s linear infinite;
    }
    .loading-title {
        color: #ffffff;
        font-size: 1.45rem;
        font-weight: 800;
        margin-bottom: 0.55rem;
    }
    .loading-subtitle {
        color: rgba(255,255,255,0.90);
        font-size: 1rem;
        margin-bottom: 1rem;
    }
    .loading-stage {
        color: rgba(255,255,255,0.95);
        font-size: 1.02rem;
        font-weight: 700;
        margin-bottom: 1rem;
    }
    .loading-stage-list {
        display: flex;
        justify-content: center;
        gap: 0.8rem;
        flex-wrap: wrap;
    }
    .loading-chip {
        border-radius: 999px;
        padding: 0.45rem 0.95rem;
        background: rgba(255,255,255,0.15);
        color: #ffffff;
        font-size: 0.92rem;
    }
    @keyframes spin {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
    }
</style>
"""

SUPPORTED_CHARTS = ["bar", "line", "pie", "scatter", "area", "histogram", "box", "funnel", "treemap"]
SUPPORTED_CHART_LABELS = {
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
MODEL_PRESETS = {
    "DeepSeek": {"model_name": "deepseek-chat", "base_url": "https://api.deepseek.com"},
    "OpenAI 兼容自定义接口": {"model_name": "", "base_url": ""},
}


def _init_state() -> None:
    defaults = {
        "df": None,
        "profile": None,
        "analysis_result": None,
        "last_question": "",
        "file_name": "",
        "file_meta": {},
        "api_key_input": os.getenv("DEEPSEEK_API_KEY", ""),
        "provider_preset": "DeepSeek",
        "model_name": "deepseek-chat",
        "base_url": "https://api.deepseek.com",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _render_header() -> None:
    st.markdown(APP_STYLE, unsafe_allow_html=True)
    st.markdown(
        """
        <div class="hero-card">
            <div class="hero-kicker">智能洞察引擎</div>
            <div class="hero-title">智能文档分析工作台</div>
            <p class="hero-subtitle">
                上传 Excel 或 CSV，用自然语言提出需求，系统会依据字段结构自适应生成图表、数据摘要和数据分析解读。
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_sidebar() -> None:
    with st.sidebar:
        st.subheader("控制台")
        with st.expander("模型与连接配置", expanded=False):
            selected_preset = st.selectbox("连接模板", list(MODEL_PRESETS.keys()), key="provider_preset")
            preset = MODEL_PRESETS[selected_preset]
            if selected_preset == "DeepSeek" and not st.session_state.model_name:
                st.session_state.model_name = preset["model_name"]
            if selected_preset == "DeepSeek" and not st.session_state.base_url:
                st.session_state.base_url = preset["base_url"]

            st.text_input(
                "API Key",
                key="api_key_input",
                type="password",
                help="支持 OpenAI 兼容接口，默认填写 DeepSeek 配置即可使用。",
            )
            st.text_input("模型名", key="model_name")
            st.text_input("Base URL", key="base_url")

        if st.session_state.api_key_input.strip() or os.getenv("DEEPSEEK_API_KEY"):
            st.success("大模型状态：已配置 API Key")
        else:
            st.warning("大模型状态：未配置 API Key，将走本地兜底")

        st.markdown("---")
        st.caption("支持 `.xlsx` / `.xls` / `.csv`，默认读取第一个 Sheet。")
        st.caption("系统会根据字段内容自适应选择分析方式，不限定财务场景。")
        st.caption("图表输出范围已固定为以下类型：")
        st.markdown("".join([f'<span class="chart-chip">{SUPPORTED_CHART_LABELS[item]}</span>' for item in SUPPORTED_CHARTS]), unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def _cached_parse_uploaded_file(file_name: str, content: bytes):
    class _UploadedFileProxy:
        def __init__(self, name: str, raw: bytes):
            self.name = name
            self._raw = raw

        def getvalue(self) -> bytes:
            return self._raw

    df, meta = load_uploaded_table(_UploadedFileProxy(file_name, content))
    profile = build_dataframe_profile(df)
    return df, meta, profile


def _load_uploaded_file(uploaded_file) -> None:
    if uploaded_file is None:
        return
    try:
        content = uploaded_file.getvalue()
        df, meta, profile = _cached_parse_uploaded_file(uploaded_file.name, content)
        st.session_state.df = df
        st.session_state.profile = profile
        st.session_state.file_name = uploaded_file.name
        st.session_state.file_meta = meta
    except Exception as exc:
        st.error(f"文件解析失败：{exc}")
        st.code(traceback.format_exc())


def _render_metric_card(label: str, value: str, caption: str) -> None:
    value_class = "metric-value file-name" if label == "当前文件" else "metric-value"
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="{value_class}">{value}</div>
            <div class="metric-caption">{caption}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_dataset_summary() -> None:
    df = st.session_state.df
    profile = st.session_state.profile
    if df is None or profile is None:
        st.info("先上传一份业务表格，左侧会显示数据预览、字段识别和分析输入区。")
        return

    meta = st.session_state.file_meta or {}
    st.markdown("### 数据概览")
    metric_cols = st.columns(4)
    with metric_cols[0]:
        _render_metric_card("当前文件", st.session_state.file_name or "-", "已接入分析工作台")
    with metric_cols[1]:
        _render_metric_card("数据规模", f"{len(df):,} 行", f"共 {len(df.columns)} 列")
    with metric_cols[2]:
        _render_metric_card("可分析指标", str(len(profile["numeric_fields"])), "可直接用于聚合或统计")
    with metric_cols[3]:
        sheet_label = meta.get("sheet_name") or "CSV / 单表"
        _render_metric_card("可用图表", str(len(SUPPORTED_CHARTS)), sheet_label)

    st.markdown('<div class="panel-card">', unsafe_allow_html=True)
    preview_tab, profile_tab = st.tabs(["数据预览", "字段识别"])
    with preview_tab:
        st.dataframe(df.head(20), use_container_width=True, height=360)
    with profile_tab:
        cols = st.columns(3)
        cols[0].write("**数值字段**")
        cols[0].write(profile["numeric_fields"] or ["未识别"])
        cols[1].write("**日期字段**")
        cols[1].write(profile["date_fields"] or ["未识别"])
        cols[2].write("**分类 / 文本字段**")
        cols[2].write((profile["categorical_fields"] + profile["text_fields"]) or ["未识别"])
    st.markdown("</div>", unsafe_allow_html=True)


def _render_input_panel() -> tuple[str, bool]:
    st.markdown('<div class="panel-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">分析需求</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-desc">请明确填写你希望系统分析的问题、对象或图表诉求。为了避免输出无意义内容，本区域现在为必填项。</div>', unsafe_allow_html=True)
    question = st.text_area(
        "请输入分析需求",
        value=st.session_state.last_question,
        height=160,
        placeholder="例如：分析各区域订单结构；看不同产品线的趋势变化；总结这份表里最值得汇报的 3 个重点",
        label_visibility="collapsed",
    )
    controls = st.columns([1.5, 1])
    with controls[0]:
        st.caption("提示：写清对象、指标、排序方式或图表类型，系统响应会更快、更稳定。")
    with controls[1]:
        run = st.button("开始分析", type="primary", use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)
    return question, run


def _render_loading_state(stage: str) -> str:
    return f"""
    <div class="loading-shell">
        <div class="loading-ring"></div>
        <div class="loading-title">系统正在生成分析结果</div>
        <div class="loading-subtitle">请稍候，当前将依次完成字段检查、计划生成与图表整理。</div>
        <div class="loading-stage">{stage}</div>
        <div class="loading-stage-list">
            <span class="loading-chip">字段与图表条件检查</span>
            <span class="loading-chip">分析计划匹配</span>
            <span class="loading-chip">结果与解读整理</span>
        </div>
    </div>
    """


def _run_if_needed(question: str, run: bool) -> None:
    if not run:
        return

    df = st.session_state.df
    profile = st.session_state.profile
    if df is None or profile is None:
        st.warning("请先上传文件。")
        return

    final_question = resolve_question(question)
    if not final_question:
        st.warning("请先填写分析需求，再开始分析。")
        return

    st.session_state.last_question = final_question
    loading_placeholder = st.empty()
    progress_placeholder = st.empty()
    loading_placeholder.markdown(_render_loading_state("步骤 1/3：正在检查数据字段与图表生成条件"), unsafe_allow_html=True)
    progress_bar = progress_placeholder.progress(16, text="正在检查数据字段与图表生成条件...")
    client = build_client(
        api_key=st.session_state.api_key_input,
        model=st.session_state.model_name,
        base_url=st.session_state.base_url,
    )
    loading_placeholder.markdown(_render_loading_state("步骤 2/3：正在生成分析计划并匹配图表"), unsafe_allow_html=True)
    progress_bar.progress(52, text="正在生成分析计划并匹配图表...")
    run_result = run_analysis(
        df=df,
        profile=profile,
        question=final_question,
        file_name=st.session_state.file_name,
        client=client,
    )
    loading_placeholder.markdown(_render_loading_state("步骤 3/3：正在整理图表结果与解读内容"), unsafe_allow_html=True)
    progress_bar.progress(88, text="正在整理图表结果与汇报解读...")
    st.session_state.analysis_result = {
        "question": run_result.question,
        "plan": run_result.plan,
        "result": run_result.result,
        "insights": run_result.insights,
        "llm_error": run_result.llm_error,
        "llm_used": run_result.llm_used,
        "plan_warnings": run_result.plan_warnings,
        "plan_source": run_result.plan_source,
    }
    progress_bar.progress(100, text="分析完成")
    loading_placeholder.empty()
    progress_placeholder.empty()


def _render_plan_summary(analysis_result: Dict[str, Any]) -> None:
    plan = analysis_result["plan"]
    st.markdown('<div class="panel-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">分析理解</div>', unsafe_allow_html=True)
    plan_source = "大模型生成" if analysis_result.get("plan_source") == "llm" else "本地规则生成"
    st.caption(f"计划来源：{plan_source}")
    st.write("系统已经根据你的需求，对主要分析对象、指标、时间口径和输出图表进行了整理：")
    for line in summarize_plan(plan):
        st.write(f"- {line}")

    warnings = analysis_result.get("plan_warnings") or []
    warnings += analysis_result.get("result", {}).get("warnings", [])
    unique_warnings = []
    for item in warnings:
        if item not in unique_warnings:
            unique_warnings.append(item)
    if unique_warnings:
        st.warning("已根据实际字段做了自动修正：")
        for item in unique_warnings:
            st.write(f"- {item}")
    st.markdown("</div>", unsafe_allow_html=True)


def _render_analysis_result() -> None:
    analysis_result = st.session_state.analysis_result
    if not analysis_result:
        st.markdown('<div class="panel-card">', unsafe_allow_html=True)
        st.subheader("结果区")
        st.write("分析完成后，这里会展示图表、结论和系统对需求的理解过程。")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    if analysis_result.get("llm_used"):
        st.success("本次分析已调用大模型生成计划与结论。")
    elif analysis_result.get("llm_error"):
        st.info(f"本次未成功调用大模型，已切换本地兜底分析：{analysis_result['llm_error']}")

    st.markdown('<div class="panel-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">本次需求</div>', unsafe_allow_html=True)
    st.write(analysis_result["question"])
    st.markdown("</div>", unsafe_allow_html=True)
    _render_plan_summary(analysis_result)

    chart_specs: List[Dict[str, Any]] = analysis_result["result"].get("charts", [])
    if analysis_result["result"].get("substitute_chart_used"):
        st.warning("未能直接生成你指定的图表类型，下面展示的是系统提供的替代概览图。")
    if not chart_specs:
        st.warning("没有生成可展示的图表，请尝试换一种更明确的描述方式。")
    else:
        for idx, chart in enumerate(chart_specs, start=1):
            st.markdown('<div class="panel-card">', unsafe_allow_html=True)
            st.markdown(f"### 图表 {idx}：{chart.get('title', '未命名图表')}")
            st.plotly_chart(build_plotly_figure(chart), use_container_width=True)
            table = chart.get("table") or []
            if table:
                with st.expander(f"查看图表 {idx} 对应数据", expanded=(idx == 1)):
                    st.dataframe(pd.DataFrame(table), use_container_width=True, height=260)
            st.markdown("</div>", unsafe_allow_html=True)

    insights = analysis_result["insights"]
    st.markdown('<div class="panel-card">', unsafe_allow_html=True)
    st.subheader("AI 汇报解读")
    st.markdown(f"**摘要**：{insights.get('summary', '-')}")

    executive_brief = insights.get("executive_brief")
    if executive_brief:
        st.markdown("**管理层速览**")
        st.write(executive_brief)

    findings = insights.get("key_findings", [])
    if findings:
        st.markdown("**关键发现**")
        for item in findings:
            st.write(f"- {item}")

    takeaways = insights.get("management_takeaways", [])
    if takeaways:
        st.markdown("**汇报要点**")
        for item in takeaways:
            st.write(f"- {item}")

    risks = insights.get("risks", [])
    if risks:
        st.markdown("**风险与提醒**")
        for item in risks:
            st.write(f"- {item}")

    suggestion = insights.get("suggestion")
    if suggestion:
        st.markdown(f"**建议**：{suggestion}")

    with st.expander("查看分析计划 JSON", expanded=False):
        st.code(json.dumps(analysis_result["plan"], ensure_ascii=False, indent=2), language="json")
    with st.expander("查看结果数据摘要", expanded=False):
        st.code(json.dumps(analysis_result["result"].get("stats", {}), ensure_ascii=False, indent=2), language="json")
    st.markdown("</div>", unsafe_allow_html=True)


def main() -> None:
    _init_state()
    _render_header()
    _render_sidebar()

    st.markdown('<div class="panel-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">上传数据</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-desc">先接入数据，再明确填写分析需求。页面将按从上到下的顺序展示数据、理解过程和图表结果。</div>', unsafe_allow_html=True)
    uploaded_file = st.file_uploader("上传表格文件", type=["xlsx", "xls", "csv"], label_visibility="collapsed")
    _load_uploaded_file(uploaded_file)
    st.markdown("</div>", unsafe_allow_html=True)

    _render_dataset_summary()
    question, run = _render_input_panel()
    _run_if_needed(question, run)
    _render_analysis_result()


main()
