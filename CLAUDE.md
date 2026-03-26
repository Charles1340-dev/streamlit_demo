# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 提供该代码仓库的工作指引。

## 项目概述

这是一个基于 Streamlit 的智能表格分析 Web 演示项目，通过 DeepSeek 大模型驱动。用户上传 Excel/CSV 数据文件，用中文输入分析需求，系统自动生成图表（柱状图、折线图、饼图、散点图等）并附带 AI 生成的分析解读。

## 开发命令

```bash
# 安装依赖
pip install -r requirements.txt

# 启动应用
streamlit run app.py

# 通过环境变量设置 API 密钥（可选，也可在 UI 中设置）
export DEEPSEEK_API_KEY=your_key_here
```

## 架构设计

### 入口文件
- **app.py**: Streamlit UI 入口。处理文件上传、会话状态管理、侧边栏配置，并协调整个分析流程。

### 核心模块

**llm_client.py**
- `DeepSeekClient` 类：封装对 DeepSeek 的 OpenAI 兼容 API 调用
- `generate_analysis_plan()`: 将数据画像和用户问题发送给 LLM，返回 JSON 分析计划
- `generate_insights()`: 将分析结果发送给 LLM，返回中文解读（摘要/关键发现/建议）
- 未配置 API 密钥时自动降级到本地分析

**analyzer.py**
- `build_fallback_plan()`: 基于规则的分析计划生成器，当 LLM 不可用或失败时使用
- `apply_analysis_plan()`: 执行分析计划，对 DataFrame 进行计算，返回图表数据和统计信息
- 包含字段匹配逻辑，支持中文业务术语同义词（收账/回款/收入/成本/利润/部门/项目/客户）
- 支持的图表类型：柱状图、折线图、饼图、散点图、面积图、直方图、箱线图、漏斗图、树图

**excel_parser.py**
- `load_uploaded_table()`: 解析 .xlsx/.xls/.csv 文件，返回 DataFrame 和元数据
- `build_dataframe_profile()`: 分析 DataFrame 列，将字段分类为数值型/日期型/分类型/文本型

**chart_builder.py**
- `build_plotly_figure()`: 将图表规格字典转换为 Plotly 图表对象以供展示

**prompts.py**
- LLM 调用的系统提示词（`ANALYSIS_PLAN_SYSTEM_PROMPT`、`INSIGHT_SYSTEM_PROMPT`）

### 数据流

1. 用户上传文件 → `excel_parser.load_uploaded_table()` 解析
2. `excel_parser.build_dataframe_profile()` 创建字段类型画像
3. 用户输入问题 → `llm_client.generate_analysis_plan()` 从 LLM 获取分析计划（或使用兜底策略）
4. `analyzer.apply_analysis_plan()` 执行计划 → 生成图表数据 + 统计信息
5. `llm_client.generate_insights()` 生成中文解读（或使用兜底策略）
6. `chart_builder.build_plotly_figure()` 在 Streamlit 中渲染图表

### 关键配置

- API 密钥可通过 `DEEPSEEK_API_KEY` 环境变量设置，或在 UI 侧边栏输入
- 默认模型：`deepseek-chat`
- 默认 Base URL：`https://api.deepseek.com`

### 文件上传行为

- 支持 `.xlsx`、`.xls`、`.csv` 格式
- Excel 文件仅读取第一个工作表
- 临时上传文件存储在 `temp_uploads/` 目录

### 字段识别机制

分析器使用中文同义词匹配用户查询与 DataFrame 列：
- 数值字段：收账/收款/回款、收入/营收、成本/费用、利润/毛利
- 维度字段：部门/团队、项目、客户/客商、供应商
- 日期字段：列名包含 日期/时间/月份 的字段
