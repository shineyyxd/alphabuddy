# AlphaBuddy — 前后端 API 契约（v1，开工冻结）

后端：FastAPI（Python 3.12，uv 管理），默认端口 8000，SSE 流式。
前端：Next.js 14+（App Router）+ Tailwind，默认端口 3000，代理 /api → 8000。

所有 API 路径以 `/api` 开头。所有时间用 ISO8601。金额单位随数据源原始值，由 `unit` 字段标明。

---

## 1. REST 端点

### POST /api/threads
创建研究线程。
- 请求：`{ "goal": string, "skill": "thesis_check" | "earnings_review" | "watchlist_brief" | null }`
- 响应：`{ "thread_id": string }`
- skill 为 null 时由 Supervisor 意图识别自动匹配技能卡。

### GET /api/threads
线程列表。响应：`{ "threads": [{ "thread_id", "goal", "skill", "status", "created_at", "updated_at" }] }`
status ∈ `planning | awaiting_approval | running | interrupted | done | failed`

### GET /api/threads/{thread_id}/state
完整状态快照（用于刷新页面后恢复 UI）：
```json
{
  "thread_id": "…", "goal": "…", "skill": "thesis_check", "status": "running",
  "plan": [{ "id": "s1", "title": "…", "tool": "ifind_fin_indicator", "status": "done" }],
  "events": [ /* 迄今所有 SSE 事件，按序 */ ],
  "artifacts": [{ "id", "kind": "report", "title", "markdown" }],
  "cost": { "tokens_in": 0, "tokens_out": 0, "llm_calls": 0, "tool_calls": 0, "elapsed_ms": 0, "budget_remaining": 0 }
}
```

### POST /api/threads/{thread_id}/run
启动或恢复执行（包括首次运行、审批后继续、刷新后断点续跑）。
- 请求：`{ "resume_token": string | null }`
- 响应：`text/event-stream`（SSE，事件格式见 §2）

### POST /api/threads/{thread_id}/approve
对 interrupt 审批点做决定。
- 请求：`{ "action": "approve" | "edit", "plan": [/* 编辑后的计划，action=edit 时必带 */] }`
- 响应：`{ "ok": true }`，随后客户端再调 /run 继续。

### GET /api/capabilities
工具注册表（能力页数据源）：
```json
{ "tools": [{ "name", "display_name", "description", "source": "fuyao|ifind", "params_schema": {}, "returns": ["data","source","as_of","unit","caliber"] }] }
```

### GET /api/threads/{thread_id}/audit
审计日志：该线程每次工具调用 `{ ts, tool, params, latency_ms, auth: "ok|missing_key|fixture", status, error }`。

---

## 2. SSE 事件（/run 流，前端步骤流的数据源）

每个事件：`event: <type>\ndata: <json>\n\n`

| type | data 关键字段 | 说明 |
|---|---|---|
| `run_started` | `{thread_id, skill}` | 开始/恢复 |
| `plan` | `{steps: [{id,title,tool}]}` | Planner 产出计划 |
| `interrupt` | `{kind:"plan_approval", plan}` | 等待人工审批（UI 显示审批卡） |
| `step_start` | `{step_id, title}` | 计划某步开始 |
| `tool_call_start` | `{step_id, call_id, tool, params}` | 工具调用卡（入参） |
| `tool_call_result` | `{step_id, call_id, tool, status:"ok|empty|error|degraded", envelope}` | envelope 含 data/source/as_of/unit/caliber 或 error 原因 |
| `conflict` | `{step_id, field, sources: [{source,value,as_of}]}` | 双源冲突标记 |
| `compress` | `{before_chars, after_chars}` | 上下文压缩事件 |
| `memory_write` | `{key, summary}` | 写入长期记忆 |
| `step_done` | `{step_id, status:"ok|failed|skipped"}` | 失败不阻塞后续步骤 |
| `artifact_delta` | `{artifact_id, kind:"report", delta}` | 报告流式增量 |
| `artifact_done` | `{artifact_id, kind, title, markdown}` | 产物完成（含证据清单/待核实事项/失效条件） |
| `cost` | `{tokens_in, tokens_out, llm_calls, tool_calls, elapsed_ms, budget_remaining}` | 成本条更新（每次 LLM/工具调用后发） |
| `warning` | `{kind:"degraded|guard", message}` | 降级提示 / 合规拦截提示 |
| `stopped` | `{reason:"step_limit|token_budget|timeout"}` | 触发停止规则 |
| `done` | `{status:"done|failed", summary}` | 结束 |

---

## 3. 工具统一返回信封（工具层铁律）

```json
{
  "data": { /* 原始字段 */ },
  "source": "fuyao | ifind",
  "as_of": "2026-06-30",
  "unit": "元 | % | 亿元 …",
  "caliber": "口径说明，如：扣除非经常性损益后归属母公司净利润，同比",
  "fetched_at": "2026-09-23T10:00:00",
  "auth": "ok | missing_key | fixture",
  "error": null
}
```
失败时 `data=null` 且 `error={kind, message}`，调用方必须生成"无法验证/降级"卡片，禁止静默跳过。

## 4. 合规拦截

- 输入守卫：命中涨跌预测/买卖建议意图 → `warning{kind:"guard"}` + 引导话术，不进入计划。
- 输出核验：产物中的关键数字由后端从工具信封渲染，LLM 只生成解释文字。
