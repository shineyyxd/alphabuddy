"use client";

import { useEffect, useRef } from "react";
import type { PlanStep } from "@/lib/types";
import type { TimelineItem } from "@/lib/store";
import PlanCard from "./PlanCard";
import ToolCallCard from "./ToolCallCard";
import MarkerRow from "./MarkerRow";

interface Props {
  hasThread: boolean;
  status: string;
  plan: PlanStep[];
  awaitingApproval: boolean;
  approving: boolean;
  onApprove: (action: "approve" | "edit", plan?: PlanStep[]) => void;
  timeline: TimelineItem[];
  streaming: boolean;
  onResume: (() => void) | null;
}

// 中栏：步骤流（核心）—— 计划卡 + 按时间序的事件卡片
export default function StepStream({
  hasThread,
  status,
  plan,
  awaitingApproval,
  approving,
  onApprove,
  timeline,
  streaming,
  onResume,
}: Props) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [timeline.length, plan]);

  if (!hasThread) {
    return (
      <div className="flex-1 flex items-center justify-center text-neutral-400 text-sm">
        在左侧输入研究目标，或选择一个历史线程
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto min-h-0 px-4 py-3 space-y-3">
      {status === "running" && !streaming && onResume && (
        <div className="border border-blue-300 bg-blue-50 rounded-lg px-3 py-2 text-xs text-blue-800 flex items-center justify-between">
          <span>该线程处于执行中状态（可能是刷新/断线后恢复的检查点）。</span>
          <button
            className="px-2.5 py-1 bg-blue-600 text-white rounded hover:bg-blue-700"
            onClick={onResume}
          >
            断点续跑
          </button>
        </div>
      )}

      <PlanCard
        plan={plan}
        awaitingApproval={awaitingApproval}
        approving={approving}
        onApprove={onApprove}
      />

      {timeline.map((item) =>
        item.kind === "tool_call" ? (
          <ToolCallCard key={item.key} item={item} />
        ) : (
          <MarkerRow key={item.key} item={item} />
        )
      )}

      {streaming && (
        <div className="text-xs text-neutral-400 text-center animate-pulse">
          执行中，等待事件…
        </div>
      )}
      <div ref={endRef} />
    </div>
  );
}
