// REST + POST SSE 客户端，严格按 API_CONTRACT.md
import type { PlanStep, Skill, SseEvent, ThreadMeta, ThreadState, ToolInfo } from "./types";

// ---- 匿名访客标识：首次访问生成 UUID 存 localStorage，所有 API 调用带 X-Visitor-Id ----
const VISITOR_KEY = "ab_visitor_id";

export function getVisitorId(): string {
  if (typeof window === "undefined") return "anon";
  let id = window.localStorage.getItem(VISITOR_KEY);
  if (!id) {
    id = window.crypto.randomUUID();
    window.localStorage.setItem(VISITOR_KEY, id);
  }
  return id;
}

export function resetVisitorId(): string {
  const id = window.crypto.randomUUID();
  window.localStorage.setItem(VISITOR_KEY, id);
  return id;
}

function withVisitor(headers?: HeadersInit): HeadersInit {
  return { "X-Visitor-Id": getVisitorId(), ...(headers ?? {}) };
}

async function jsonFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, { ...init, headers: withVisitor(init?.headers) });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${init?.method ?? "GET"} ${url} → ${res.status} ${text}`);
  }
  return (await res.json()) as T;
}

export const api = {
  listThreads: () => jsonFetch<{ threads: ThreadMeta[] }>("/api/threads"),

  createThread: (goal: string, skill: Skill | null) =>
    jsonFetch<{ thread_id: string }>("/api/threads", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ goal, skill }),
    }),

  getState: (threadId: string) =>
    jsonFetch<ThreadState>(`/api/threads/${threadId}/state`),

  approve: (threadId: string, action: "approve" | "edit", plan?: PlanStep[]) =>
    jsonFetch<{ ok: true }>(`/api/threads/${threadId}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(action === "edit" ? { action, plan } : { action }),
    }),

  capabilities: () => jsonFetch<{ tools: ToolInfo[] }>("/api/capabilities"),
};

// POST /run 是 SSE：EventSource 不支持 POST，用 fetch + ReadableStream 手工解析
export async function streamRun(
  threadId: string,
  resumeToken: string | null,
  onEvent: (ev: SseEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  const res = await fetch(`/api/threads/${threadId}/run`, {
    method: "POST",
    headers: withVisitor({ "Content-Type": "application/json" }),
    body: JSON.stringify({ resume_token: resumeToken }),
    signal,
  });
  if (!res.ok || !res.body) {
    const text = await res.text().catch(() => "");
    throw new Error(`POST /run → ${res.status} ${text}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE 帧以空行分隔
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      let type = "message";
      const dataLines: string[] = [];
      for (const line of frame.split("\n")) {
        if (line.startsWith("event:")) type = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
      }
      if (dataLines.length === 0) continue;
      try {
        const data = JSON.parse(dataLines.join("\n"));
        onEvent({ type, data } as SseEvent);
      } catch {
        // 忽略无法解析的帧（心跳等）
      }
    }
  }
}
