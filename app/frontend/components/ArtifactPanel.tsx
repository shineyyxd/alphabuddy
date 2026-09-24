"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Props {
  title: string | null;
  markdown: string;
  streaming: boolean;
  goal: string | null;
  collapsed: boolean;
  onToggle: () => void;
}

// 右栏：产物面板（差异化能力）—— 流式 Markdown 报告 + 导出，可折叠
export default function ArtifactPanel({
  title,
  markdown,
  streaming,
  goal,
  collapsed,
  onToggle,
}: Props) {
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

  if (collapsed) {
    return (
      <aside className="w-8 shrink-0 bg-neutral-50 border-l border-neutral-100 flex flex-col items-center pt-3">
        <button
          className="text-neutral-400 hover:text-blue-600 text-xs transition-colors"
          style={{ writingMode: "vertical-rl" }}
          onClick={onToggle}
          title="展开产物面板"
        >
          ⟨ 研究产物
        </button>
      </aside>
    );
  }

  return (
    <aside className="w-[26rem] shrink-0 bg-neutral-50 border-l border-neutral-100 flex flex-col min-h-0 relative">
      {/* 栏边缘折叠按钮 */}
      <button
        className="absolute -left-3 top-4 z-10 w-6 h-6 bg-white border border-neutral-200 rounded-full text-neutral-400 hover:text-blue-600 text-xs shadow-sm transition-colors"
        onClick={onToggle}
        title="折叠产物面板"
      >
        ⟩
      </button>
      <div className="flex items-center justify-between px-4 py-3 shrink-0">
        <h2 className="text-sm font-semibold text-neutral-800 truncate">
          {title ?? "研究产物"}
          {streaming && markdown && (
            <span className="ml-2 text-xs text-blue-500 animate-pulse">生成中…</span>
          )}
        </h2>
        <button
          className="px-3 py-1.5 text-xs bg-white border border-neutral-200 rounded-full hover:border-blue-300 hover:text-blue-600 disabled:opacity-40 shrink-0 transition-colors"
          disabled={!markdown}
          onClick={exportMarkdown}
        >
          导出 Markdown
        </button>
      </div>
      <div className="flex-1 overflow-y-auto min-h-0 px-4 pb-4">
        {markdown ? (
          <div className="report-md bg-white rounded-2xl shadow-sm border border-neutral-100 px-5 py-4">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
          </div>
        ) : (
          <div className="h-full flex items-center justify-center text-neutral-300 text-sm text-center px-6">
            报告将在这里流式生成
            <br />
            （结论 / 证据清单 / 待核实事项 / 失效条件）
          </div>
        )}
      </div>
    </aside>
  );
}
