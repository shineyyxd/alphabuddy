"use client";

import type { Skill } from "@/lib/types";
import { SKILL_CARDS } from "./LeftSidebar";

const WEEKDAYS = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];

export const SUGGESTED_GOALS = [
  "验证寒武纪盈利改善来自主营业务",
  "点评寒武纪最新财报",
  "看看寒武纪今天的行情和估值",
  "验证「AI 算力需求仍在加速」这一命题",
];

function greeting(): string {
  const h = new Date().getHours();
  if (h < 11) return "早上好";
  if (h < 14) return "中午好";
  if (h < 18) return "下午好";
  return "晚上好";
}

function dateLine(): string {
  const d = new Date();
  return `${d.getMonth() + 1}月${d.getDate()}日${WEEKDAYS[d.getDay()]}`;
}

interface Props {
  onPickSkill: (skill: Skill) => void;
  onPickGoal: (goal: string) => void;
}

// 首页空状态：问候语 → 三张技能入口卡 → 示例研究目标
export default function HomeEmpty({ onPickSkill, onPickGoal }: Props) {
  return (
    <div className="flex-1 overflow-y-auto min-h-0">
      <div className="max-w-2xl mx-auto px-6 pt-14 pb-8">
        <p className="text-xs text-neutral-400">{dateLine()}</p>
        <h1 className="text-2xl font-bold text-neutral-900 mt-1">
          {greeting()}，先看一件最重要的事。
        </h1>

        {/* 技能入口卡 */}
        <div className="grid grid-cols-3 gap-3 mt-8">
          {SKILL_CARDS.map((s) => (
            <button
              key={s.value}
              className="bg-white border border-neutral-100 rounded-2xl px-4 py-5 text-left shadow-sm hover:border-blue-200 hover:shadow transition-all"
              onClick={() => onPickSkill(s.value)}
            >
              <div className="text-sm font-semibold text-neutral-800">{s.label}</div>
              <div className="text-xs text-neutral-400 mt-1">{s.desc}</div>
            </button>
          ))}
        </div>

        {/* 建议研究目标 */}
        <div className="mt-10">
          <h2 className="text-sm font-medium text-neutral-500 flex items-center gap-1.5">
            <span className="text-blue-500">✦</span> 可以继续问主研
          </h2>
          <p className="text-xs text-neutral-400 mt-1">
            给一个研究目标，主研会出计划、调真实金融数据、全程可见可控。
          </p>
          <div className="grid grid-cols-2 gap-2.5 mt-3">
            {SUGGESTED_GOALS.map((g) => (
              <button
                key={g}
                className="text-left text-[13px] text-neutral-600 bg-white border border-neutral-100 rounded-xl px-3.5 py-3 hover:border-blue-200 hover:text-blue-600 transition-colors"
                onClick={() => onPickGoal(g)}
              >
                {g}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
