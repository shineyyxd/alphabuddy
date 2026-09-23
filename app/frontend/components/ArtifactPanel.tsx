"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Props {
  title: string | null;
  markdown: string;
  streaming: boolean;
  goal: string | null;
}

// 右栏：产物面板 —— 流式渲染 Markdown 报告 + 导出
export default function ArtifactPanel({ title, markdown, streaming, goal }: Props) {
  const exportMarkdown = () => {
    const header = `# ${title ?? goal ?? "研究报告"}\n\n> 研 Buddy 生成 · 仅做事实研究，不构成投资建议\n\n`;
    const blob = new Blob([header + markdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${(title ?? "yanbuddy-report").replace(/[\\/:*?"<>|]/g, "_")}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <aside className="w-[26rem] shrink-0 bg-white border-l border-neutral-200 flex flex-col min-h-0">
      <div className="flex items-center justify-between px-3 py-2 border-b border-neutral-200 shrink-0">
        <h2 className="text-sm font-semibold truncate">
          {title ?? "研究产物"}
          {streaming && markdown && (
            <span className="ml-2 text-xs text-blue-500 animate-pulse">生成中…</span>
          )}
        </h2>
        <button
          className="px-2.5 py-1 text-xs border border-neutral-300 rounded hover:bg-neutral-50 disabled:opacity-40 shrink-0"
          disabled={!markdown}
          onClick={exportMarkdown}
        >
          导出 Markdown
        </button>
      </div>
      <div className="flex-1 overflow-y-auto min-h-0 px-4 py-3">
        {markdown ? (
          <div className="report-md">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
          </div>
        ) : (
          <div className="h-full flex items-center justify-center text-neutral-400 text-sm text-center px-6">
            报告将在这里流式生成
            <br />
            （结论 / 证据清单 / 待核实事项 / 失效条件）
          </div>
        )}
      </div>
    </aside>
  );
}
