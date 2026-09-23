"use client";

import { useEffect, useState } from "react";
import type { Skill, ThreadMeta, ThreadStatus, ToolInfo } from "@/lib/types";

const SKILL_OPTIONS: { value: Skill | ""; label: string }[] = [
  { value: "thesis_check", label: "命题验证" },
  { value: "earnings_review", label: "业绩点评" },
  { value: "watchlist_brief", label: "持仓早报" },
  { value: "", label: "自动（意图识别）" },
];

export const STATUS_LABEL: Record<ThreadStatus, { text: string; cls: string }> = {
  planning: { text: "规划中", cls: "bg-blue-100 text-blue-700" },
  awaiting_approval: { text: "待审批", cls: "bg-amber-100 text-amber-700" },
  running: { text: "执行中", cls: "bg-blue-100 text-blue-700" },
  interrupted: { text: "已中断", cls: "bg-amber-100 text-amber-700" },
  done: { text: "完成", cls: "bg-green-100 text-green-700" },
  failed: { text: "失败", cls: "bg-red-100 text-red-700" },
};

export function StatusBadge({ status }: { status: ThreadStatus }) {
  const s = STATUS_LABEL[status] ?? { text: status, cls: "bg-neutral-100 text-neutral-600" };
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded ${s.cls}`}>{s.text}</span>
  );
}

interface Props {
  threads: ThreadMeta[];
  activeThreadId: string | null;
  onSelectThread: (id: string) => void;
  onCreateThread: (goal: string, skill: Skill | null) => void;
  creating: boolean;
  loadCapabilities: () => Promise<ToolInfo[]>;
}

export default function LeftSidebar({
  threads,
  activeThreadId,
  onSelectThread,
  onCreateThread,
  creating,
  loadCapabilities,
}: Props) {
  const [goal, setGoal] = useState("");
  const [skill, setSkill] = useState<Skill | "">("thesis_check");
  const [capOpen, setCapOpen] = useState(false);
  const [tools, setTools] = useState<ToolInfo[] | null>(null);
  const [capError, setCapError] = useState<string | null>(null);
  const [expandedTool, setExpandedTool] = useState<string | null>(null);

  useEffect(() => {
    if (!capOpen || tools !== null) return;
    loadCapabilities()
      .then(setTools)
      .catch((e) => setCapError(String(e)));
  }, [capOpen, tools, loadCapabilities]);

  const submit = () => {
    const g = goal.trim();
    if (!g || creating) return;
    onCreateThread(g, skill === "" ? null : skill);
    setGoal("");
  };

  return (
    <aside className="w-64 shrink-0 bg-white border-r border-neutral-200 flex flex-col min-h-0">
      {/* 新建研究目标 */}
      <div className="p-3 border-b border-neutral-200">
        <h2 className="text-xs font-semibold text-neutral-500 mb-2">新建研究目标</h2>
        <textarea
          className="w-full text-sm border border-neutral-300 rounded p-2 resize-none focus:outline-none focus:ring-1 focus:ring-blue-500"
          rows={3}
          placeholder="例：验证「寒武纪盈利改善来自主营业务」"
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
        />
        <div className="flex gap-2 mt-2">
          <select
            className="flex-1 text-sm border border-neutral-300 rounded px-2 py-1.5 bg-white"
            value={skill}
            onChange={(e) => setSkill(e.target.value as Skill | "")}
          >
            {SKILL_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <button
            className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
            disabled={!goal.trim() || creating}
            onClick={submit}
          >
            {creating ? "创建中…" : "开始研究"}
          </button>
        </div>
      </div>

      {/* 线程列表 */}
      <div className="flex-1 overflow-y-auto min-h-0">
        <h2 className="text-xs font-semibold text-neutral-500 px-3 pt-3 pb-1">
          研究线程
        </h2>
        {threads.length === 0 && (
          <p className="text-xs text-neutral-400 px-3 py-2">暂无线程</p>
        )}
        <ul>
          {threads.map((t) => (
            <li key={t.thread_id}>
              <button
                className={`w-full text-left px-3 py-2 border-b border-neutral-100 hover:bg-neutral-50 ${
                  t.thread_id === activeThreadId ? "bg-blue-50 border-l-2 border-l-blue-600" : ""
                }`}
                onClick={() => onSelectThread(t.thread_id)}
              >
                <div className="text-sm leading-snug line-clamp-2">{t.goal}</div>
                <div className="flex items-center gap-2 mt-1">
                  <StatusBadge status={t.status} />
                  <span className="text-[10px] text-neutral-400">
                    {t.skill ?? "auto"} · {t.updated_at.slice(0, 16).replace("T", " ")}
                  </span>
                </div>
              </button>
            </li>
          ))}
        </ul>
      </div>

      {/* 能力折叠面板 */}
      <div className="border-t border-neutral-200">
        <button
          className="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold text-neutral-600 hover:bg-neutral-50"
          onClick={() => setCapOpen((v) => !v)}
        >
          <span>能力（工具注册表）</span>
          <span>{capOpen ? "▾" : "▸"}</span>
        </button>
        {capOpen && (
          <div className="max-h-64 overflow-y-auto px-3 pb-3 space-y-2">
            {capError && (
              <p className="text-xs text-red-600">加载失败：{capError}</p>
            )}
            {!tools && !capError && (
              <p className="text-xs text-neutral-400">加载中…</p>
            )}
            {tools?.map((tool) => (
              <div key={tool.name} className="border border-neutral-200 rounded text-xs">
                <button
                  className="w-full text-left px-2 py-1.5 hover:bg-neutral-50"
                  onClick={() =>
                    setExpandedTool(expandedTool === tool.name ? null : tool.name)
                  }
                >
                  <div className="font-medium">{tool.display_name}</div>
                  <div className="text-neutral-400 font-mono text-[10px]">
                    {tool.name} · {tool.source}
                  </div>
                </button>
                {expandedTool === tool.name && (
                  <div className="px-2 pb-2 border-t border-neutral-100">
                    <p className="text-neutral-600 my-1">{tool.description}</p>
                    <p className="text-neutral-400 mb-1">入参 schema：</p>
                    <pre className="bg-neutral-50 rounded p-1.5 overflow-x-auto text-[10px]">
                      {JSON.stringify(tool.params_schema, null, 2)}
                    </pre>
                    <p className="text-neutral-400 mt-1">
                      返回：{tool.returns.join(" / ")}
                    </p>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}
