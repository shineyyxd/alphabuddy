// 类型定义，与 app/docs/API_CONTRACT.md 严格对齐

export type Skill = "thesis_check" | "earnings_review" | "watchlist_brief";

export type ThreadStatus =
  | "planning"
  | "awaiting_approval"
  | "running"
  | "interrupted"
  | "done"
  | "failed";

export interface ThreadMeta {
  thread_id: string;
  goal: string;
  skill: Skill | null;
  status: ThreadStatus;
  created_at: string;
  updated_at: string;
}

export interface PlanStep {
  id: string;
  title: string;
  tool: string | null;
  status?: "pending" | "running" | "done" | "failed" | "skipped";
}

// 工具统一返回信封（契约 §3）
export interface ToolEnvelope {
  data: Record<string, unknown> | null;
  source: string;
  as_of: string | null;
  unit: string | null;
  caliber: string | null;
  fetched_at?: string;
  auth?: "ok" | "missing_key" | "fixture";
  error: { kind: string; message: string } | null;
}

export type ToolCallStatus = "ok" | "empty" | "error" | "degraded";

export interface Cost {
  tokens_in: number;
  tokens_out: number;
  llm_calls: number;
  tool_calls: number;
  elapsed_ms: number;
  budget_remaining: number;
}

export interface Artifact {
  id: string;
  kind: "report";
  title: string;
  markdown: string;
}

export interface ToolInfo {
  name: string;
  display_name: string;
  description: string;
  source: "fuyao" | "ifind";
  params_schema: Record<string, unknown>;
  returns: string[];
}

export interface ThreadState {
  thread_id: string;
  goal: string;
  skill: Skill | null;
  status: ThreadStatus;
  plan: PlanStep[];
  events: SseEvent[];
  artifacts: Artifact[];
  cost: Cost;
}

// ---- SSE 事件（契约 §2） ----

export interface SseEventBase {
  type: string;
  data: Record<string, unknown>;
}

export interface ConflictSource {
  source: string;
  value: unknown;
  as_of: string | null;
}

export type SseEvent =
  | { type: "run_started"; data: { thread_id: string; skill: Skill | null } }
  | { type: "plan"; data: { steps: PlanStep[] } }
  | { type: "interrupt"; data: { kind: "plan_approval"; plan: PlanStep[] } }
  | { type: "step_start"; data: { step_id: string; title: string } }
  | {
      type: "tool_call_start";
      data: { step_id: string; call_id: string; tool: string; params: Record<string, unknown> };
    }
  | {
      type: "tool_call_result";
      data: {
        step_id: string;
        call_id: string;
        tool: string;
        status: ToolCallStatus;
        envelope: ToolEnvelope;
      };
    }
  | {
      type: "conflict";
      data: { step_id: string; field: string; sources: ConflictSource[] };
    }
  | { type: "compress"; data: { before_chars: number; after_chars: number } }
  | { type: "memory_write"; data: { key: string; summary: string } }
  | { type: "step_done"; data: { step_id: string; status: "ok" | "failed" | "skipped" } }
  | { type: "artifact_delta"; data: { artifact_id: string; kind: "report"; delta: string } }
  | {
      type: "artifact_done";
      data: { artifact_id: string; kind: "report"; title: string; markdown: string };
    }
  | { type: "cost"; data: Cost }
  | { type: "warning"; data: { kind: "degraded" | "guard"; message: string } }
  | { type: "stopped"; data: { reason: "step_limit" | "token_budget" | "timeout" } }
  | { type: "done"; data: { status: "done" | "failed"; summary: string } };
