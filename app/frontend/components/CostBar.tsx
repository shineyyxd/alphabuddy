import type { Cost } from "@/lib/types";

function fmtElapsed(ms: number) {
  if (ms < 1000) return `${ms}ms`;
  const s = ms / 1000;
  return s < 60 ? `${s.toFixed(1)}s` : `${Math.floor(s / 60)}m${Math.round(s % 60)}s`;
}

// 底部成本条：cost 事件驱动（差异化能力）
export default function CostBar({ cost }: { cost: Cost | null }) {
  const c: Cost = cost ?? {
    tokens_in: 0,
    tokens_out: 0,
    llm_calls: 0,
    tool_calls: 0,
    elapsed_ms: 0,
    budget_remaining: 0,
  };
  const items: [string, string][] = [
    ["tokens in", c.tokens_in.toLocaleString()],
    ["tokens out", c.tokens_out.toLocaleString()],
    ["LLM 调用", String(c.llm_calls)],
    ["工具调用", String(c.tool_calls)],
    ["耗时", fmtElapsed(c.elapsed_ms)],
    ["预算余量", c.budget_remaining.toLocaleString()],
  ];
  return (
    <footer className="h-7 shrink-0 bg-neutral-50 border-t border-neutral-100 flex items-center px-4 gap-5 text-[11px] overflow-x-auto">
      <span className="text-neutral-300 shrink-0">成本</span>
      {items.map(([label, value]) => (
        <span key={label} className="whitespace-nowrap">
          <span className="text-neutral-400">{label} </span>
          <span className="text-neutral-700 font-mono">{value}</span>
        </span>
      ))}
    </footer>
  );
}
