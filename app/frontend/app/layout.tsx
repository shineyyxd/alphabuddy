import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AlphaBuddy — 透明 Agent 工作台",
  description: "面向投资研究者的透明 Agent 工作台。仅做事实研究，不构成投资建议。",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body className="h-full overflow-hidden">{children}</body>
    </html>
  );
}
