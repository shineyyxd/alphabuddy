# AlphaBuddy 后端

面向投资研究者的透明 Agent 工作台后端。FastAPI + LangGraph（Supervisor → Planner → interrupt 审批 → Researcher → Reporter），SSE 流式，SQLite 检查点/审计，双数据源（扶摇 REST + iFinD MCP）三态降级（ok / missing_key / fixture）。

## 启动

```bash
cd app/backend
uv sync
# 环境变量见 ../.env.example；无任何 Key 也能以 fixture 回放模式跑通全流程
ALLOW_FIXTURE_FALLBACK=true uv run uvicorn app.main:app --port 8000
# 或使用 env 文件：uv run --env-file ../.env uvicorn app.main:app --port 8000
```

测试：`uv run pytest`（LLM 全部 mock/降级，不真调）。

## 无 Key fixture 模式 curl 走通序列

```bash
# 1. 创建线程（命题验证：寒武纪）
TID=$(curl -s -X POST localhost:8000/api/threads -H 'Content-Type: application/json' \
  -d '{"goal":"验证寒武纪盈利改善来自主营业务","skill":"thesis_check"}' | jq -r .thread_id)

# 2. 首次运行：SSE 流出 run_started → plan → interrupt（计划审批点，流结束）
curl -N -X POST localhost:8000/api/threads/$TID/run -H 'Content-Type: application/json' \
  -d '{"resume_token":null}'

# 3.（可选）刷新恢复：完整状态快照（plan 从 interrupt 事件还原）
curl -s localhost:8000/api/threads/$TID/state | jq .status   # awaiting_approval

# 4. 审批（也可 {"action":"edit","plan":[...]} 编辑计划后再批准）
curl -s -X POST localhost:8000/api/threads/$TID/approve -H 'Content-Type: application/json' \
  -d '{"action":"approve"}'

# 5. 继续运行：step_start/tool_call_start/tool_call_result/step_done ×4
#    → artifact_delta/artifact_done（含证据清单/待核实事项/失效条件）→ memory_write → done
curl -N -X POST localhost:8000/api/threads/$TID/run -H 'Content-Type: application/json' \
  -d '{"resume_token":null}'

# 6. 产物 / 审计 / 能力页
curl -s localhost:8000/api/threads/$TID/state | jq -r .artifacts[0].markdown
curl -s localhost:8000/api/threads/$TID/audit | jq .
curl -s localhost:8000/api/capabilities | jq .
```

关键 SSE 事件序列（fixture 模式实测）：

```
run_started → plan → interrupt                       # 第一次 /run，停在审批点
run_started → step_start → tool_call_start → tool_call_result → step_done (×4)
            → warning{kind:"degraded"} (fixture 回放提示)
            → artifact_delta → artifact_done → memory_write → cost → done
```

## 架构要点

- **LangGraph 硬能力**：`AsyncSqliteSaver` 检查点（服务重启后审批/断点续跑已验证）、`interrupt()` 计划审批、`InMemoryStore` 长期记忆（namespace `user_memories`，跨线程命中"上次研究的…"）、`recursion_limit` + token 预算 + 单工具 10s 超时停止规则（触发发 `stopped` 事件）。
- **工具信封铁律**：每个工具返回 `{data, source, as_of, unit, caliber, fetched_at, auth, error}`；每次调用写 `tool_audit` 表。报告中的关键数字由后端从信封渲染（`_evidence_rows`），LLM 只写解释文字，不可编造数字。
- **三态数据源**：无 Key + `ALLOW_FIXTURE_FALLBACK=true` → 回放 `fixtures/`（寒武纪 2026 中报已验证数据）；无 Key + false → `error.kind=missing_key` 显式降级，步骤标 failed 不阻塞后续；有 Key → 真调（扶摇 `X-api-key` 头；iFinD streamable-http JSON-RPC + Bearer，2026-09-24 实测 tools/list 全部为自然语言 query 风格工具：`ifind_fin_indicator`/`ifind_fin_statement` → `get_stock_financials`，`ifind_announcement` → `get_stock_events`，返回 markdown 表格由后端解析为指标字段，解析失败则原文入 data 不崩；**证券代码校验**：iFinD 会把不存在的代码模糊匹配到相近真实标的，normalize 校验返回代码与请求一致，不一致按标的不存在转错误信封）。`ifind_news` 已移除（真实无对应工具）。
- **LLM（推理模型适配）**：结论解读由 LLM 撰写；**命题判定句与关键数字由程序基于证据渲染**（判定即数字的函数），prompt 禁止 LLM 出现证据外数字及任何算术加工；content 为空（reasoning 吃光 max_tokens）时自动放大重试；成本读 usage。
- **合规**：输入守卫拦截涨跌预测/买卖建议（`warning{kind:"guard"}`，不进图）；报告强制含待核实事项与失效条件；页脚 disclaimer。
- **上下文压缩**：`context_blob` 超 `COMPRESS_THRESHOLD_CHARS`（默认 24000）时摘要压缩并发 `compress` 事件。

## 目录

```
app/
  main.py            # REST + SSE 端点（API 契约 §1/§2）
  graph.py           # LangGraph 图：supervisor/planner(interrupt)/researcher/reporter/stopped
  skills.py          # 3 张技能卡（thesis_check/earnings_review/watchlist_brief）
  guard.py           # 输入合规守卫
  llm.py             # OpenAI 兼容 LLM 客户端（无 Key 显式降级）
  cost.py            # 成本累计器（Langfuse 可选）
  events.py          # 线程级事件总线（回放 + 订阅）
  tools/             # ToolRegistry + 扶摇/iFinD 客户端 + 信封/审计/fixture
fixtures/            # 寒武纪 688256.SH 2026 中报录制数据
tests/               # 22 个单测（信封/守卫/降级/interrupt-resume/停止规则/API+SSE 全流程）
```

## 已知边界

- InMemoryStore 进程内有效，重启后长期记忆丢失（升级路径：PostgresStore）；检查点与审计在 SQLite 中持久。
- iFinD MCP 工具名未经真实服务校验（无 token），`_resolve_tool` 做了 tools/list 关键字匹配兜底，连不通时自动走降级。
- `resume_token` 当前语义：不带审批决定时只回放事件不推进图；审批决定经 /approve 暂存后由 /run 消费。
- 单用户单例，无账户体系（设计使然）。
