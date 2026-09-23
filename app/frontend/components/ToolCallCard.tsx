"use client";

import { useState } from "react";
import type { ToolCallItem } from "@/lib/store";

const STATUS_STYLE: Record<string, { border: string; badge: string; label: string }> = {
  running: { border: "border-blue-300", badge: "bg-blue-100 text-blue-700", label: "调用中" },
  ok: { border: "border-neutral-200", badge: "bg-green-100 text-green-700", label: "ok" },
  empty: { border: "border-neutral-300", badge: "bg-neutral-100 text-neutral-600", label: "empty（无数据）" },
  degraded: { border: "border-neutral-400", badge: "bg-neutral-200 text-neutral-700", label: "degraded（降级）" },
  error: { border: "border-red-400", badge: "bg-red-100 text-red-700", label: "error" },
};

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div className="min-w-0">
      <div className="text-[10px] text-neutral-400">{label}</div>
      <div className="text-xs text-neutral-700 break-words">{value ?? "—"}</div>
    </div>
  );
}

export default function ToolCallCard({ item }: { item: ToolCallItem }) {
  const [open, setOpen] = useState(false);
  const st = STATUS_STYLE[item.status] ?? STATUS_STYLE.running;
  const env = item.envelope;
  const failed = item.status === "error" || item.status === "degraded";

  return (
    <div className={`border rounded-lg bg-white ${st.border} ${failed ? "bg-neutral-50" : ""}`}>
      <button
        className="w-full flex items-center gap-2 px-3 py-2 text-left"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="text-neutral-400 text-xs">{open ? "▾" : "▸"}</span>
        <span className="font-mono text-sm font-medium">{item.tool}</span>
        <span className={`text-[10px] px-1.5 py-0.5 rounded ${st.badge}`}>{st.label}</span>
        {failed && (
          <span className="text-xs text-neutral-500">无法验证 — 已生成降级卡片</span>
        )}
        <span className="ml-auto text-[10px] text-neutral-400">{item.callId}</span>
      </button>

      {open && (
        <div className="px-3 pb-3 border-t border-neutral-100 space-y-2">
          <div className="mt-2">
            <div className="text-[10px] text-neutral-400 mb-1">入参</div>
            <pre className="bg-neutral-50 border border-neutral-200 rounded p-2 text-xs overflow-x-auto">
              {JSON.stringify(item.params, null, 2)}
            </pre>
          </div>

          {env && (
            <>
              {/* 证据四要素：来源 / 时点 / 单位 / 口径（固定展示） */}
              <div className="grid grid-cols-2 gap-2 bg-neutral-50 border border-neutral-200 rounded p-2">
                <Field label="来源 source" value={env.source} />
                <Field label="时点 as_of" value={env.as_of} />
                <Field label="单位 unit" value={env.unit} />
                <Field label="口径 caliber" value={env.caliber} />
              </div>

              {env.error && (
                <div
                  className={`text-xs rounded p-2 border ${
                    item.status === "error"
                      ? "bg-red-50 border-red-200 text-red-700"
                      : "bg-neutral-100 border-neutral-300 text-neutral-600"
                  }`}
                >
                  失败原因 [{env.error.kind}]：{env.error.message}
                </div>
              )}

              <div>
                <div className="text-[10px] text-neutral-400 mb-1">
                  出参信封（data / auth / fetched_at）
                </div>
                <pre className="bg-neutral-50 border border-neutral-200 rounded p-2 text-xs overflow-x-auto max-h-64 overflow-y-auto">
                  {JSON.stringify(
                    {
                      data: env.data,
                      auth: env.auth ?? null,
                      fetched_at: env.fetched_at ?? null,
                    },
                    null,
                    2
                  )}
                </pre>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
