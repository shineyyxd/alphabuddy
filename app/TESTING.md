# 测试说明（题目 13 交付物）

执行环境：macOS，本机（后端 :8000 / 前端 :3000）  日期：2026-09-23（fixture 轮）/ 2026-09-24（真实数据源复测轮）
数据源状态：扶摇 ☑ok（2026-09-24 实测） ☐fixture ☐down；iFinD ☑ok（2026-09-24 实测，MCP initialize/tools-list/tools-call 全通）☐fixture ☐down；LLM：☑ok（DeepSeek deepseek-flash，2026-09-24 实测）
> 注：T1–T12 已在 fixture 回放模式下执行；T6/T7 已于 2026-09-24 用真实数据源复测（见下）。单元测试 22 个全绿（`uv run pytest`，conftest 强制清 Key 走 fixture）。真实数据源端到端 + 评测集复跑见 `app/benchmark/README.md` 基线 v3。

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
| T6 | 不存在标的 | 显式报错不编造 | ✅ 通过（fixture + 真实数据源复测） | fixture 模式：999999.SH 4 工具均 missing_key 错误卡，无编造数值。真实复测（2026-09-24）：评测集 deg-01/02/03 三条用例在真实 Key 下复跑，错误信封 + 防编造核验均通过（benchmark 基线 v3） |
| T7 | 字段未披露 | 灰卡"数据未披露" | ✅ 通过（真实数据源复测） | 真实复测（2026-09-24）：iFinD 真实返回中缺失单元格（如 2026Q1 主营收入为制表空位）解析为 null 透传不补零，证据表跳过该字段，待核实事项保留"扣非/明细需查原文"提示；真实 LLM 结论仅引用证据内数字 |
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
3. **真实 LLM 算术加工缺陷（2026-09-24 联调发现）**：接入 deepseek-flash 后，Reporter 结论出现证据中不存在的衍生数字（把投资收益 0.83 亿 + 其他收益 1.67 亿加成"约 2.51 亿"），违反"数字必须回指信封"铁律，被评测集通用防编造核验捕获。修复：结论 prompt 增加"禁止对证据数字做任何算术加工（合计/差值/倍数/取整变形），每个数字必须原样引用证据值"。
4. **推理模型正文为空风险（2026-09-24 联调预防）**：deepseek-flash 为推理模型，max_tokens 过小时 reasoning 会吃光额度导致 content 为空。修复：llm.py 解析仅取 content（reasoning_content 由 langchain 放入 additional_kwargs），content 为空时自动放大 max_tokens×2 重试；成本统计读 usage_metadata。
5. **ifind_announcement 信封 as_of 缺失（评测集基线 v2 发现，v3 修复）**：公告类信封缺时点导致证据四要素齐全率 0.75。修复：iFinD get_stock_events 真实返回的披露日期（如 20260808）解析提升到信封 as_of。

## 真实数据源联调记录（2026-09-24）

- **扶摇 REST（X-api-key）**：prices/snapshot、valuations/snapshot、financials/indicators、financials/income-statements 四端点对 688256.SH 全部 code=0 实测通过；真实营收 5,995,573,619.61 元、营收同比 108.1331%、毛利率 55.2506%，与 fixtures 录制值一致（行情/估值随交易日漂移，中报指标不变）。
- **iFinD MCP（Bearer + JSON-RPC）**：实测 tools/list 全部为自然语言 query 风格工具，已完成映射：ifind_fin_indicator / ifind_fin_statement → get_stock_financials，ifind_announcement → get_stock_events；ifind_news 无对应工具，从注册表移除。返回为 markdown 表格文本，后端解析为标准字段（解析失败则原文入 data，不崩）。
- **iFinD 与 fixtures 对账**：营收 59.9557 亿 ✓、营收同比 108.1331 ✓、归母 23.1091 亿 ✓、归母同比 122.6135 ✓、扣非同比 137.3038 ✓、毛利率 55.2506 ✓、净利率 38.541 ✓、研发费用率 11.7164 ✓、投资收益 8327 万 ✓、其他收益 1.6725 亿 ✓、资产减值 3.9702 亿 ✓；fixtures 未录的扣非绝对额真实值为 21.6556 亿；主营占比真实计算值 99.9922%（fixtures 录 99.9995%，差异源于 fixtures 按 59.951/59.9557 亿元口径的舍入，真实值以 iFinD 返回为准）。
- **延迟观察**：iFinD 指标类 query 单次约 6–9s，贴近 10s 单工具超时上限，偶发超时会按设计降级（fixture 或错误信封），属已知风险。
- 评测集真实模式复跑结果见 `app/benchmark/README.md` 基线 v3。
