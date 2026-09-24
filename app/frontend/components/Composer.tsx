"use client";

import { useEffect, useRef } from "react";
import type { Skill } from "@/lib/types";
import { SKILL_CARDS } from "./LeftSidebar";

interface Props {
  goal: string;
  skill: Skill | null;
  sending: boolean;
  focusSignal: number;
  onChangeGoal: (v: string) => void;
  onChangeSkill: (s: Skill | null) => void;
  onSend: () => void;
}

// 底部固定输入条：技能快捷 chips + 多行输入 + 发送
export default function Composer({
  goal,
  skill,
  sending,
  focusSignal,
  onChangeGoal,
  onChangeSkill,
  onSend,
}: Props) {
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (focusSignal > 0) taRef.current?.focus();
  }, [focusSignal]);

  const canSend = goal.trim().length > 0 && !sending;

  return (
    <div className="shrink-0 px-6 pb-4 pt-2 bg-white">
      <div className="max-w-3xl mx-auto">
        <div className="flex gap-2 mb-2">
          {SKILL_CARDS.map((s) => {
            const active = skill === s.value;
            return (
              <button
                key={s.value}
                className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
                  active
                    ? "bg-blue-50 border-blue-300 text-blue-600"
                    : "bg-white border-neutral-200 text-neutral-500 hover:border-blue-200 hover:text-blue-600"
                }`}
                onClick={() => onChangeSkill(active ? null : s.value)}
              >
                {s.label}
              </button>
            );
          })}
          {skill === null && (
            <span className="text-[11px] text-neutral-300 self-center ml-1">
              未选技能卡时将自动意图识别
            </span>
          )}
        </div>
        <div className="flex items-end gap-2 bg-white border border-neutral-200 rounded-2xl px-4 py-3 shadow-sm focus-within:border-blue-300 transition-colors">
          <textarea
            ref={taRef}
            className="flex-1 text-sm resize-none focus:outline-none placeholder:text-neutral-300"
            rows={2}
            placeholder="问问主研：想验证什么投资命题？"
            value={goal}
            onChange={(e) => onChangeGoal(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                if (canSend) onSend();
              }
            }}
          />
          <button
            className="w-9 h-9 shrink-0 rounded-full bg-blue-600 text-white flex items-center justify-center hover:bg-blue-700 disabled:opacity-30 transition-colors"
            disabled={!canSend}
            onClick={onSend}
            title="开始研究"
          >
            {sending ? (
              <span className="text-xs animate-pulse">…</span>
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                <path
                  d="M5 12h14M13 6l6 6-6 6"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            )}
          </button>
        </div>
        <p className="text-center text-[11px] text-neutral-300 mt-2">
          内容由 AI 生成，仅做事实研究，不构成投资建议
        </p>
      </div>
    </div>
  );
}
