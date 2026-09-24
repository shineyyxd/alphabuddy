import type { MarkerItem } from "@/lib/store";

// 事件标记：compress / memory_write / conflict / warning / stopped / done
export default function MarkerRow({ item }: { item: MarkerItem }) {
  const m = item.marker;

  switch (m.type) {
    case "compress":
      return (
        <span className="inline-block text-xs bg-purple-50 text-purple-600 rounded-full px-3 py-1.5">
          ⤓ 上下文已压缩 {m.beforeChars.toLocaleString()} → {m.afterChars.toLocaleString()} 字符
        </span>
      );

    case "memory_write":
      return (
        <span
          className="inline-block text-xs bg-teal-50 text-teal-600 rounded-full px-3 py-1.5"
          title={m.summary}
        >
          ✎ 写入长期记忆：{m.memKey} — {m.summary}
        </span>
      );

    case "conflict":
      return (
        <div className="border border-red-100 bg-red-50/60 rounded-2xl px-4 py-3 shadow-sm">
          <div className="text-xs font-semibold text-red-600 mb-2">
            ⚠ 来源冲突：{m.field}（双源不一致，未强行统一）
          </div>
          <div className="grid grid-cols-2 gap-2">
            {m.sources.map((s, i) => (
              <div key={i} className="bg-white rounded-xl p-2.5 text-xs shadow-sm">
                <div className="text-neutral-400">{s.source}</div>
                <div className="text-base font-semibold text-red-600">{String(s.value)}</div>
                <div className="text-neutral-300">as_of: {s.as_of ?? "—"}</div>
              </div>
            ))}
          </div>
        </div>
      );

    case "warning":
      return (
        <div
          className={`rounded-2xl px-4 py-2.5 text-xs shadow-sm ${
            m.warningKind === "guard"
              ? "bg-amber-50 text-amber-700 border border-amber-100"
              : "bg-neutral-50 text-neutral-500 border border-neutral-100"
          }`}
        >
          {m.warningKind === "guard" ? "🛡 合规拦截：" : "⚠ 降级提示："}
          {m.message}
        </div>
      );

    case "stopped":
      return (
        <div className="border border-red-200 bg-red-50 rounded-2xl px-4 py-2.5 text-xs text-red-600 shadow-sm">
          ■ 任务已停止，原因：
          {m.reason === "step_limit"
            ? "达到步数上限"
            : m.reason === "token_budget"
              ? "token 预算耗尽"
              : "执行超时"}
        </div>
      );

    case "done":
      return (
        <div
          className={`rounded-2xl px-4 py-2.5 text-xs shadow-sm ${
            m.status === "done"
              ? "bg-green-50 text-green-700 border border-green-100"
              : "bg-red-50 text-red-600 border border-red-100"
          }`}
        >
          {m.status === "done" ? "✔ 任务完成：" : "✖ 任务失败："}
          {m.summary}
        </div>
      );
  }
}
