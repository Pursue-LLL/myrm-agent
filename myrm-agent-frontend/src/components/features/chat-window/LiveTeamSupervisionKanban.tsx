'use client';

import React, { useState } from 'react';
import { Users, CheckCircle2, Clock, AlertTriangle, ArrowRight, ShieldAlert, X, Send } from 'lucide-react';

export interface TeamMemberData {
  id: string;
  name: string;
  description: string;
  provider: string;
  context: string;
  role: 'lead' | 'teammate';
  phase: 'provisioning' | 'active' | 'failed';
  error?: string | null;
  created_at?: number;
}

export interface TeamTaskData {
  id: string;
  revision: number;
  subject: string;
  description: string;
  status: 'pending' | 'in_progress' | 'completed' | 'deleted';
  owner_id?: string | null;
  owner_name?: string | null;
  blocked_by: string[];
  write_scopes: string[];
  ready: boolean;
  write_scope_warnings: string[];
}

export interface TeamMessageData {
  id: string;
  team_id: string;
  sender_id: string;
  sender_name: string;
  target_id: string;
  target_name: string;
  content: string;
  mode: 'quiet' | 'waking';
  created_at: number;
  delivered: boolean;
}

export interface TeamProjectionData {
  team_id: string;
  members: TeamMemberData[];
  tasks: TeamTaskData[];
  failure?: string | null;
}

export interface LiveTeamSupervisionKanbanProps {
  projection: TeamProjectionData;
  onDismiss: () => void;
  onClaimTask?: (taskId: string, expectedRevision: number, ownerName: string) => Promise<void> | void;
  onCompleteTask?: (taskId: string, expectedRevision: number) => Promise<void> | void;
  onSendMessage?: (senderName: string, targetName: string, content: string) => Promise<void> | void;
  className?: string;
}

type TabType = 'tasks' | 'roster' | 'messages';

export function LiveTeamSupervisionKanban({
  projection,
  onDismiss,
  onClaimTask,
  onCompleteTask,
  onSendMessage,
  className = '',
}: LiveTeamSupervisionKanbanProps) {
  const [activeTab, setActiveTab] = useState<TabType>('tasks');
  const [selectedTaskOwner, setSelectedTaskOwner] = useState<string>('');
  const [msgTarget, setMsgTarget] = useState<string>('');
  const [msgContent, setMsgContent] = useState<string>('');

  const activeMembers = projection.members.filter((m) => m.phase === 'active');
  const readyTasks = projection.tasks.filter((t) => t.ready && t.status === 'pending');
  const inProgressTasks = projection.tasks.filter((t) => t.status === 'in_progress');
  const completedTasks = projection.tasks.filter((t) => t.status === 'completed');
  const blockedTasks = projection.tasks.filter((t) => !t.ready && t.status === 'pending');

  const handleClaim = (task: TeamTaskData) => {
    const owner = selectedTaskOwner || (activeMembers.find((m) => m.role === 'teammate')?.name ?? 'lead');
    if (onClaimTask) {
      onClaimTask(task.id, task.revision, owner);
    }
  };

  const handleComplete = (task: TeamTaskData) => {
    if (onCompleteTask) {
      onCompleteTask(task.id, task.revision);
    }
  };

  const handleSend = () => {
    if (!msgTarget || !msgContent.trim() || !onSendMessage) {
      return;
    }
    onSendMessage('lead', msgTarget, msgContent.trim());
    setMsgContent('');
  };

  return (
    <section
      aria-label="Durable Agent Teams 实时监控看板"
      className={`bg-card text-card-foreground border rounded-xl shadow-2xl p-5 flex flex-col gap-4 ${className}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b pb-3">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-primary/10 text-primary rounded-lg">
            <Users className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-semibold leading-none">Durable Agent Teams 看板</h2>
              <span className="text-xs font-mono bg-muted px-2 py-0.5 rounded text-muted-foreground">
                Team: {projection.team_id}
              </span>
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              会话自组网 · CAS 共享任务 DAG · 去中心化对等邮箱
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex gap-1.5 text-xs">
            <span className="px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-medium border border-emerald-500/20">
              {activeMembers.length} 成员活跃
            </span>
            <span className="px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-600 dark:text-blue-400 font-medium border border-blue-500/20">
              {readyTasks.length} 任务就绪
            </span>
          </div>
          <button
            onClick={onDismiss}
            aria-label="关闭面板"
            className="p-1 rounded-md text-muted-foreground hover:bg-muted transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Failure Banner */}
      {projection.failure ? (
        <div className="p-3 bg-destructive/10 border border-destructive/20 text-destructive rounded-lg flex items-start gap-2.5 text-xs">
          <ShieldAlert className="w-4 h-4 shrink-0 mt-0.5" />
          <div className="flex-1">
            <span className="font-semibold">团队异常状态：</span>
            <span>{projection.failure}</span>
          </div>
        </div>
      ) : null}

      {/* Tab Navigation */}
      <div className="flex border-b text-xs">
        <button
          onClick={() => setActiveTab('tasks')}
          className={`px-4 py-2 font-medium border-b-2 transition-colors ${
            activeTab === 'tasks'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          任务 DAG 看板 ({projection.tasks.length})
        </button>
        <button
          onClick={() => setActiveTab('roster')}
          className={`px-4 py-2 font-medium border-b-2 transition-colors ${
            activeTab === 'roster'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          成员名册 ({projection.members.length})
        </button>
        <button
          onClick={() => setActiveTab('messages')}
          className={`px-4 py-2 font-medium border-b-2 transition-colors ${
            activeTab === 'messages'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          对等邮箱消息流
        </button>
      </div>

      {/* Tab 1: Tasks Board */}
      {activeTab === 'tasks' ? (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 max-h-96 overflow-y-auto pr-1">
          {/* Column: Ready */}
          <div className="bg-muted/40 p-2.5 rounded-lg border flex flex-col gap-2">
            <div className="flex items-center justify-between text-xs font-semibold text-emerald-600 dark:text-emerald-400">
              <span>就绪 (Ready)</span>
              <span className="text-[10px] bg-emerald-500/10 px-1.5 py-0.5 rounded">{readyTasks.length}</span>
            </div>
            {readyTasks.map((t) => (
              <div key={t.id} className="bg-card p-2.5 rounded border shadow-sm text-xs flex flex-col gap-1.5">
                <div className="flex items-center justify-between">
                  <span className="font-mono font-medium">{t.id}</span>
                  <span className="text-[10px] text-muted-foreground">rev:{t.revision}</span>
                </div>
                <div className="font-semibold text-foreground">{t.subject}</div>
                {t.write_scope_warnings.length > 0 ? (
                  <div className="text-[10px] text-amber-600 dark:text-amber-400 flex items-center gap-1">
                    <AlertTriangle className="w-3 h-3 shrink-0" />
                    <span>范围重叠</span>
                  </div>
                ) : null}
                <button
                  onClick={() => handleClaim(t)}
                  className="mt-1 w-full py-1 bg-primary text-primary-foreground text-[10px] rounded font-medium hover:opacity-90"
                >
                  认领 (Claim)
                </button>
              </div>
            ))}
          </div>

          {/* Column: In Progress */}
          <div className="bg-muted/40 p-2.5 rounded-lg border flex flex-col gap-2">
            <div className="flex items-center justify-between text-xs font-semibold text-blue-600 dark:text-blue-400">
              <span>执行中 (In Progress)</span>
              <span className="text-[10px] bg-blue-500/10 px-1.5 py-0.5 rounded">{inProgressTasks.length}</span>
            </div>
            {inProgressTasks.map((t) => (
              <div key={t.id} className="bg-card p-2.5 rounded border shadow-sm text-xs flex flex-col gap-1.5">
                <div className="flex items-center justify-between">
                  <span className="font-mono font-medium">{t.id}</span>
                  <span className="text-[10px] text-muted-foreground">rev:{t.revision}</span>
                </div>
                <div className="font-semibold text-foreground">{t.subject}</div>
                <div className="text-[10px] text-muted-foreground">负责人: @{t.owner_name}</div>
                {t.write_scope_warnings.length > 0 ? (
                  <div className="text-[10px] text-amber-600 dark:text-amber-400 flex items-center gap-1">
                    <AlertTriangle className="w-3 h-3 shrink-0" />
                    <span>范围重叠</span>
                  </div>
                ) : null}
                <button
                  onClick={() => handleComplete(t)}
                  className="mt-1 w-full py-1 bg-emerald-600 text-white text-[10px] rounded font-medium hover:opacity-90 flex items-center justify-center gap-1"
                >
                  <CheckCircle2 className="w-3 h-3" /> 完成 (Complete)
                </button>
              </div>
            ))}
          </div>

          {/* Column: Blocked */}
          <div className="bg-muted/40 p-2.5 rounded-lg border flex flex-col gap-2">
            <div className="flex items-center justify-between text-xs font-semibold text-amber-600 dark:text-amber-400">
              <span>前置阻塞 (Blocked)</span>
              <span className="text-[10px] bg-amber-500/10 px-1.5 py-0.5 rounded">{blockedTasks.length}</span>
            </div>
            {blockedTasks.map((t) => (
              <div key={t.id} className="bg-card p-2.5 rounded border shadow-sm text-xs flex flex-col gap-1.5 opacity-80">
                <div className="flex items-center justify-between">
                  <span className="font-mono font-medium">{t.id}</span>
                  <span className="text-[10px] text-muted-foreground">rev:{t.revision}</span>
                </div>
                <div className="font-medium text-foreground">{t.subject}</div>
                <div className="text-[10px] text-amber-600 flex items-center gap-1">
                  <Clock className="w-3 h-3" /> 等待: {t.blocked_by.join(', ')}
                </div>
              </div>
            ))}
          </div>

          {/* Column: Completed */}
          <div className="bg-muted/40 p-2.5 rounded-lg border flex flex-col gap-2">
            <div className="flex items-center justify-between text-xs font-semibold text-muted-foreground">
              <span>已完成 (Completed)</span>
              <span className="text-[10px] bg-muted px-1.5 py-0.5 rounded">{completedTasks.length}</span>
            </div>
            {completedTasks.map((t) => (
              <div key={t.id} className="bg-card p-2.5 rounded border shadow-sm text-xs flex flex-col gap-1 opacity-70">
                <div className="flex items-center justify-between">
                  <span className="font-mono line-through">{t.id}</span>
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                </div>
                <div className="text-muted-foreground line-through text-[11px]">{t.subject}</div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {/* Tab 2: Roster */}
      {activeTab === 'roster' ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-96 overflow-y-auto pr-1">
          {projection.members.map((m) => (
            <div key={m.id} className="bg-muted/30 p-3 rounded-lg border flex flex-col gap-2 text-xs">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <span className="font-bold text-foreground">{m.name}</span>
                  <span className="text-[10px] px-1.5 py-0.2 rounded bg-primary/10 text-primary font-mono uppercase">
                    {m.role}
                  </span>
                </div>
                <span
                  className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
                    m.phase === 'active'
                      ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20'
                      : m.phase === 'failed'
                      ? 'bg-destructive/10 text-destructive border border-destructive/20'
                      : 'bg-muted text-muted-foreground'
                  }`}
                >
                  {m.phase}
                </span>
              </div>
              <p className="text-muted-foreground text-[11px] leading-relaxed">{m.description}</p>
              {m.error ? (
                <div className="text-[10px] text-destructive bg-destructive/10 p-1.5 rounded">
                  异常: {m.error}
                </div>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}

      {/* Tab 3: Peer Mailbox */}
      {activeTab === 'messages' ? (
        <div className="flex flex-col gap-3">
          <div className="flex gap-2">
            <select
              value={msgTarget}
              onChange={(e) => setMsgTarget(e.target.value)}
              className="text-xs bg-background border rounded px-2 py-1.5"
            >
              <option value="">选择收信人 (Target)</option>
              {activeMembers
                .filter((m) => m.name !== 'lead')
                .map((m) => (
                  <option key={m.name} value={m.name}>
                    {m.name}
                  </option>
                ))}
            </select>
            <input
              type="text"
              placeholder="输入给队员的对等消息..."
              value={msgContent}
              onChange={(e) => setMsgContent(e.target.value)}
              className="text-xs bg-background border rounded px-3 py-1.5 flex-1"
            />
            <button
              onClick={handleSend}
              className="px-3 py-1.5 bg-primary text-primary-foreground text-xs rounded font-medium flex items-center gap-1 hover:opacity-90"
            >
              <Send className="w-3.5 h-3.5" /> 发送
            </button>
          </div>
          <div className="p-4 bg-muted/20 border border-dashed rounded-lg text-center text-xs text-muted-foreground">
            对等邮箱通信保持无锁 FIFO 排队，目标节点在步骤边界自动接收。
          </div>
        </div>
      ) : null}

      {/* Footer info */}
      <div className="flex items-center justify-between text-[11px] text-muted-foreground border-t pt-2.5">
        <div className="flex items-center gap-1.5">
          <Clock className="w-3.5 h-3.5" />
          <span>CAS 乐观并发保护 · 自动依赖拓扑解析</span>
        </div>
        <div className="flex items-center gap-1">
          <span>模式: 隐式 Root Lead</span>
          <ArrowRight className="w-3 h-3" />
        </div>
      </div>
    </section>
  );
}
