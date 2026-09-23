"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import TopBar from "@/components/TopBar";
import LeftSidebar from "@/components/LeftSidebar";
import StepStream from "@/components/StepStream";
import ArtifactPanel from "@/components/ArtifactPanel";
import CostBar from "@/components/CostBar";
import { api, streamRun } from "@/lib/api";
import { applyEvent, applySnapshot, initialState, type WorkbenchState } from "@/lib/store";
import type { PlanStep, Skill, SseEvent, ThreadMeta } from "@/lib/types";
import {
  MOCK_GOAL,
  MOCK_THREAD_ID,
  mockCapabilities,
  mockEventsAfterApproval,
  mockEventsBeforeApproval,
  mockThreads,
} from "@/mocks/sse-fixture";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export default function Workbench() {
  const searchParams = useSearchParams();
  const mockMode = searchParams.get("mock") === "1";

  const [threads, setThreads] = useState<ThreadMeta[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [activeGoal, setActiveGoal] = useState<string | null>(null);
  const [wb, setWb] = useState<WorkbenchState>(initialState);
  const [streaming, setStreaming] = useState(false);
  const [approving, setApproving] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 代际计数：切换线程/重开运行时作废旧回放与旧流
  const genRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);

  const dispatchEvent = useCallback((ev: SseEvent) => {
    setWb((prev) => applyEvent(prev, ev));
  }, []);

  const resetWorkbench = useCallback(() => {
    genRef.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
    setWb(initialState());
    setStreaming(false);
    setApproving(false);
    setError(null);
    return genRef.current;
  }, []);

  // ---- mock 模式：回放 fixture ----
  const replayMock = useCallback(
    async (events: SseEvent[], gen: number, delayMs = 600) => {
      setStreaming(true);
      for (const ev of events) {
        if (genRef.current !== gen) return;
        await sleep(delayMs);
        if (genRef.current !== gen) return;
        dispatchEvent(ev);
      }
      setStreaming(false);
    },
    [dispatchEvent]
  );

  // ---- 真实模式：从快照恢复（检查点与恢复演示路径）----
  const restoreThread = useCallback(
    async (threadId: string) => {
      const gen = resetWorkbench();
      setActiveThreadId(threadId);
      try {
        const snap = await api.getState(threadId);
        if (genRef.current !== gen) return;
        setActiveGoal(snap.goal);
        for (const ev of snap.events) {
          setWb((prev) => applyEvent(prev, ev));
        }
        setWb((prev) => applySnapshot(prev, snap));
      } catch (e) {
        setError(`恢复线程状态失败：${String(e)}`);
      }
    },
    [resetWorkbench]
  );

  // ---- 真实模式：启动/续跑（POST /run，SSE）----
  const startRun = useCallback(
    async (threadId: string, resumeToken: string | null = null) => {
      const gen = genRef.current;
      const controller = new AbortController();
      abortRef.current = controller;
      setStreaming(true);
      setError(null);
      try {
        await streamRun(threadId, resumeToken, (ev) => {
          if (genRef.current === gen) dispatchEvent(ev);
        }, controller.signal);
      } catch (e) {
        if (!controller.signal.aborted) setError(`运行流中断：${String(e)}`);
      } finally {
        if (genRef.current === gen) {
          setStreaming(false);
          abortRef.current = null;
        }
      }
    },
    [dispatchEvent]
  );

  // ---- 初始化 ----
  useEffect(() => {
    if (mockMode) {
      setThreads(mockThreads);
      const gen = resetWorkbench();
      setActiveThreadId(MOCK_THREAD_ID);
      setActiveGoal(MOCK_GOAL);
      void replayMock(mockEventsBeforeApproval, gen);
      return;
    }
    api
      .listThreads()
      .then((r) => {
        setThreads(r.threads);
        const last = window.localStorage.getItem("yanbuddy:lastThread");
        if (last && r.threads.some((t) => t.thread_id === last)) {
          void restoreThread(last);
        }
      })
      .catch((e) => setError(`加载线程列表失败（后端未启动？可加 ?mock=1 进入演示模式）：${String(e)}`));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mockMode]);

  // ---- 交互 ----
  const handleSelectThread = useCallback(
    (id: string) => {
      window.localStorage.setItem("yanbuddy:lastThread", id);
      if (mockMode) {
        const gen = resetWorkbench();
        setActiveThreadId(MOCK_THREAD_ID);
        setActiveGoal(MOCK_GOAL);
        void replayMock(mockEventsBeforeApproval, gen);
        return;
      }
      void restoreThread(id);
    },
    [mockMode, resetWorkbench, restoreThread, replayMock]
  );

  const handleCreateThread = useCallback(
    async (goal: string, skill: Skill | null) => {
      if (mockMode) {
        // mock 模式只演示单条预置线程
        const gen = resetWorkbench();
        setActiveThreadId(MOCK_THREAD_ID);
        setActiveGoal(goal || MOCK_GOAL);
        void replayMock(mockEventsBeforeApproval, gen);
        return;
      }
      setCreating(true);
      setError(null);
      try {
        const { thread_id } = await api.createThread(goal, skill);
        const r = await api.listThreads();
        setThreads(r.threads);
        window.localStorage.setItem("yanbuddy:lastThread", thread_id);
        resetWorkbench();
        setActiveThreadId(thread_id);
        setActiveGoal(goal);
        void startRun(thread_id);
      } catch (e) {
        setError(`创建线程失败：${String(e)}`);
      } finally {
        setCreating(false);
      }
    },
    [mockMode, resetWorkbench, startRun]
  );

  const handleApprove = useCallback(
    async (action: "approve" | "edit", plan?: PlanStep[]) => {
      if (!activeThreadId) return;
      setApproving(true);
      setError(null);
      try {
        if (mockMode) {
          await sleep(300);
          // action=edit 时以后端会采用编辑后的计划，前端同步替换计划卡；
          // 回放时过滤掉被删除步骤的事件，模拟后端按编辑后计划执行
          let events = mockEventsAfterApproval;
          if (action === "edit" && plan) {
            const keepIds = new Set(plan.map((s) => s.id));
            setWb((prev) => ({
              ...prev,
              plan: plan.map((s) => ({ ...s, status: "pending" as const })),
            }));
            events = events.filter((ev) => {
              const stepId = (ev.data as { step_id?: string }).step_id;
              return stepId === undefined || keepIds.has(stepId);
            });
          }
          const gen = genRef.current;
          setApproving(false);
          void replayMock(events, gen, 700);
          return;
        }
        await api.approve(activeThreadId, action, plan);
        setApproving(false);
        void startRun(activeThreadId);
      } catch (e) {
        setError(`审批提交失败：${String(e)}`);
        setApproving(false);
      }
    },
    [activeThreadId, mockMode, replayMock, startRun]
  );

  const handleResume = useCallback(() => {
    if (activeThreadId && !mockMode) void startRun(activeThreadId);
  }, [activeThreadId, mockMode, startRun]);

  const loadCapabilities = useCallback(async () => {
    if (mockMode) return mockCapabilities.tools;
    const r = await api.capabilities();
    return r.tools;
  }, [mockMode]);

  return (
    <div className="h-full flex flex-col">
      <TopBar />
      {mockMode && (
        <div className="bg-indigo-50 border-b border-indigo-200 text-indigo-700 text-xs px-4 py-1 shrink-0">
          演示模式（?mock=1）：回放内置 fixture 事件流，不依赖后端。审批后将继续回放执行阶段。
        </div>
      )}
      {error && (
        <div className="bg-red-50 border-b border-red-200 text-red-700 text-xs px-4 py-1.5 shrink-0">
          {error}
        </div>
      )}
      <div className="flex-1 flex min-h-0">
        <LeftSidebar
          threads={threads}
          activeThreadId={activeThreadId}
          onSelectThread={handleSelectThread}
          onCreateThread={handleCreateThread}
          creating={creating}
          loadCapabilities={loadCapabilities}
        />
        <main className="flex-1 flex flex-col min-w-0 bg-neutral-100">
          {activeGoal && (
            <div className="px-4 py-2 border-b border-neutral-200 bg-white text-sm shrink-0">
              <span className="text-neutral-400 text-xs mr-2">研究目标</span>
              {activeGoal}
            </div>
          )}
          <StepStream
            hasThread={activeThreadId !== null}
            status={wb.status}
            plan={wb.plan}
            awaitingApproval={wb.awaitingApproval}
            approving={approving}
            onApprove={handleApprove}
            timeline={wb.timeline}
            streaming={streaming}
            onResume={wb.status === "running" && !streaming ? handleResume : null}
          />
        </main>
        <ArtifactPanel
          title={wb.artifactTitle}
          markdown={wb.artifactMarkdown}
          streaming={streaming}
          goal={activeGoal}
        />
      </div>
      <CostBar cost={wb.cost} />
    </div>
  );
}
