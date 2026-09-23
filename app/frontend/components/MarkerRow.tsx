import type { MarkerItem } from "@/lib/store";

// 中栏事件标记行：compress / memory_write / conflict / warning / stopped / done
export default function MarkerRow({ item }: { item: MarkerItem }) {
  const m = item.marker;

  switch (m.type) {
    case "compress":
      return (
        <div className="flex justify-center">
          <span className="text-xs bg-purple-50 text-purple-700 border border-purple-200 rounded-full px-3 py-1">
            ⤓ 上下文已压缩 {m.beforeChars.toLocaleString()} → {m.afterChars.toLocaleString()} 字符
          </span>
        </div>
      );

    case "memory_write":
      return (
        <div className="flex justify-center">
          <span
            className="text-xs bg-teal-50 text-teal-700 border border-teal-200 rounded-full px-3 py-1"
            title={m.summary}
          >
            ✎ 写入长期记忆：{m.memKey} — {m.summary}
          </span>
        </div>
      );

    case "conflict":
      return (
        <div className="border border-red-300 bg-red-50 rounded-lg px-3 py-2">
          <div className="text-xs font-semibold text-red-700 mb-1">
            ⚠ 来源冲突：{m.field}（双源不一致，未强行统一）
          </div>
          <div className="grid grid-cols-2 gap-2">
            {m.sources.map((s, i) => (
              <div key={i} className="bg-white border border-red-200 rounded p-2 text-xs">
                <div className="text-neutral-500">{s.source}</div>
                <div className="text-base font-semibold text-red-700">{String(s.value)}</div>
                <div className="text-neutral-400">as_of: {s.as_of ?? "—"}</div>
              </div>
            ))}
          </div>
        </div>
      );

    case "warning":
      return (
        <div
          className={`rounded px-3 py-2 text-xs border ${
            m.warningKind === "guard"
              ? "bg-amber-50 border-amber-300 text-amber-800"
              : "bg-neutral-100 border-neutral-300 text-neutral-600"
          }`}
        >
          {m.warningKind === "guard" ? "🛡 合规拦截：" : "⚠ 降级提示："}
          {m.message}
        </div>
      );

    case "stopped":
      return (
        <div className="border border-red-400 bg-red-50 rounded px-3 py-2 text-xs text-red-700">
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
          className={`rounded px-3 py-2 text-xs border ${
            m.status === "done"
              ? "bg-green-50 border-green-300 text-green-800"
              : "bg-red-50 border-red-300 text-red-700"
          }`}
        >
          {m.status === "done" ? "✔ 任务完成：" : "✖ 任务失败："}
          {m.summary}
        </div>
      );
  }
}
