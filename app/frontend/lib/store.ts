// 事件流 → UI 状态。同一份 reducer 用于：实时 SSE、刷新后从 events 重放、mock 回放。
import type {
  Cost,
  PlanStep,
  SseEvent,
  ThreadStatus,
  ToolCallStatus,
  ToolEnvelope,
} from "./types";

export interface ToolCallItem {
  kind: "tool_call";
  key: string;
  stepId: string;
  callId: string;
  tool: string;
  params: Record<string, unknown>;
  status: ToolCallStatus | "running";
  envelope: ToolEnvelope | null;
}

export interface MarkerItem {
  kind: "marker";
  key: string;
  marker:
    | { type: "compress"; beforeChars: number; afterChars: number }
    | { type: "memory_write"; memKey: string; summary: string }
    | {
        type: "conflict";
        field: string;
        sources: { source: string; value: unknown; as_of: string | null }[];
      }
    | { type: "warning"; warningKind: "degraded" | "guard"; message: string }
    | { type: "stopped"; reason: string }
    | { type: "done"; status: "done" | "failed"; summary: string };
}

export type TimelineItem = ToolCallItem | MarkerItem;

export interface WorkbenchState {
  status: ThreadStatus | "idle";
  plan: PlanStep[];
  awaitingApproval: boolean;
  timeline: TimelineItem[];
  artifactTitle: string | null;
  artifactMarkdown: string;
  artifactDone: boolean;
  cost: Cost | null;
}

export const emptyCost: Cost = {
  tokens_in: 0,
  tokens_out: 0,
  llm_calls: 0,
  tool_calls: 0,
  elapsed_ms: 0,
  budget_remaining: 0,
};

export function initialState(): WorkbenchState {
  return {
    status: "idle",
    plan: [],
    awaitingApproval: false,
    timeline: [],
    artifactTitle: null,
    artifactMarkdown: "",
    artifactDone: false,
    cost: null,
  };
}

let seq = 0;
function nextKey(prefix: string) {
  seq += 1;
  return `${prefix}-${seq}`;
}

function setStepStatus(
  plan: PlanStep[],
  stepId: string,
  status: PlanStep["status"]
): PlanStep[] {
  return plan.map((s) => (s.id === stepId ? { ...s, status } : s));
}

export function applyEvent(state: WorkbenchState, ev: SseEvent): WorkbenchState {
  switch (ev.type) {
    case "run_started":
      return { ...state, status: "running" };

    case "plan":
      return {
        ...state,
        plan: ev.data.steps.map((s) => ({ ...s, status: s.status ?? "pending" })),
      };

    case "interrupt":
      if (ev.data.kind === "plan_approval") {
        return {
          ...state,
          status: "awaiting_approval",
          awaitingApproval: true,
          plan: ev.data.plan.map((s) => ({ ...s, status: s.status ?? "pending" })),
        };
      }
      return { ...state, status: "interrupted" };

    case "step_start":
      return {
        ...state,
        awaitingApproval: false,
        status: "running",
        plan: setStepStatus(state.plan, ev.data.step_id, "running"),
      };

    case "tool_call_start": {
      const item: ToolCallItem = {
        kind: "tool_call",
        key: `tc-${ev.data.call_id}`,
        stepId: ev.data.step_id,
        callId: ev.data.call_id,
        tool: ev.data.tool,
        params: ev.data.params,
        status: "running",
        envelope: null,
      };
      return { ...state, timeline: [...state.timeline, item] };
    }

    case "tool_call_result": {
      const key = `tc-${ev.data.call_id}`;
      const timeline = state.timeline.map((it) =>
        it.kind === "tool_call" && it.key === key
          ? { ...it, status: ev.data.status, envelope: ev.data.envelope }
          : it
      );
      return { ...state, timeline };
    }

    case "conflict":
      return {
        ...state,
        timeline: [
          ...state.timeline,
          {
            kind: "marker",
            key: nextKey("conflict"),
            marker: {
              type: "conflict",
              field: ev.data.field,
              sources: ev.data.sources,
            },
          },
        ],
      };

    case "compress":
      return {
        ...state,
        timeline: [
          ...state.timeline,
          {
            kind: "marker",
            key: nextKey("compress"),
            marker: {
              type: "compress",
              beforeChars: ev.data.before_chars,
              afterChars: ev.data.after_chars,
            },
          },
        ],
      };

    case "memory_write":
      return {
        ...state,
        timeline: [
          ...state.timeline,
          {
            kind: "marker",
            key: nextKey("mem"),
            marker: {
              type: "memory_write",
              memKey: ev.data.key,
              summary: ev.data.summary,
            },
          },
        ],
      };

    case "step_done": {
      const mapped =
        ev.data.status === "ok"
          ? "done"
          : ev.data.status === "failed"
            ? "failed"
            : "skipped";
      return { ...state, plan: setStepStatus(state.plan, ev.data.step_id, mapped) };
    }

    case "artifact_delta":
      return {
        ...state,
        artifactMarkdown: state.artifactMarkdown + ev.data.delta,
      };

    case "artifact_done":
      return {
        ...state,
        artifactTitle: ev.data.title,
        artifactMarkdown: ev.data.markdown || state.artifactMarkdown,
        artifactDone: true,
      };

    case "cost":
      return { ...state, cost: ev.data };

    case "warning":
      return {
        ...state,
        timeline: [
          ...state.timeline,
          {
            kind: "marker",
            key: nextKey("warn"),
            marker: {
              type: "warning",
              warningKind: ev.data.kind,
              message: ev.data.message,
            },
          },
        ],
      };

    case "stopped":
      return {
        ...state,
        status: "failed",
        timeline: [
          ...state.timeline,
          {
            kind: "marker",
            key: nextKey("stopped"),
            marker: { type: "stopped", reason: ev.data.reason },
          },
        ],
      };

    case "done":
      return {
        ...state,
        status: ev.data.status,
        awaitingApproval: false,
        timeline: [
          ...state.timeline,
          {
            kind: "marker",
            key: nextKey("done"),
            marker: {
              type: "done",
              status: ev.data.status,
              summary: ev.data.summary,
            },
          },
        ],
      };

    default:
      return state;
  }
}

// 刷新恢复：重放事件得到派生态，再用快照里的权威字段（plan/status/cost/artifacts）覆盖
export function applySnapshot(
  state: WorkbenchState,
  snap: {
    status: ThreadStatus;
    plan: PlanStep[];
    artifacts: { title: string; markdown: string }[];
    cost: Cost;
  }
): WorkbenchState {
  const artifact = snap.artifacts[0];
  return {
    ...state,
    status: snap.status,
    plan: snap.plan.map((s) => ({ ...s, status: s.status ?? "pending" })),
    awaitingApproval: snap.status === "awaiting_approval",
    artifactTitle: artifact ? artifact.title : state.artifactTitle,
    artifactMarkdown: artifact ? artifact.markdown : state.artifactMarkdown,
    artifactDone: !!artifact,
    cost: snap.cost,
  };
}
