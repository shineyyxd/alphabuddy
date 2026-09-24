"use client";

import { useEffect, useState } from "react";
import type { PlanStep } from "@/lib/types";

function StepIcon({ status }: { status: PlanStep["status"] }) {
  switch (status) {
    case "done":
      return <span className="w-4 h-4 rounded-full bg-green-500 text-white text-[10px] flex items-center justify-center">✓</span>;
    case "failed":
      return <span className="w-4 h-4 rounded-full bg-red-500 text-white text-[10px] flex items-center justify-center">✕</span>;
    case "skipped":
      return <span className="w-4 h-4 rounded-full bg-neutral-200 text-neutral-400 text-[10px] flex items-center justify-center">–</span>;
    case "running":
      return <span className="w-4 h-4 rounded-full border-2 border-blue-500 border-t-transparent animate-spin" />;
    default:
      return <span className="w-4 h-4 rounded-full border border-neutral-200 bg-white" />;
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
      className={`rounded-2xl bg-white shadow-sm border ${
        awaitingApproval ? "border-amber-200 ring-2 ring-amber-50" : "border-neutral-100"
      }`}
    >
      <div className="flex items-center justify-between px-4 py-3">
        <h3 className="text-sm font-semibold text-neutral-800">
          主研的研究计划
          {awaitingApproval && (
            <span className="ml-2 text-xs text-amber-600 font-normal">
              等你确认（interrupt）
            </span>
          )}
        </h3>
        <span className="text-xs text-neutral-300">{steps.length} 步</span>
      </div>

      <ol className="px-4 pb-3 space-y-2">
        {steps.map((s, i) => (
          <li key={s.id} className="flex items-center gap-2.5 text-sm">
            <StepIcon status={s.status} />
            <span className="text-neutral-300 text-xs w-4">{i + 1}.</span>
            {awaitingApproval ? (
              <input
                className="flex-1 border border-neutral-200 rounded-lg px-2 py-1 text-[13px] focus:outline-none focus:border-amber-300"
                value={s.title}
                onChange={(e) => updateTitle(s.id, e.target.value)}
              />
            ) : (
              <span
                className={
                  s.status === "failed"
                    ? "text-red-600"
                    : s.status === "done"
                      ? "text-neutral-600"
                      : "text-neutral-500"
                }
              >
                {s.title}
              </span>
            )}
            {s.tool && (
              <span className="text-[10px] font-mono text-neutral-400 bg-neutral-50 rounded-full px-2 py-0.5">
                {s.tool}
              </span>
            )}
            {awaitingApproval && (
              <button
                className="text-xs text-neutral-300 hover:text-red-500 px-1 transition-colors"
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
        <div className="flex items-center gap-2 px-4 py-3 border-t border-amber-100 bg-amber-50/60 rounded-b-2xl">
          <button
            className="px-4 py-1.5 text-[13px] bg-green-600 text-white rounded-full hover:bg-green-700 disabled:opacity-50 transition-colors"
            disabled={approving}
            onClick={() => onApprove("approve")}
          >
            批准
          </button>
          <button
            className="px-4 py-1.5 text-[13px] bg-blue-600 text-white rounded-full hover:bg-blue-700 disabled:opacity-50 transition-colors"
            disabled={approving || !dirty || steps.length === 0}
            title={dirty ? "以编辑后的计划继续执行" : "先编辑（删步/改标题）再批准"}
            onClick={() => onApprove("edit", steps)}
          >
            编辑后批准
          </button>
          {approving && <span className="text-xs text-neutral-400">提交中…</span>}
          {dirty && <span className="text-xs text-amber-600">计划已修改（未提交）</span>}
        </div>
      )}
    </div>
  );
}
