# 智能表格分析 Streamlit Demo（DeepSeek）

这是一个可快速演示的网页 Demo：

- 上传 Excel / CSV
- 输入一句中文分析需求
- 后端调用 DeepSeek 生成分析计划
- 本地用 pandas 计算图表数据
- 页面输出柱图 / 饼图 / 折线图 + 文字解释

## 1. 安装依赖

```bash
pip install -r requirements.txt
```

## 2. 配置 API Key

Linux / macOS:

```bash
export DEEPSEEK_API_KEY=你的key
```

Windows PowerShell:

```powershell
$env:DEEPSEEK_API_KEY="你的key"
```

也可以直接在网页左侧侧边栏手动输入 key。

## 3. 启动项目

```bash
streamlit run app.py
```

启动后浏览器会自动打开页面。

## 4. 推荐演示方式

### 演示一
问题：

```text
分析各部门的收账情况
```

### 演示二
问题：

```text
按月份看回款趋势
```

### 演示三
问题：

```text
分析收入、成本和利润情况
```

## 5. 当前限制

- 默认只读取第一个 Sheet
- 暂未支持多表关联
- 利润等复杂口径优先使用表中现有字段
- 如果大模型调用失败，会自动回退到本地规则兜底分析

## 6. 建议的表格字段

为了更好识别，列名尽量带有以下业务词：

- 部门
- 收款 / 回款 / 收账
- 收入 / 营收
- 成本
- 利润 / 毛利
- 日期 / 时间 / 月份

