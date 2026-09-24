"use client";

import { useEffect, useRef } from "react";
import type { PlanStep } from "@/lib/types";
import type { TimelineItem } from "@/lib/store";
import PlanCard from "./PlanCard";
import ToolCallCard from "./ToolCallCard";
import MarkerRow from "./MarkerRow";

// 「主研」头像（对话流视觉）
export function ZhuyanAvatar() {
  return (
    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 text-white text-xs font-bold flex items-center justify-center shrink-0 select-none">
      研
    </div>
  );
}

function AgentMessage({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex gap-3">
      <ZhuyanAvatar />
      <div className="flex-1 min-w-0 pt-0.5">{children}</div>
    </div>
  );
}

interface Props {
  status: string;
  goal: string | null;
  plan: PlanStep[];
  awaitingApproval: boolean;
  approving: boolean;
  onApprove: (action: "approve" | "edit", plan?: PlanStep[]) => void;
  timeline: TimelineItem[];
  streaming: boolean;
  onResume: (() => void) | null;
}

// 中栏：对话式步骤流 —— 用户目标气泡 + 「主研」的消息卡片序列
export default function StepStream({
  status,
  goal,
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

  return (
    <div className="flex-1 overflow-y-auto min-h-0">
      <div className="max-w-3xl mx-auto px-6 py-6 space-y-4">
        {/* 用户研究目标气泡 */}
        {goal && (
          <div className="flex justify-end">
            <div className="max-w-[80%] bg-blue-600 text-white text-sm rounded-2xl rounded-br-md px-4 py-2.5">
              {goal}
            </div>
          </div>
        )}

        {status === "running" && !streaming && onResume && (
          <AgentMessage>
            <div className="border border-blue-100 bg-blue-50 rounded-2xl px-4 py-3 text-[13px] text-blue-800 flex items-center justify-between">
              <span>该线程处于执行中状态（可能是刷新/断线后恢复的检查点）。</span>
              <button
                className="px-3 py-1.5 text-xs bg-blue-600 text-white rounded-full hover:bg-blue-700 shrink-0 ml-3"
                onClick={onResume}
              >
                断点续跑
              </button>
            </div>
          </AgentMessage>
        )}

        {plan.length > 0 && (
          <AgentMessage>
            <PlanCard
              plan={plan}
              awaitingApproval={awaitingApproval}
              approving={approving}
              onApprove={onApprove}
            />
          </AgentMessage>
        )}

        {timeline.map((item) => (
          <AgentMessage key={item.key}>
            {item.kind === "tool_call" ? (
              <ToolCallCard item={item} />
            ) : (
              <MarkerRow item={item} />
            )}
          </AgentMessage>
        ))}

        {streaming && (
          <AgentMessage>
            <div className="flex items-center gap-1.5 py-2">
              <span className="w-1.5 h-1.5 rounded-full bg-neutral-300 animate-bounce" />
              <span className="w-1.5 h-1.5 rounded-full bg-neutral-300 animate-bounce [animation-delay:150ms]" />
              <span className="w-1.5 h-1.5 rounded-full bg-neutral-300 animate-bounce [animation-delay:300ms]" />
            </div>
          </AgentMessage>
        )}
        <div ref={endRef} />
      </div>
    </div>
  );
}
