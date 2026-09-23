// 开发用 mock：一段完整 SSE 事件序列（契约 §2），?mock=1 模式回放，不依赖后端。
// 场景：技能卡① 命题验证 —— 验证"寒武纪盈利改善来自主营业务"
// 顺序：plan → interrupt(审批) → [批准后] 3 个工具调用(1 个 degraded) → conflict
//       → compress → artifact 流式 → memory_write → done，cost 事件贯穿。
import type { SseEvent } from "@/lib/types";

export const MOCK_THREAD_ID = "mock-thread-001";
export const MOCK_GOAL = "验证「寒武纪盈利改善来自主营业务」这一命题";

// 审批前：run_started → plan → interrupt，然后界面进入等待审批态
export const mockEventsBeforeApproval: SseEvent[] = [
  {
    type: "run_started",
    data: { thread_id: MOCK_THREAD_ID, skill: "thesis_check" },
  },
  {
    type: "plan",
    data: {
      steps: [
        { id: "s1", title: "获取行情快照与最新估值", tool: "fuyao_quote_snapshot" },
        { id: "s2", title: "拉取财务指标（毛利率/净利率/研发费用率）", tool: "ifind_fin_indicator" },
        { id: "s3", title: "拉取利润表，拆分主营收入与费用结构", tool: "ifind_fin_statement" },
        { id: "s4", title: "检索近期公告，定位非经常性损益线索", tool: "ifind_announcement" },
        { id: "s5", title: "生成命题验证报告", tool: null },
      ],
    },
  },
  {
    type: "interrupt",
    data: {
      kind: "plan_approval",
      plan: [
        { id: "s1", title: "获取行情快照与最新估值", tool: "fuyao_quote_snapshot" },
        { id: "s2", title: "拉取财务指标（毛利率/净利率/研发费用率）", tool: "ifind_fin_indicator" },
        { id: "s3", title: "拉取利润表，拆分主营收入与费用结构", tool: "ifind_fin_statement" },
        { id: "s4", title: "检索近期公告，定位非经常性损益线索", tool: "ifind_announcement" },
        { id: "s5", title: "生成命题验证报告", tool: null },
      ],
    },
  },
];

// 审批后：逐步执行 → 出报告 → 结束
export const mockEventsAfterApproval: SseEvent[] = [
  // ---- 步骤 1：行情快照（ok） ----
  { type: "step_start", data: { step_id: "s1", title: "获取行情快照与最新估值" } },
  {
    type: "tool_call_start",
    data: {
      step_id: "s1",
      call_id: "c1",
      tool: "fuyao_quote_snapshot",
      params: { symbol: "688256.SH" },
    },
  },
  {
    type: "tool_call_result",
    data: {
      step_id: "s1",
      call_id: "c1",
      tool: "fuyao_quote_snapshot",
      status: "ok",
      envelope: {
        data: { close: 1286.0, pct_chg: 2.31, turnover_rate: 3.85, total_mv: 5380.2 },
        source: "fuyao",
        as_of: "2026-09-22",
        unit: "元 / % / 亿元",
        caliber: "收盘价、涨跌幅、换手率、总市值，A 股日频",
        fetched_at: "2026-09-23T09:45:12",
        auth: "fixture",
        error: null,
      },
    },
  },
  {
    type: "cost",
    data: { tokens_in: 1820, tokens_out: 340, llm_calls: 2, tool_calls: 1, elapsed_ms: 4200, budget_remaining: 197840 },
  },
  { type: "step_done", data: { step_id: "s1", status: "ok" } },

  // ---- 步骤 2：财务指标（ok，带出冲突素材） ----
  { type: "step_start", data: { step_id: "s2", title: "拉取财务指标（毛利率/净利率/研发费用率）" } },
  {
    type: "tool_call_start",
    data: {
      step_id: "s2",
      call_id: "c2",
      tool: "ifind_fin_indicator",
      params: { symbol: "688256.SH", fields: ["gross_margin", "net_margin", "rd_expense_ratio"], period: "2026H1" },
    },
  },
  {
    type: "tool_call_result",
    data: {
      step_id: "s2",
      call_id: "c2",
      tool: "ifind_fin_indicator",
      status: "ok",
      envelope: {
        data: { gross_margin: 60.45, net_margin: 23.9, rd_expense_ratio: 21.3, net_profit_yoy: 412.5 },
        source: "ifind",
        as_of: "2026-06-30",
        unit: "%",
        caliber: "2026 半年报，归属母公司口径，同比",
        fetched_at: "2026-09-23T09:45:20",
        auth: "fixture",
        error: null,
      },
    },
  },
  {
    // 双源冲突：同一字段两个来源不一致，标记矛盾点，不强行统一
    type: "conflict",
    data: {
      step_id: "s2",
      field: "gross_margin",
      sources: [
        { source: "ifind（2026 半年报）", value: "60.45%", as_of: "2026-06-30" },
        { source: "扶摇（TTM 估算）", value: "58.10%", as_of: "2026-09-22" },
      ],
    },
  },
  {
    type: "cost",
    data: { tokens_in: 3100, tokens_out: 620, llm_calls: 3, tool_calls: 2, elapsed_ms: 9100, budget_remaining: 196280 },
  },
  { type: "step_done", data: { step_id: "s2", status: "ok" } },

  // ---- 步骤 3：利润表（degraded，演示降级可见） ----
  { type: "step_start", data: { step_id: "s3", title: "拉取利润表，拆分主营收入与费用结构" } },
  {
    type: "tool_call_start",
    data: {
      step_id: "s3",
      call_id: "c3",
      tool: "ifind_fin_statement",
      params: { symbol: "688256.SH", statement: "income", period: "2026H1" },
    },
  },
  {
    type: "tool_call_result",
    data: {
      step_id: "s3",
      call_id: "c3",
      tool: "ifind_fin_statement",
      status: "degraded",
      envelope: {
        data: null,
        source: "ifind",
        as_of: null,
        unit: null,
        caliber: null,
        fetched_at: "2026-09-23T09:45:31",
        auth: "missing_key",
        error: { kind: "auth", message: "iFinD MCP 登录态失效（JWE Token 过期），利润表数据不可用，改用公告文本推断" },
      },
    },
  },
  {
    type: "warning",
    data: { kind: "degraded", message: "数据源 iFinD 利润表接口降级：相关结论标记为「无法验证」，任务继续。" },
  },
  {
    type: "cost",
    data: { tokens_in: 3950, tokens_out: 810, llm_calls: 4, tool_calls: 3, elapsed_ms: 14600, budget_remaining: 195240 },
  },
  { type: "step_done", data: { step_id: "s3", status: "failed" } },

  // ---- 步骤 4：公告（ok） + 上下文压缩 ----
  { type: "step_start", data: { step_id: "s4", title: "检索近期公告，定位非经常性损益线索" } },
  {
    type: "tool_call_start",
    data: {
      step_id: "s4",
      call_id: "c4",
      tool: "ifind_announcement",
      params: { symbol: "688256.SH", limit: 5 },
    },
  },
  {
    type: "tool_call_result",
    data: {
      step_id: "s4",
      call_id: "c4",
      tool: "ifind_announcement",
      status: "ok",
      envelope: {
        data: {
          items: [
            { title: "2026 年半年度报告", date: "2026-08-28", pdf_url: "https://example.com/ann/2026h1.pdf" },
            { title: "关于获得政府补助的公告", date: "2026-07-15", pdf_url: "https://example.com/ann/subsidy.pdf" },
          ],
        },
        source: "ifind",
        as_of: "2026-09-22",
        unit: null,
        caliber: "公告标题 + PDF 链接，按披露日期倒序",
        fetched_at: "2026-09-23T09:45:40",
        auth: "fixture",
        error: null,
      },
    },
  },
  { type: "step_done", data: { step_id: "s4", status: "ok" } },
  {
    // 上下文压缩事件（管理上下文评分点）
    type: "compress",
    data: { before_chars: 48210, after_chars: 12340 },
  },
  {
    type: "cost",
    data: { tokens_in: 5200, tokens_out: 1250, llm_calls: 5, tool_calls: 4, elapsed_ms: 21300, budget_remaining: 193550 },
  },

  // ---- 步骤 5：报告流式产出 ----
  { type: "step_start", data: { step_id: "s5", title: "生成命题验证报告" } },
  {
    type: "artifact_delta",
    data: {
      artifact_id: "a1",
      kind: "report",
      delta: "## 结论\n\n**命题部分成立（置信度：中）。** 寒武纪 2026H1 净利率 23.9%、净利润同比 +412.5%（iFinD，2026-06-30，归属母公司口径），盈利改善显著；毛利率 60.45% 处于高位，支撑「主营驱动」的判断。但利润表明细因数据源降级**无法验证**，非经常性损益的贡献比例尚不能排除。\n\n",
    },
  },
  {
    type: "cost",
    data: { tokens_in: 6900, tokens_out: 2100, llm_calls: 6, tool_calls: 4, elapsed_ms: 28900, budget_remaining: 191000 },
  },
  {
    type: "artifact_delta",
    data: {
      artifact_id: "a1",
      kind: "report",
      delta: "## 证据清单\n\n| # | 事实 | 来源 | 时点 | 单位 | 口径 |\n|---|---|---|---|---|---|\n| 1 | 收盘价 1286.0，总市值 5380.2 | 扶摇 | 2026-09-22 | 元/亿元 | A 股日频 |\n| 2 | 毛利率 60.45 | iFinD | 2026-06-30 | % | 半年报，同比 |\n| 3 | 净利率 23.9，净利润同比 +412.5 | iFinD | 2026-06-30 | % | 归属母公司 |\n| 4 | 研发费用率 21.3 | iFinD | 2026-06-30 | % | 半年报 |\n| 5 | 毛利率 TTM 估算 58.10（与 #2 冲突，见下） | 扶摇 | 2026-09-22 | % | TTM 估算 |\n\n",
    },
  },
  {
    type: "artifact_delta",
    data: {
      artifact_id: "a1",
      kind: "report",
      delta: "### 来源冲突\n\n- **gross_margin**：iFinD 半年报 60.45%（2026-06-30）vs 扶摇 TTM 估算 58.10%（2026-09-22）——口径不同（定期报告 vs TTM 估算），未强行统一。\n\n",
    },
  },
  {
    type: "artifact_delta",
    data: {
      artifact_id: "a1",
      kind: "report",
      delta: "## 待核实事项\n\n1. 利润表主营收入/其他收益拆分：**无法验证**（iFinD 利润表接口降级，登录态失效）。恢复数据源后需重新拉取，确认政府补助等非经常性损益占比。\n2. 2026-07-15「关于获得政府补助的公告」（[PDF](https://example.com/ann/subsidy.pdf)）金额未读，可能影响命题结论。\n3. 毛利率两源差异需以定期报告为准复核。\n\n",
    },
  },
  {
    type: "artifact_delta",
    data: {
      artifact_id: "a1",
      kind: "report",
      delta: "## 失效条件\n\n- 若 2026 三季报显示净利率环比显著回落或政府补助占净利润比例 >20%，则「盈利改善来自主营业务」命题失效。\n- 若毛利率跌破 50%（连续两期），主营竞争力假设需重估。\n\n---\n*仅做事实研究，不构成投资建议。*",
    },
  },
  {
    type: "artifact_done",
    data: {
      artifact_id: "a1",
      kind: "report",
      title: "命题验证：寒武纪盈利改善是否来自主营业务",
      markdown: "", // 前端以流式累计内容为准
    },
  },
  { type: "step_done", data: { step_id: "s5", status: "ok" } },
  {
    type: "memory_write",
    data: {
      key: "stock:688256.SH:last_conclusion",
      summary: "寒武纪 2026H1 盈利改善显著（净利率 23.9%，同比 +412.5%），主营驱动判断部分成立，利润表拆分待数据源恢复后核实。",
    },
  },
  {
    type: "cost",
    data: { tokens_in: 8100, tokens_out: 3050, llm_calls: 7, tool_calls: 4, elapsed_ms: 35400, budget_remaining: 188850 },
  },
  {
    type: "done",
    data: { status: "done", summary: "命题部分成立：盈利改善显著且毛利率高位支撑主营驱动；利润表降级项已列入待核实。" },
  },
];

// mock 模式下的线程列表 / 能力页数据
export const mockThreads = [
  {
    thread_id: MOCK_THREAD_ID,
    goal: MOCK_GOAL,
    skill: "thesis_check" as const,
    status: "awaiting_approval" as const,
    created_at: "2026-09-23T09:44:00",
    updated_at: "2026-09-23T09:45:00",
  },
];

export const mockCapabilities = {
  tools: [
    {
      name: "fuyao_quote_snapshot",
      display_name: "行情快照（扶摇）",
      description: "A 股实时行情快照：收盘价、涨跌幅、换手率、总市值。",
      source: "fuyao" as const,
      params_schema: { symbol: { type: "string", desc: "证券代码，如 688256.SH" } },
      returns: ["data", "source", "as_of", "unit", "caliber"],
    },
    {
      name: "fuyao_valuation",
      display_name: "估值（扶摇）",
      description: "PE/PB/PS 等估值指标，含 TTM 口径。",
      source: "fuyao" as const,
      params_schema: { symbol: { type: "string" } },
      returns: ["data", "source", "as_of", "unit", "caliber"],
    },
    {
      name: "ifind_fin_indicator",
      display_name: "财务指标（iFinD）",
      description: "毛利率、净利率、研发费用率等关键财务指标。",
      source: "ifind" as const,
      params_schema: { symbol: { type: "string" }, fields: { type: "string[]" }, period: { type: "string" } },
      returns: ["data", "source", "as_of", "unit", "caliber"],
    },
    {
      name: "ifind_fin_statement",
      display_name: "三大报表（iFinD）",
      description: "资产负债表 / 利润表 / 现金流量表原始科目。",
      source: "ifind" as const,
      params_schema: { symbol: { type: "string" }, statement: { type: "string" }, period: { type: "string" } },
      returns: ["data", "source", "as_of", "unit", "caliber"],
    },
    {
      name: "ifind_announcement",
      display_name: "公告检索（iFinD）",
      description: "公告列表 + PDF 链接，为待核实事项提供原始材料线索。",
      source: "ifind" as const,
      params_schema: { symbol: { type: "string" }, limit: { type: "number" } },
      returns: ["data", "source", "as_of", "unit", "caliber"],
    },
  ],
};
