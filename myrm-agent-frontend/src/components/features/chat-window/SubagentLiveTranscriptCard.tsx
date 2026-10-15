import React, { useState } from 'react';
import { LiveTranscriptTimeline } from './subagent-live-transcript/LiveTranscriptTimeline';
import { SmartApprovalBanner } from './subagent-live-transcript/SmartApprovalBanner';
import {
  type DelegationTask,
  INITIAL_MOCK_APPROVAL,
  INITIAL_MOCK_EVENTS,
  INITIAL_MOCK_TASK,
  type SmartApproval,
  type TranscriptEvent,
} from './subagent-live-transcript/types';

export const SubagentLiveTranscriptCard: React.FC = () => {
  const [task, setTask] = useState<DelegationTask>(INITIAL_MOCK_TASK);
  const [events, setEvents] = useState<TranscriptEvent[]>(INITIAL_MOCK_EVENTS);
  const [approval, setApproval] = useState<SmartApproval | null>(INITIAL_MOCK_APPROVAL);
  const [liveAnnouncement, setLiveAnnouncement] = useState<string>(
    '子 Agent 实时 Live Transcript 正在流式接收中，后台委派账本已完成检查点 #3 落盘。',
  );

  const getReasoningBadgeClass = (effort: string) => {
    switch (effort) {
      case 'ultra':
        return 'bg-purple-900/60 text-purple-200 border-purple-700/60';
      case 'max':
        return 'bg-indigo-900/60 text-indigo-200 border-indigo-700/60';
      case 'medium':
        return 'bg-blue-900/60 text-blue-200 border-blue-700/60';
      default:
        return 'bg-zinc-800 text-zinc-300 border-zinc-700';
    }
  };

  const getStatusBadgeClass = (status: string) => {
    switch (status) {
      case 'running':
        return 'bg-emerald-950/80 text-emerald-300 border-emerald-600/60 animate-pulse';
      case 'waiting_approval':
        return 'bg-amber-950/80 text-amber-300 border-amber-600/60';
      case 'paused':
        return 'bg-zinc-800 text-zinc-300 border-zinc-600';
      case 'completed':
        return 'bg-blue-950/80 text-blue-300 border-blue-600/60';
      case 'failed':
        return 'bg-rose-950/80 text-rose-300 border-rose-600/60';
      default:
        return 'bg-zinc-800 text-zinc-400 border-zinc-700';
    }
  };

  const handleSimulateNextStep = () => {
    const nextSeq = events.length + 1;
    const newEvent: TranscriptEvent = {
      task_id: task.task_id,
      subagent_id: task.subagent_id,
      seq: nextSeq,
      timestamp: Date.now(),
      kind: 'thought',
      human_readable: `[步骤 #${nextSeq}] 深度推理中：核验多 Agent 间无死锁与原子回退路径 (MoA: ${task.reasoning_effort.toUpperCase()})`,
      payload: { checkpoint_step: task.checkpoint_step + 1, active_rules: 4 },
    };

    setEvents((prev) => [...prev, newEvent]);
    setTask((prev) => ({
      ...prev,
      checkpoint_step: prev.checkpoint_step + 1,
      status: 'running',
    }));
    setLiveAnnouncement(`新事件派发：步骤 #${nextSeq} 思考完成，检查点更新至 #${task.checkpoint_step + 1}。`);
  };

  const handleApprove = (approvalId: string) => {
    if (!approval || approval.approval_id !== approvalId) {
      return;
    }
    setApproval((prev) => (prev ? { ...prev, status: 'approved' } : null));

    const nextSeq = events.length + 1;
    const ev: TranscriptEvent = {
      task_id: task.task_id,
      subagent_id: task.subagent_id,
      seq: nextSeq,
      timestamp: Date.now(),
      kind: 'approval_resolved',
      human_readable: `用户批准命令：${approval.command}（单次消费授权，防越权复用）`,
      payload: { approval_id: approvalId, decision: 'approved' },
    };

    setEvents((prev) => [...prev, ev]);
    setTask((prev) => ({ ...prev, status: 'running' }));
    setLiveAnnouncement(`命令已被单次核准，子 Agent 已恢复执行并记录审计日志。`);
  };

  const handleDeny = (approvalId: string, reason: string) => {
    if (!approval || approval.approval_id !== approvalId) {
      return;
    }
    const prompt = `User rejected command: \`${approval.command}\`. Reason: '${reason}'. Guidance: Reconsider approach and propose safe alternative.`;

    setApproval((prev) =>
      prev
        ? {
            ...prev,
            status: 'denied',
            deny_reason: reason,
            remediation_prompt: prompt,
          }
        : null,
    );

    const nextSeq = events.length + 1;
    const ev: TranscriptEvent = {
      task_id: task.task_id,
      subagent_id: task.subagent_id,
      seq: nextSeq,
      timestamp: Date.now(),
      kind: 'denied_feedback',
      human_readable: `用户拒绝执行命令：${approval.command} | 原因: ${reason}`,
      payload: { approval_id: approvalId, decision: 'denied', deny_reason: reason },
    };

    setEvents((prev) => [...prev, ev]);
    setTask((prev) => ({ ...prev, status: 'running' }));
    setLiveAnnouncement(`用户拒绝高危命令，子 Agent 已接收 /deny 反馈指导并启动自省。`);
  };

  const handleSimulateCrashRecovery = () => {
    setTask((prev) => ({
      ...prev,
      status: 'paused',
      error_message: '宿主意外中断：已从本地持久化账本 (Ledger) 恢复检查点并暂停等待安全接续。',
    }));

    const nextSeq = events.length + 1;
    const ev: TranscriptEvent = {
      task_id: task.task_id,
      subagent_id: task.subagent_id,
      seq: nextSeq,
      timestamp: Date.now(),
      kind: 'state_change',
      human_readable: `[孤儿任务自愈] 进程重启后已成功重连持久账本，当前检查点：#${task.checkpoint_step}`,
      payload: { auto_recovered: true, checkpoint_step: task.checkpoint_step },
    };

    setEvents((prev) => [...prev, ev]);
    setLiveAnnouncement(`宿主重启自愈：孤儿任务已安全重锚定至检查点 #${task.checkpoint_step}，绝无任务丢失。`);
  };

  const handleReset = () => {
    setTask(INITIAL_MOCK_TASK);
    setEvents(INITIAL_MOCK_EVENTS);
    setApproval(INITIAL_MOCK_APPROVAL);
    setLiveAnnouncement('演示重置：初始状态已恢复。');
  };

  return (
    <div
      data-testid="subagent-live-transcript-card"
      className="p-4 rounded-xl border border-zinc-800 bg-zinc-950 text-zinc-100 shadow-xl space-y-3"
    >
      {/* Accessible Live Region */}
      <output aria-live="polite" className="sr-only">
        {liveAnnouncement}
      </output>

      {/* Card Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-zinc-800/80 pb-3">
        <div className="flex items-center gap-2">
          <span className="text-lg">📜</span>
          <div>
            <h3 className="font-semibold text-sm text-zinc-100 flex items-center gap-1.5">
              <span>子 Agent 实时 Live Transcript 与后台委派账本</span>
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400">
                Hermes v0.19 对标
              </span>
            </h3>
            <p className="text-xs text-zinc-400">
              透明人类可读实时轨迹流 · 跨进程持久化自愈 · Smart Approvals 独立审核 · MoA 细粒度推理分配
            </p>
          </div>
        </div>

        {/* Status Badges */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <span
            className={`px-2 py-0.5 rounded-full text-xs font-mono font-medium border ${getStatusBadgeClass(
              task.status,
            )}`}
          >
            {task.status.toUpperCase()}
          </span>
          <span
            className={`px-2 py-0.5 rounded-full text-xs font-mono font-medium border ${getReasoningBadgeClass(
              task.reasoning_effort,
            )}`}
          >
            MoA: {task.reasoning_effort.toUpperCase()}
          </span>
          <span className="px-2 py-0.5 rounded-full text-xs font-mono bg-zinc-900 text-zinc-300 border border-zinc-800">
            检查点 #{task.checkpoint_step}
          </span>
        </div>
      </div>

      {/* Task Summary Banner */}
      <div className="p-2.5 rounded-lg bg-zinc-900/60 border border-zinc-800/60 text-xs flex flex-col gap-1">
        <div className="flex items-center justify-between text-zinc-400 text-[11px]">
          <span>任务 ID: <code className="text-zinc-200">{task.task_id}</code></span>
          <span>委派角色: <span className="text-indigo-300 font-medium">{task.role}</span></span>
        </div>
        <p className="text-zinc-200 font-medium">{task.prompt}</p>
        {task.error_message && (
          <div className="text-amber-300 text-[11px] pt-1 flex items-center gap-1">
            <span>⚠️</span> {task.error_message}
          </div>
        )}
      </div>

      {/* Smart Approval Banner */}
      <SmartApprovalBanner
        approval={approval}
        onApprove={handleApprove}
        onDeny={handleDeny}
      />

      {/* Live Transcript Event Stream */}
      <LiveTranscriptTimeline events={events} />

      {/* Interactive Simulation Controls */}
      <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-zinc-800/60">
        <div className="flex items-center gap-2 flex-wrap">
          <button
            type="button"
            onClick={handleSimulateNextStep}
            className="px-2.5 py-1 text-xs rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 transition-colors"
          >
            ➕ 模拟下一步 (Live Emit)
          </button>
          <button
            type="button"
            onClick={handleSimulateCrashRecovery}
            className="px-2.5 py-1 text-xs rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 transition-colors"
          >
            🔄 模拟重启自愈 (Ledger Recover)
          </button>
        </div>
        <button
          type="button"
          onClick={handleReset}
          className="text-xs text-zinc-400 hover:text-zinc-200 underline transition-colors"
        >
          重置演示
        </button>
      </div>
    </div>
  );
};
