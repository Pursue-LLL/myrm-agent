'use client';

import { useState, useCallback, useEffect } from 'react';
import {
  Terminal,
  Play,
  Send,
  Square,
  CheckCircle2,
  AlertOctagon,
  Clock,
  RefreshCw,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';

export type SubagentStatus = 'pending' | 'running' | 'completed' | 'failed' | 'killed' | 'timeout';

export interface SubagentEventItemData {
  event_id: string;
  event_type: string;
  subagent_id: string;
  payload: Record<string, string | number | boolean>;
  timestamp: string;
}

export interface SubagentInputMessageData {
  message_id: string;
  subagent_id: string;
  content: string;
  sender_role: string;
  created_at: string;
}

export interface SubagentTaskItemData {
  subagent_id: string;
  parent_session_id: string;
  task_prompt: string;
  agent_profile: string;
  tools_whitelist: string[];
  status: SubagentStatus;
  timeout_seconds: number;
  created_at: string;
  started_at?: string | null;
  ended_at?: string | null;
  result_summary?: string | null;
  error_detail?: string | null;
  kill_reason?: string | null;
  token_usage: number;
  step_count: number;
  input_queue: SubagentInputMessageData[];
  events: SubagentEventItemData[];
}

export interface SubagentLifecycleToolchainCardProps {
  chatId?: string;
  initialTasks?: SubagentTaskItemData[];
  onDismiss?: () => void;
}

export function SubagentLifecycleToolchainCard({
  chatId,
  initialTasks = [],
  onDismiss,
}: SubagentLifecycleToolchainCardProps) {
  const [tasks, setTasks] = useState<SubagentTaskItemData[]>(initialTasks);
  const [isLoading, setIsLoading] = useState(false);
  const [newPrompt, setNewPrompt] = useState('');
  const [newProfile, setNewProfile] = useState('general_worker');
  const [inputMessageMap, setInputMessageMap] = useState<Record<string, string>>({});
  const [expandedTaskId, setExpandedTaskId] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const fetchTasks = useCallback(async () => {
    if (!chatId) {
      return;
    }
    setIsLoading(true);
    try {
      const res = await fetch(`/api/chats/${chatId}/subagents`);
      if (res.ok) {
        const json = await res.json();
        setTasks(json.data.tasks);
      }
    } catch {
      setStatusMessage('获取子任务失败');
    } finally {
      setIsLoading(false);
    }
  }, [chatId]);

  useEffect(() => {
    if (initialTasks.length === 0 && chatId) {
      void fetchTasks();
    }
  }, [chatId, fetchTasks, initialTasks.length]);

  const handleSpawn = async () => {
    if (!chatId || !newPrompt.trim()) {
      return;
    }
    setIsLoading(true);
    setStatusMessage(null);
    try {
      const res = await fetch(`/api/chats/${chatId}/subagents/spawn`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task_prompt: newPrompt.trim(),
          agent_profile: newProfile.trim(),
          tools_whitelist: ['read_file', 'write_file'],
          timeout_seconds: 60.0,
        }),
      });
      if (res.ok) {
        const json = await res.json();
        setTasks((prev) => [json.data, ...prev]);
        setNewPrompt('');
        setStatusMessage(`成功拉起子智能体: ${json.data.subagent_id}`);
      }
    } catch {
      setStatusMessage('派发子智能体异常');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSendInput = async (subagentId: string) => {
    const text = inputMessageMap[subagentId]?.trim();
    if (!chatId || !text) {
      return;
    }
    setIsLoading(true);
    try {
      const res = await fetch(`/api/chats/${chatId}/subagents/${subagentId}/input`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content: text,
          sender_role: 'orchestrator',
        }),
      });
      if (res.ok) {
        setInputMessageMap((prev) => ({ ...prev, [subagentId]: '' }));
        setStatusMessage(`已向 ${subagentId} 注入指导`);
        void fetchTasks();
      }
    } catch {
      setStatusMessage('注入指导失败');
    } finally {
      setIsLoading(false);
    }
  };

  const handleKill = async (subagentId: string) => {
    if (!chatId) {
      return;
    }
    setIsLoading(true);
    try {
      const res = await fetch(`/api/chats/${chatId}/subagents/${subagentId}/kill`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: '用户手动硬熔断' }),
      });
      if (res.ok) {
        setStatusMessage(`子智能体 ${subagentId} 已被熔断终止`);
        void fetchTasks();
      }
    } catch {
      setStatusMessage('熔断操作失败');
    } finally {
      setIsLoading(false);
    }
  };

  const handleWaitAll = async () => {
    if (!chatId || tasks.length === 0) {
      return;
    }
    setIsLoading(true);
    setStatusMessage('等待任务批次执行...');
    try {
      const subagentIds = tasks.map((t) => t.subagent_id);
      const res = await fetch(`/api/chats/${chatId}/subagents/wait`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          subagent_ids: subagentIds,
          timeout_seconds: 5.0,
        }),
      });
      if (res.ok) {
        const json = await res.json();
        setTasks(json.data.tasks);
        setStatusMessage(`批量汇聚完成: 成功 ${json.data.completed_count} / 终止 ${json.data.killed_count}`);
      }
    } catch {
      setStatusMessage('等待子任务批次失败');
    } finally {
      setIsLoading(false);
    }
  };

  const getStatusIcon = (status: SubagentStatus) => {
    switch (status) {
      case 'running':
        return <span className="inline-block h-2 w-2 animate-ping rounded-full bg-emerald-500" />;
      case 'completed':
        return <CheckCircle2 className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />;
      case 'killed':
      case 'failed':
        return <AlertOctagon className="h-4 w-4 text-rose-500" />;
      case 'timeout':
        return <Clock className="h-4 w-4 text-amber-500" />;
      default:
        return <span className="inline-block h-2 w-2 rounded-full bg-gray-400" />;
    }
  };

  return (
    <dialog
      open
      aria-label="Subagent Lifecycle Toolchain"
      className="fixed bottom-6 right-6 z-50 m-0 w-[440px] rounded-xl border border-gray-200 bg-white/95 p-4 shadow-2xl backdrop-blur-md transition-all dark:border-gray-800 dark:bg-gray-900/95"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-100 pb-3 dark:border-gray-800">
        <div className="flex items-center gap-2">
          <Terminal className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
          <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
            原生 Subagent 细粒度生命周期管控
          </h2>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => void fetchTasks()}
            aria-label="刷新任务列表"
            className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800"
          >
            <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
          {onDismiss ? (
            <button
              type="button"
              onClick={onDismiss}
              aria-label="关闭"
              className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800"
            >
              ×
            </button>
          ) : null}
        </div>
      </div>

      {/* Spawn Bar */}
      <div className="mt-3 space-y-2 rounded-lg bg-gray-50 p-2.5 dark:bg-gray-800/60">
        <div className="flex gap-2">
          <input
            type="text"
            value={newPrompt}
            onChange={(e) => setNewPrompt(e.target.value)}
            placeholder="输入任务指令以按需 spawn 子智能体..."
            className="flex-1 rounded border border-gray-200 bg-white px-2 py-1 text-xs outline-none focus:border-indigo-500 dark:border-gray-700 dark:bg-gray-900"
          />
          <input
            type="text"
            value={newProfile}
            onChange={(e) => setNewProfile(e.target.value)}
            placeholder="Profile"
            className="w-24 rounded border border-gray-200 bg-white px-2 py-1 text-xs outline-none focus:border-indigo-500 dark:border-gray-700 dark:bg-gray-900"
          />
          <button
            type="button"
            onClick={() => void handleSpawn()}
            disabled={isLoading || !newPrompt.trim()}
            className="flex items-center gap-1 rounded bg-indigo-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            <Play className="h-3 w-3" />
            <span>Spawn</span>
          </button>
        </div>
      </div>

      {/* Task List */}
      <div className="mt-3 max-h-72 space-y-2 overflow-y-auto pr-1 text-xs">
        {tasks.length === 0 ? (
          <div className="py-6 text-center text-gray-400">
            暂无活跃或历史子智能体任务
          </div>
        ) : (
          tasks.map((task) => {
            const isExpanded = expandedTaskId === task.subagent_id;
            return (
              <div
                key={task.subagent_id}
                className="rounded-lg border border-gray-100 bg-white p-2.5 shadow-sm dark:border-gray-800 dark:bg-gray-800/50"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    {getStatusIcon(task.status)}
                    <span className="font-mono text-[11px] font-semibold text-gray-800 dark:text-gray-200">
                      {task.subagent_id}
                    </span>
                    <span className="rounded bg-indigo-50 px-1.5 py-0.2 text-[10px] text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
                      {task.agent_profile}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] text-gray-400">
                      {task.step_count} 步 / {task.token_usage} Tokens
                    </span>
                    <button
                      type="button"
                      onClick={() => setExpandedTaskId(isExpanded ? null : task.subagent_id)}
                      className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
                    >
                      {isExpanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                    </button>
                  </div>
                </div>

                <div className="mt-1 text-gray-600 dark:text-gray-300">
                  {task.task_prompt}
                </div>

                {task.status === 'running' ? (
                  <div className="mt-2 flex items-center gap-1.5 border-t border-gray-100 pt-2 dark:border-gray-800">
                    <input
                      type="text"
                      value={inputMessageMap[task.subagent_id] ?? ''}
                      onChange={(e) =>
                        setInputMessageMap((prev) => ({
                          ...prev,
                          [task.subagent_id]: e.target.value,
                        }))
                      }
                      placeholder="动态注入纠偏指令..."
                      className="flex-1 rounded border border-gray-200 px-2 py-0.5 text-[11px] dark:border-gray-700 dark:bg-gray-900"
                    />
                    <button
                      type="button"
                      onClick={() => void handleSendInput(task.subagent_id)}
                      disabled={isLoading || !inputMessageMap[task.subagent_id]?.trim()}
                      className="rounded bg-emerald-600 px-2 py-0.5 text-[11px] text-white hover:bg-emerald-700 disabled:opacity-50"
                    >
                      <Send className="h-3 w-3" />
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleKill(task.subagent_id)}
                      disabled={isLoading}
                      className="flex items-center gap-1 rounded bg-rose-600 px-2 py-0.5 text-[11px] text-white hover:bg-rose-700 disabled:opacity-50"
                    >
                      <Square className="h-3 w-3" />
                      <span>Kill</span>
                    </button>
                  </div>
                ) : null}

                {isExpanded ? (
                  <div className="mt-2 space-y-1 rounded bg-gray-50 p-2 text-[10px] text-gray-500 dark:bg-gray-900/60 dark:text-gray-400">
                    {task.result_summary ? (
                      <div>产出摘要: {task.result_summary}</div>
                    ) : null}
                    {task.kill_reason ? (
                      <div className="text-rose-500">终止原因: {task.kill_reason}</div>
                    ) : null}
                    {task.error_detail ? (
                      <div className="text-rose-500">错误详情: {task.error_detail}</div>
                    ) : null}
                    {task.events.length > 0 ? (
                      <div className="mt-1 border-t border-gray-200 pt-1 dark:border-gray-800">
                        <div className="font-semibold text-gray-700 dark:text-gray-300">事件记录:</div>
                        {task.events.map((e) => (
                          <div key={e.event_id} className="font-mono">
                            • [{e.event_type}]
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            );
          })
        )}
      </div>

      {/* Footer Actions */}
      <div className="mt-3 flex items-center justify-between border-t border-gray-100 pt-2 text-xs dark:border-gray-800">
        <button
          type="button"
          onClick={() => void handleWaitAll()}
          disabled={isLoading || tasks.length === 0}
          className="rounded border border-gray-200 px-3 py-1 font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
        >
          Wait All 批量汇聚
        </button>
        {statusMessage ? (
          <span className="truncate text-[11px] text-gray-500 dark:text-gray-400">
            {statusMessage}
          </span>
        ) : null}
      </div>
    </dialog>
  );
}

export default SubagentLifecycleToolchainCard;
