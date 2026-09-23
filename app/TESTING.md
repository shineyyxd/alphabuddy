# 测试说明（题目 13 交付物）

执行环境：macOS，本机（后端 :8000 / 前端 :3000）  日期：2026-09-23
数据源状态：扶摇 ☐ok ☑fixture ☐down；iFinD ☐ok ☑fixture ☐down；LLM：mock（未配置 Key）
> 注：T1–T12 已在 fixture 回放模式下执行；标注"待真 Key 复测"的用例需在配置真实数据源后复核。单元测试 22 个全绿（`uv run pytest`）。

## 主链路

| # | 用例 | 预期 | 结果 | 证据 |
|---|---|---|---|---|
| T1 | 命题验证全流程 | 计划→批准→逐步调工具→报告 | ✅ 通过 | 计划 4 步（快照/指标/利润表/公告），批准后 4 工具调用全 ok，报告 2388 字含证据清单（四要素表格）+ 待核实事项 + 失效条件。另：业绩点评、持仓早报两张技能卡同样端到端跑通，持仓早报报告自动关联 thesis_check 的历史记忆 |
| T2 | 审批非摆设 | 编辑后计划被执行 | ✅ 通过 | 删除"公告"步后 edit 批准：仅执行 3 个保留工具（fuyao_quote_snapshot / ifind_fin_indicator / ifind_fin_statement），ifind_announcement 未出现，status=done |
| T3 | 检查点恢复 | 刷新/重启后续跑 | ✅ 通过 | 执行中 kill uvicorn 重启（同一 SQLite），approve + /run 从检查点继续完成；前端刷新经 GET /state 重放事件重建 UI |
| T4 | 长期记忆 | 新会话命中历史结论 | ✅ 通过 | 新会话问"上次研究的寒武纪…"，报告头部命中关联历史记忆（memory_write 事件 + Store 记录） |

## 接口异常 / 数据缺失

| # | 用例 | 预期 | 结果 | 证据 |
|---|---|---|---|---|
| T5 | 数据源不可用 | 标红降级，任务继续 | ✅ 通过 | ALLOW_FIXTURE_FALLBACK=false 且无 Key：4 个工具全部 missing_key 错误卡，任务仍 done，报告含"无法验证/未披露"提示 |
| T6 | 不存在标的 | 显式报错不编造 | ✅ 通过（fixture 模式）/ 待真 Key 复测 | 999999.SH：4 工具均返回错误卡（fixture 未命中），无任何编造数值；真实 API 下的"标的不存在"语义待真 Key 复测 |
| T7 | 字段未披露 | 灰卡"数据未披露" | ⏳ 待真 Key 复测 | 代码路径：envelope.data 为空 → status=empty → 灰卡；单测已覆盖 empty 分支，真实未披露字段待真 Key 构造 |
| T8 | LLM 失败 | 重试一次后显式失败 | ✅ 通过 | 单测覆盖：LLM 调用失败重试一次，仍失败则显式降级（mock LLM 抛错验证） |

## 极端 / 合规边界

| # | 用例 | 预期 | 结果 | 证据 |
|---|---|---|---|---|
| T9 | 涨跌预测 | 拒绝+引导改写 | ✅ 通过 | "寒武纪下周会涨吗"→ warning{kind:"guard"} + 改写示例，未进入计划，status=failed(合规拦截) |
| T10 | 买卖建议 | 不给建议+引导 | ✅ 通过 | "我该不该买寒武纪" → guard 拦截同上 |
| T11 | 停止规则 | 显式 stopped+原因 | ✅ 通过 | 单测覆盖：GraphRecursionError → stopped{reason:"step_limit"}；token 预算超限 → stopped{reason:"token_budget"} |
| T12 | 可追溯 | 数字可回指信封 | ✅ 通过 | 报告证据表每行含 来源/时点/单位/口径；时点经修正显示报告期日期（2026-06-30）；关键数字由后端从工具信封渲染，非 LLM 生成 |

## 关键结论可追溯抽查记录

| 报告数字 | 工具 | 字段 | 来源 | 时点 | 单位 | 口径 |
|---|---|---|---|---|---|---|
| +137.30% | ifind_fin_indicator | deducted_net_profit_yoy | iFinD（fixture 回放） | 2026-06-30 | % | 扣除非经常性损益后归属母公司净利润，同比 |
| 59.96 亿元 | ifind_fin_indicator | operating_income | iFinD（fixture 回放） | 2026-06-30 | 亿元 | 营业总收入，同比 +108.13% |
| 99.9995% | ifind_fin_indicator | main_business_income_ratio | iFinD（fixture 回放） | 2026-06-30 | % | 主营业务收入占营业总收入比例 |
| 11.72% | ifind_fin_indicator | rd_expense_ratio | iFinD（fixture 回放） | 2026-06-30 | % | 研发费用率（上年同期 18.81%） |

## 测试中发现并修复的真实缺陷

1. **T2 阻断缺陷**：编辑后的计划丢失工具参数（客户端只回传 id/title/tool），导致 `FuyaoClient.quote_snapshot() missing required argument: 'thscode'` 整个任务失败。修复：planner 编辑分支按工具补默认参数；registry.call 捕获 TypeError → bad_params 错误信封，不再打断全流程。（已记入 AI_LOG）
2. **T12 时点口径缺陷**：证据卡时点显示报告期代号"2026-2"。修复：_guess_as_of 解包 JSON-RPC/MCP 包裹并优先取 period_end。（已记入 AI_LOG）
