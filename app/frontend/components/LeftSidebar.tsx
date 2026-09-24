"use client";

import { useEffect, useState } from "react";
import { getVisitorId, resetVisitorId } from "@/lib/api";
import type { Skill, ThreadMeta, ThreadStatus, ToolInfo } from "@/lib/types";

export const SKILL_CARDS: { value: Skill; label: string; desc: string }[] = [
  { value: "thesis_check", label: "命题验证", desc: "验证一句投资说法" },
  { value: "earnings_review", label: "业绩点评", desc: "最新财报四段点评" },
  { value: "watchlist_brief", label: "持仓早报", desc: "自选标的例行扫描" },
];

export const STATUS_LABEL: Record<ThreadStatus, { text: string; cls: string }> = {
  planning: { text: "进行中", cls: "bg-blue-50 text-blue-600" },
  running: { text: "进行中", cls: "bg-blue-50 text-blue-600" },
  awaiting_approval: { text: "待审批", cls: "bg-amber-50 text-amber-600" },
  interrupted: { text: "待审批", cls: "bg-amber-50 text-amber-600" },
  done: { text: "完成", cls: "bg-green-50 text-green-600" },
  failed: { text: "失败", cls: "bg-red-50 text-red-600" },
};

const ACTIVE_STATUSES: ThreadStatus[] = [
  "planning",
  "running",
  "awaiting_approval",
  "interrupted",
];

export function StatusBadge({ status }: { status: ThreadStatus }) {
  const s = STATUS_LABEL[status] ?? { text: status, cls: "bg-neutral-100 text-neutral-500" };
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${s.cls}`}>{s.text}</span>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-xs font-medium text-neutral-400 px-3 pt-4 pb-1.5">
      {children}
    </h2>
  );
}

interface Props {
  threads: ThreadMeta[];
  activeThreadId: string | null;
  onSelectThread: (id: string) => void;
  onNewResearch: () => void;
  onPickSkill: (skill: Skill) => void;
  loadCapabilities: () => Promise<ToolInfo[]>;
}

export default function LeftSidebar({
  threads,
  activeThreadId,
  onSelectThread,
  onNewResearch,
  onPickSkill,
  loadCapabilities,
}: Props) {
  const [capOpen, setCapOpen] = useState(false);
  const [tools, setTools] = useState<ToolInfo[] | null>(null);
  const [capError, setCapError] = useState<string | null>(null);
  const [expandedTool, setExpandedTool] = useState<string | null>(null);
  const [visitorId, setVisitorId] = useState<string | null>(null);

  // 客户端挂载后再读 localStorage，避免 hydration 不一致
  useEffect(() => {
    setVisitorId(getVisitorId());
  }, []);

  const onResetVisitor = () => {
    if (window.confirm("重置为新访客？旧空间的内容在新空间不可见（仍保留在原访客空间下）。")) {
      resetVisitorId();
      window.location.reload();
    }
  };

  useEffect(() => {
    if (!capOpen || tools !== null) return;
    loadCapabilities()
      .then(setTools)
      .catch((e) => setCapError(String(e)));
  }, [capOpen, tools, loadCapabilities]);

  const runningCount = threads.filter((t) => ACTIVE_STATUSES.includes(t.status)).length;

  return (
    <aside className="w-60 shrink-0 bg-neutral-50 border-r border-neutral-100 flex flex-col min-h-0">
      {/* 产品名 */}
      <div className="px-4 pt-4 pb-3">
        <h1 className="text-base font-bold tracking-wide text-neutral-900">AlphaBuddy</h1>
        <p className="text-[11px] text-neutral-400 mt-0.5">Every thesis deserves verifiable evidence.</p>
      </div>

      <div className="px-3">
        <button
          className="w-full flex items-center gap-2 px-3 py-2 text-sm text-neutral-700 bg-white border border-neutral-200 rounded-xl hover:border-blue-300 hover:text-blue-600 transition-colors"
          onClick={onNewResearch}
        >
          <span className="text-base leading-none">＋</span> 新建研究
        </button>
      </div>

      <div className="flex-1 overflow-y-auto min-h-0 pb-2">
        {/* 研究线程 */}
        <SectionTitle>研究线程</SectionTitle>
        {threads.length === 0 && (
          <p className="text-xs text-neutral-300 px-3 py-1">暂无线程</p>
        )}
        <ul className="px-2 space-y-0.5">
          {threads.map((t) => (
            <li key={t.thread_id}>
              <button
                className={`w-full text-left px-2.5 py-2 rounded-lg hover:bg-white transition-colors ${
                  t.thread_id === activeThreadId
                    ? "bg-white shadow-sm border border-neutral-100"
                    : ""
                }`}
                onClick={() => onSelectThread(t.thread_id)}
              >
                <div className="text-[13px] leading-snug line-clamp-1 text-neutral-700">
                  {t.goal}
                </div>
                <div className="flex items-center gap-1.5 mt-1">
                  <StatusBadge status={t.status} />
                  <span className="text-[10px] text-neutral-300">
                    {t.updated_at.slice(5, 16).replace("T", " ")}
                  </span>
                </div>
              </button>
            </li>
          ))}
        </ul>

        {/* 技能卡 */}
        <SectionTitle>技能卡</SectionTitle>
        <ul className="px-2 space-y-0.5">
          {SKILL_CARDS.map((s) => (
            <li key={s.value}>
              <button
                className="w-full text-left px-2.5 py-2 rounded-lg hover:bg-white transition-colors"
                onClick={() => onPickSkill(s.value)}
                title="点击预填输入框"
              >
                <div className="text-[13px] text-neutral-700">{s.label}</div>
                <div className="text-[11px] text-neutral-400">{s.desc}</div>
              </button>
            </li>
          ))}
        </ul>

        {/* 能力（工具注册表） */}
        <SectionTitle>能力</SectionTitle>
        <div className="px-2">
          <button
            className="w-full flex items-center justify-between px-2.5 py-2 rounded-lg hover:bg-white text-[13px] text-neutral-700 transition-colors"
            onClick={() => setCapOpen((v) => !v)}
          >
            <span>工具注册表</span>
            <span className="text-neutral-300 text-xs">{capOpen ? "▾" : "▸"}</span>
          </button>
          {capOpen && (
            <div className="mt-1 space-y-1.5 pb-2">
              {capError && <p className="text-xs text-red-500 px-1">加载失败：{capError}</p>}
              {!tools && !capError && <p className="text-xs text-neutral-300 px-1">加载中…</p>}
              {tools?.map((tool) => (
                <div
                  key={tool.name}
                  className="bg-white border border-neutral-100 rounded-lg text-xs"
                >
                  <button
                    className="w-full text-left px-2.5 py-2"
                    onClick={() =>
                      setExpandedTool(expandedTool === tool.name ? null : tool.name)
                    }
                  >
                    <div className="font-medium text-neutral-700">{tool.display_name}</div>
                    <div className="text-neutral-300 font-mono text-[10px]">
                      {tool.name} · {tool.source}
                    </div>
                  </button>
                  {expandedTool === tool.name && (
                    <div className="px-2.5 pb-2.5 border-t border-neutral-50">
                      <p className="text-neutral-500 my-1.5">{tool.description}</p>
                      <pre className="bg-neutral-50 rounded-lg p-2 overflow-x-auto text-[10px] text-neutral-500">
                        {JSON.stringify(tool.params_schema, null, 2)}
                      </pre>
                      <p className="text-neutral-400 mt-1.5">
                        返回：{tool.returns.join(" / ")}
                      </p>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 研究更新 */}
        <SectionTitle>研究更新</SectionTitle>
        <div className="px-3 pb-3 space-y-1.5">
          <div className="flex items-start gap-1.5 text-xs">
            <span
              className={`mt-1.5 w-1.5 h-1.5 rounded-full shrink-0 ${
                runningCount > 0 ? "bg-blue-500" : "bg-neutral-300"
              }`}
            />
            <div>
              <div className="text-neutral-700">{runningCount} 个任务运行中</div>
              <div className="text-neutral-300 text-[11px]">含进行中与待审批线程</div>
            </div>
          </div>
        </div>
      </div>

      {/* 我的空间（匿名访客标识） */}
      <div className="border-t border-neutral-100 px-3 py-2.5 flex items-center justify-between shrink-0">
        <span className="text-[10px] text-neutral-400">
          我的空间 · {visitorId ? visitorId.slice(0, 6) : "…"}
        </span>
        <button
          className="text-[10px] text-neutral-400 hover:text-red-500 transition-colors"
          onClick={onResetVisitor}
          title="生成新的访客标识并刷新；旧空间内容在新空间不可见"
        >
          重置为新访客
        </button>
      </div>
    </aside>
  );
}
