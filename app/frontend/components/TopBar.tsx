export default function TopBar() {
  return (
    <header className="flex items-center justify-between px-4 h-12 bg-neutral-900 text-white shrink-0">
      <div className="flex items-baseline gap-3">
        <h1 className="text-lg font-bold tracking-wide">研 Buddy</h1>
        <span className="text-xs text-neutral-400">透明 Agent 工作台 · 投资研究</span>
      </div>
      <p className="text-xs text-amber-300">仅做事实研究，不构成投资建议</p>
    </header>
  );
}
