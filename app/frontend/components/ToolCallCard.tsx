"use client";

import { useState } from "react";
import type { ToolCallItem } from "@/lib/store";

const STATUS_STYLE: Record<string, { badge: string; label: string }> = {
  running: { badge: "bg-blue-50 text-blue-600", label: "调用中" },
  ok: { badge: "bg-green-50 text-green-600", label: "ok" },
  empty: { badge: "bg-neutral-100 text-neutral-500", label: "empty（无数据）" },
  degraded: { badge: "bg-neutral-100 text-neutral-600", label: "degraded（降级）" },
  error: { badge: "bg-red-50 text-red-600", label: "error" },
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
    <div
      className={`rounded-2xl shadow-sm border ${
        item.status === "error"
          ? "border-red-200 bg-red-50/40"
          : failed
            ? "border-neutral-200 bg-neutral-50"
            : "border-neutral-100 bg-white"
      }`}
    >
      <button
        className="w-full flex items-center gap-2 px-4 py-2.5 text-left"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="text-neutral-300 text-xs">{open ? "▾" : "▸"}</span>
        <span className="font-mono text-[13px] font-medium text-neutral-700">{item.tool}</span>
        <span className={`text-[10px] px-2 py-0.5 rounded-full ${st.badge}`}>{st.label}</span>
        {failed && (
          <span className="text-xs text-neutral-400">无法验证 — 已生成降级卡片</span>
        )}
        <span className="ml-auto text-[10px] text-neutral-300">{item.callId}</span>
      </button>

      {open && (
        <div className="px-4 pb-4 border-t border-neutral-100/80 space-y-2.5">
          <div className="mt-2.5">
            <div className="text-[10px] text-neutral-400 mb-1">入参</div>
            <pre className="bg-neutral-50 rounded-xl p-2.5 text-xs overflow-x-auto text-neutral-600">
              {JSON.stringify(item.params, null, 2)}
            </pre>
          </div>

          {env && (
            <>
              {/* 证据四要素：来源 / 时点 / 单位 / 口径（固定展示） */}
              <div className="grid grid-cols-2 gap-2 bg-white border border-neutral-100 rounded-xl p-2.5">
                <Field label="来源 source" value={env.source} />
                <Field label="时点 as_of" value={env.as_of} />
                <Field label="单位 unit" value={env.unit} />
                <Field label="口径 caliber" value={env.caliber} />
              </div>

              {env.error && (
                <div
                  className={`text-xs rounded-xl p-2.5 ${
                    item.status === "error"
                      ? "bg-red-50 text-red-600"
                      : "bg-neutral-100 text-neutral-500"
                  }`}
                >
                  失败原因 [{env.error.kind}]：{env.error.message}
                </div>
              )}

              <div>
                <div className="text-[10px] text-neutral-400 mb-1">
                  出参信封（data / auth / fetched_at）
                </div>
                <pre className="bg-neutral-50 rounded-xl p-2.5 text-xs overflow-x-auto max-h-64 overflow-y-auto text-neutral-600">
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
