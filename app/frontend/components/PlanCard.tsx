"use client";

import { useEffect, useState } from "react";
import type { PlanStep } from "@/lib/types";

function StepIcon({ status }: { status: PlanStep["status"] }) {
  switch (status) {
    case "done":
      return <span className="text-green-600">●</span>;
    case "failed":
      return <span className="text-red-600">●</span>;
    case "skipped":
      return <span className="text-neutral-400">●</span>;
    case "running":
      return <span className="text-blue-600 animate-pulse">●</span>;
    default:
      return <span className="text-neutral-300">○</span>;
  }
}

interface Props {
  plan: PlanStep[];
  awaitingApproval: boolean;
  approving: boolean;
  onApprove: (action: "approve" | "edit", plan?: PlanStep[]) => void;
}

export default function PlanCard({ plan, awaitingApproval, approving, onApprove }: Props) {
  const [edited, setEdited] = useState<PlanStep[] | null>(null);

  // 审批结束后丢弃本地编辑副本，回到以 props（事件驱动状态）为准
  useEffect(() => {
    if (!awaitingApproval) setEdited(null);
  }, [awaitingApproval]);

  const steps = edited ?? plan;
  const dirty = edited !== null;

  if (plan.length === 0) return null;

  const updateTitle = (id: string, title: string) => {
    setEdited((prev) =>
      (prev ?? plan).map((s) => (s.id === id ? { ...s, title } : s))
    );
  };
  const removeStep = (id: string) => {
    setEdited((prev) => (prev ?? plan).filter((s) => s.id !== id));
  };

  return (
    <div
      className={`border rounded-lg bg-white ${
        awaitingApproval ? "border-amber-400 ring-1 ring-amber-200" : "border-neutral-200"
      }`}
    >
      <div className="flex items-center justify-between px-3 py-2 border-b border-neutral-100">
        <h3 className="text-sm font-semibold">
          研究计划
          {awaitingApproval && (
            <span className="ml-2 text-xs text-amber-600 font-normal">
              等待人工审批（interrupt）
            </span>
          )}
        </h3>
        <span className="text-xs text-neutral-400">{steps.length} 步</span>
      </div>

      <ol className="px-3 py-2 space-y-1.5">
        {steps.map((s, i) => (
          <li key={s.id} className="flex items-center gap-2 text-sm">
            <StepIcon status={s.status} />
            <span className="text-neutral-400 text-xs w-5">{i + 1}.</span>
            {awaitingApproval ? (
              <input
                className="flex-1 border border-neutral-200 rounded px-1.5 py-0.5 text-sm focus:outline-none focus:ring-1 focus:ring-amber-400"
                value={s.title}
                onChange={(e) => updateTitle(s.id, e.target.value)}
              />
            ) : (
              <span
                className={
                  s.status === "failed"
                    ? "text-red-700"
                    : s.status === "done"
                      ? "text-neutral-700"
                      : "text-neutral-600"
                }
              >
                {s.title}
              </span>
            )}
            {s.tool && (
              <span className="text-[10px] font-mono text-neutral-400 bg-neutral-50 border border-neutral-200 rounded px-1">
                {s.tool}
              </span>
            )}
            {awaitingApproval && (
              <button
                className="text-xs text-red-500 hover:text-red-700 px-1"
                title="删除此步骤"
                onClick={() => removeStep(s.id)}
              >
                ✕
              </button>
            )}
          </li>
        ))}
      </ol>

      {awaitingApproval && (
        <div className="flex items-center gap-2 px-3 py-2 border-t border-amber-100 bg-amber-50 rounded-b-lg">
          <button
            className="px-3 py-1.5 text-sm bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50"
            disabled={approving}
            onClick={() => onApprove("approve")}
          >
            批准
          </button>
          <button
            className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
            disabled={approving || !dirty || steps.length === 0}
            title={dirty ? "以编辑后的计划继续执行" : "先编辑（删步/改标题）再批准"}
            onClick={() => onApprove("edit", steps)}
          >
            编辑后批准
          </button>
          {approving && <span className="text-xs text-neutral-500">提交中…</span>}
          {dirty && <span className="text-xs text-amber-600">计划已修改（未提交）</span>}
        </div>
      )}
    </div>
  );
}
