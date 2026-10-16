# 阿里云百炼模型联通与应用能力测试

测试日期：2026-10-13（北京时间）

## 结论

`life-circle-assistant/.env` 中的百炼配置能够成功鉴权并调用 `qwen3.7-flash`。实际请求返回 HTTP 200，中文回复、JSON 输出、项目自然语言需求提取和体检报告解读均通过测试。

当前运行在 `http://127.0.0.1:8000` 的后端也已加载模型配置；通过页面使用的 `/api/analysis/intent` 接口实测，返回 `parser=llm`，并正确提取分析参数。

原生工具调用与工具结果回传成功，但规划助手在两次合成报告测试中均降级为 `tool_rules_degraded`。复测确认模型最终回复的 Markdown 代码块，以及摘要中的数量表述，会分别触发项目校验失败。这属于应用输出兼容问题，不能据此判断百炼密钥或接口不通。

## 测试范围与结果

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| 配置读取 | 通过 | `LLM_ENABLED=true`，适配器为 `openai_compatible`，模型为 `qwen3.7-flash`，密钥已配置 |
| 实际鉴权、模型请求、中文与 JSON 输出 | 通过 | HTTP 200；JSON 为 `{"ok":true,"answer":42,"message":"已收到测试请求"}`；约 12.13 秒 |
| 项目需求提取函数 | 通过 | `parser=llm`；正确提取沙涌长盛花园、15 分钟、快速分析、菜市场与药店；约 16.82 秒 |
| 项目报告解读函数 | 通过 | 合成报告返回 `mode=llm_structured`，包含摘要与报告证据引用；端到端约 57.06 秒 |
| 原生工具调用及结果回传 | 通过 | API 返回 `finish_reason=tool_calls`；实际执行 `query_facilities` 等工具，结果再次传回模型并获得最终回答 |
| 工具规划助手完整流程 | 未通过 | 两次测试均返回 `tool_rules_degraded`；工具执行成功，但模型最终回答未通过应用校验 |
| 当前运行后端需求解析接口 | 通过 | `POST /api/analysis/intent` 返回 HTTP 200、`parser=llm`、`model=qwen3.7-flash`；约 16.49 秒 |

测试使用项目现有模型适配器和默认请求参数。报告解读和工具规划使用合成报告，未调用真实地图接口，也未创建体检任务或保存业务报告。

报告解读耗时为整个函数调用耗时，不等同于单次 HTTP 耗时；本次未进一步拆分排队和重试耗时，也不构成性能基准。

## 当前服务核验

测试开始时，8000 端口服务仍返回模型未启用，需求解析为 `parser=rules`。测试期间服务状态发生变化，最终复查和真实请求确认新配置已生效；测试过程没有执行服务重启。

最终健康检查的模型部分为：

```json
{
  "enabled": true,
  "available": true,
  "provider": "openai_compatible",
  "model": "qwen3.7-flash",
  "missing": [],
  "calls": 1,
  "failures": 0,
  "average_latency_ms": 16461.9
}
```

上述计数来自运行中的后端；独立测试进程的调用不计入其中。

实际接口测试输入：

> 体检沙涌长盛花园，步行15分钟，快速分析，仅关注买菜和买药

接口输出中的关键字段：

```json
{
  "parser": "llm",
  "model": "qwen3.7-flash",
  "draft": {
    "address": "沙涌长盛花园",
    "use_current_center": false,
    "minutes": 15,
    "mode": "demo",
    "categories": ["market", "pharmacy"],
    "defaulted_fields": []
  },
  "missing_fields": []
}
```

## 工具回答兼容问题

定位位置：`life-circle-assistant/backend/app/planning_assistant.py` 的 `_validate_answer`。

复测中，模型返回的内容以 Markdown 的 JSON 代码块包裹；应用直接调用 `json.loads`，产生 `JSONDecodeError`。该次摘要还包含“匹配到一处菜市场设施”，其中“一处”被摘要数值校验拒绝。

用捕获的内容离线重放校验器，三个断言全部通过：

| 重放内容 | 应用校验 |
| --- | --- |
| 原始代码块与数量表述 | 拒绝 |
| 仅移除代码块，保留“一处” | 拒绝 |
| 纯 JSON，摘要改为定性表述，保留原合法证据引用 | 通过 |

这说明需要同时处理输出格式和摘要约束。当前测试范围为联通性及能力验证，没有修改模型配置或产品代码。待评估问题见 [工具回答兼容问题](issues/01-tool-answer-validation.md)。

测试记录不包含 API 密钥或鉴权头。

## 兼容修复与复测（2026-10-13）

以上失败结果为修复前的测试记录。本次按用户要求实现了以下修复：

- 只剥离完整的 JSON 或无语言标记 Markdown 代码块；外围说明、截断和非法 JSON 不放行。
- 先核验证据，再对包含“一处”“两处”或数值的摘要请求一次定性改写，改写再次经过原校验。
- 改写只能使用已有成功工具结果及合法引用，不执行工具，纳入五轮模型请求与九十秒预算；失败保留真实结果并降级。
- 加强输出提示词，版本更新为 `tool-planner-v2`；前后端继续接受旧版问答追问。

回归命令：在 `life-circle-assistant/backend` 执行 `LLM_ENABLED=false .venv/bin/python -m pytest tests/test_planning_assistant.py -q`。新增测试修复前为 11 项失败、1 项通过；实现后完整规划助手测试为 **43 项通过**。覆盖代码块、数量摘要校正、非法证据拒绝、失败和超时、预算上限、模拟不重复，以及历史追问兼容。前端 lint、类型检查、构建与完整测试通过（26 个文件、107 项测试）。后端 lint 与变更文件格式检查通过；全库格式检查仍有四个原有文件不合格：`app/exports/charts.py`、`app/exports/pdf.py`、`app/planning_comparison.py`、`tests/test_pdf_exports.py`。

百炼复测使用当前代码、新进程、原 `.env` 参数，以及带本地快照来源标记的合成报告。未调用真实地图接口，未保存业务报告：

| 场景 | 结果 | 证据 |
| --- | --- | --- |
| 原生规划完整流程 | 通过 | `qwen3.7-flash` 调用 `query_facilities` 并使用工具结果回答；`mode=llm_tools`，提示词 v2；两轮模型请求，未触发校正；约 6.74 秒 |
| 代码块与数量摘要重放，百炼真实校正 | 通过 | 重放 `匹配到一处菜市场设施，从分析中心步行8分钟。` 的 fenced JSON；真实百炼 JSON 请求改为定性摘要；`mode=llm_tools`，合法证据保留；校正一次，工具执行一次；约 18.96 秒 |

第二项的初始工具选择与违规回答是确定性重放，校正请求由真实百炼模型完成。两项测试分别完成两次及一次成功模型调用，无模型调用失败。耗时是单次端到端观测，不构成性能基准。

相关后端回归 `test_llm.py`、`test_ai_assistant.py`、`test_planning_comparison.py`、`test_simulations.py`、`test_analysis_intent.py` 另有 **54 项通过**，与规划助手合计 97 项。`git diff --check` 通过，未保留调试日志。运行中的 8000 端口后端健康且百炼配置已启用，但启动参数未开启热重载；本次没有重启该服务，新代码须重启后端后才会在页面请求中生效。

校正后摘要：

> 报告匹配到菜市场设施，具体数量与步行信息见工具结果。
