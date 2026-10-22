'use client';

import { useState, useCallback, useEffect } from 'react';
import {
  Cloud,
  HardDrive,
  ArrowRight,
  RefreshCw,
  CheckCircle2,
  AlertCircle,
  FileText,
  Activity,
  Send,
  Wifi,
  WifiOff,
} from 'lucide-react';

export type FleetRole = 'local_brain' | 'remote_executor';
export type FleetExecutionStatus = 'idle' | 'dispatched' | 'executing' | 'completed' | 'failed' | 'offline';

export interface FleetNodeSpecData {
  node_id: string;
  role: FleetRole;
  display_name: string;
  is_online: boolean;
  endpoint_url?: string | null;
  last_heartbeat: string;
  supported_capabilities: string[];
}

export interface MixedFleetHandoffManifestData {
  manifest_id: string;
  chat_id: string;
  source_role: FleetRole;
  target_role: FleetRole;
  task_instruction: string;
  handoff_markdown: string;
  context_files: string[];
  execution_status: FleetExecutionStatus;
  created_at: string;
  synced_at?: string | null;
  output_summary?: string | null;
  error_detail?: string | null;
}

export interface FleetStatusSnapshotData {
  chat_id: string;
  local_brain: FleetNodeSpecData;
  remote_executor: FleetNodeSpecData;
  active_manifest?: MixedFleetHandoffManifestData | null;
  total_handoffs: number;
}

export interface MixedFleetPresetCardProps {
  chatId?: string;
  initialSnapshot?: FleetStatusSnapshotData | null;
  onDismiss?: () => void;
}

export function MixedFleetPresetCard({
  chatId,
  initialSnapshot = null,
  onDismiss,
}: MixedFleetPresetCardProps) {
  const [snapshot, setSnapshot] = useState<FleetStatusSnapshotData | null>(initialSnapshot);
  const [isLoading, setIsLoading] = useState(false);
  const [taskInstruction, setTaskInstruction] = useState('');
  const [contextFilesText, setContextFilesText] = useState('');
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const activeManifest = snapshot?.active_manifest;

  const fetchSnapshot = useCallback(async () => {
    if (!chatId) {
      return;
    }
    setIsLoading(true);
    try {
      const res = await fetch(`/api/chats/${chatId}/mixed-fleet/snapshot`);
      if (res.ok) {
        const json = await res.json();
        setSnapshot(json.data);
      }
    } catch {
      setStatusMessage('获取舰队状态失败');
    } finally {
      setIsLoading(false);
    }
  }, [chatId]);

  useEffect(() => {
    if (!initialSnapshot && chatId) {
      void fetchSnapshot();
    }
  }, [chatId, fetchSnapshot, initialSnapshot]);

  const handleDispatch = async () => {
    if (!chatId || !taskInstruction.trim()) {
      return;
    }
    setIsLoading(true);
    setStatusMessage(null);
    try {
      const files = contextFilesText
        .split(',')
        .map((f) => f.trim())
        .filter(Boolean);

      const res = await fetch(`/api/chats/${chatId}/mixed-fleet/dispatch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task_instruction: taskInstruction.trim(),
          context_files: files,
        }),
      });

      if (res.ok) {
        setTaskInstruction('');
        setContextFilesText('');
        setStatusMessage('任务已成功派发至 24/7 Remote Executor');
        void fetchSnapshot();
      } else {
        const errJson = await res.json();
        setStatusMessage(`派发拦截: ${errJson.detail ?? '远端不可用'}`);
      }
    } catch {
      setStatusMessage('派发任务异常');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSync = async (manifestId: string) => {
    if (!chatId) {
      return;
    }
    setIsLoading(true);
    try {
      const res = await fetch(`/api/chats/${chatId}/mixed-fleet/${manifestId}/sync`, {
        method: 'POST',
      });
      if (res.ok) {
        setStatusMessage('已同步最新工件进展');
        void fetchSnapshot();
      }
    } catch {
      setStatusMessage('同步失败');
    } finally {
      setIsLoading(false);
    }
  };

  const handleToggleRemoteOnline = async () => {
    if (!chatId || !snapshot) {
      return;
    }
    setIsLoading(true);
    try {
      const nextOnline = !snapshot.remote_executor.is_online;
      const res = await fetch(`/api/chats/${chatId}/mixed-fleet/heartbeat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          role: 'remote_executor',
          is_online: nextOnline,
        }),
      });
      if (res.ok) {
        setStatusMessage(nextOnline ? 'Remote Executor 已恢复在线' : 'Remote Executor 已切为离线');
        void fetchSnapshot();
      }
    } catch {
      setStatusMessage('更新心跳状态异常');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSimulateComplete = async (manifestId: string) => {
    if (!chatId) {
      return;
    }
    setIsLoading(true);
    try {
      const res = await fetch(`/api/chats/${chatId}/mixed-fleet/${manifestId}/complete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          output_summary: '24/7 远端沙箱运行完成，生成结构化分析工件',
        }),
      });
      if (res.ok) {
        setStatusMessage('远端执行器已提交完成工件');
        void fetchSnapshot();
      }
    } catch {
      setStatusMessage('模拟完成失败');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <dialog
      open
      aria-label="Mixed Fleet Orchestration Card"
      className="fixed bottom-6 right-6 z-50 m-0 w-[440px] rounded-xl border border-gray-200 bg-white/95 p-4 shadow-2xl backdrop-blur-md transition-all dark:border-gray-800 dark:bg-gray-900/95"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-100 pb-3 dark:border-gray-800">
        <div className="flex items-center gap-2">
          <Activity className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
          <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
            混合舰队 (Local Brain + Remote Executor)
          </h2>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => void fetchSnapshot()}
            aria-label="刷新舰队状态"
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

      {/* Nodes Topology */}
      {snapshot ? (
        <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
          <div className="rounded-lg border border-indigo-100 bg-indigo-50/50 p-2.5 dark:border-indigo-900/40 dark:bg-indigo-950/30">
            <div className="flex items-center gap-1.5 font-semibold text-indigo-900 dark:text-indigo-200">
              <HardDrive className="h-4 w-4 text-indigo-600 dark:text-indigo-400" />
              <span>Local Brain</span>
            </div>
            <div className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
              {snapshot.local_brain.display_name}
            </div>
            <div className="mt-1.5 flex items-center gap-1 text-[10px] text-emerald-600 dark:text-emerald-400">
              <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-500" />
              <span>常驻本地 (隐私受控)</span>
            </div>
          </div>

          <div className="rounded-lg border border-purple-100 bg-purple-50/50 p-2.5 dark:border-purple-900/40 dark:bg-purple-950/30">
            <div className="flex items-center justify-between font-semibold text-purple-900 dark:text-purple-200">
              <div className="flex items-center gap-1.5">
                <Cloud className="h-4 w-4 text-purple-600 dark:text-purple-400" />
                <span>Remote Executor</span>
              </div>
              <button
                type="button"
                onClick={() => void handleToggleRemoteOnline()}
                title="切换在线状态"
                className="text-gray-400 hover:text-purple-600 dark:hover:text-purple-300"
              >
                {snapshot.remote_executor.is_online ? (
                  <Wifi className="h-3.5 w-3.5 text-emerald-500" />
                ) : (
                  <WifiOff className="h-3.5 w-3.5 text-rose-500" />
                )}
              </button>
            </div>
            <div className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
              {snapshot.remote_executor.display_name}
            </div>
            <div className="mt-1.5 flex items-center gap-1 text-[10px]">
              {snapshot.remote_executor.is_online ? (
                <span className="text-emerald-600 dark:text-emerald-400">● 24/7 云端沙箱就绪</span>
              ) : (
                <span className="text-rose-500">○ 节点离线中</span>
              )}
            </div>
          </div>
        </div>
      ) : null}

      {/* Dispatch Panel */}
      <div className="mt-3 space-y-2 rounded-lg bg-gray-50 p-2.5 dark:bg-gray-800/60 text-xs">
        <div className="font-medium text-gray-800 dark:text-gray-200">
          Local Brain 派发长耗时任务至 Remote Executor
        </div>
        <textarea
          rows={2}
          value={taskInstruction}
          onChange={(e) => setTaskInstruction(e.target.value)}
          placeholder="输入需要远端 24/7 不间断执行的长耗时任务..."
          className="w-full rounded border border-gray-200 bg-white p-2 text-xs outline-none focus:border-indigo-500 dark:border-gray-700 dark:bg-gray-900"
        />
        <div className="flex gap-2">
          <input
            type="text"
            value={contextFilesText}
            onChange={(e) => setContextFilesText(e.target.value)}
            placeholder="附加本地上下文文件 (逗号分隔)"
            className="flex-1 rounded border border-gray-200 bg-white px-2 py-1 text-[11px] outline-none focus:border-indigo-500 dark:border-gray-700 dark:bg-gray-900"
          />
          <button
            type="button"
            onClick={() => void handleDispatch()}
            disabled={isLoading || !taskInstruction.trim()}
            className="flex items-center gap-1 rounded bg-indigo-600 px-3 py-1 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            <Send className="h-3 w-3" />
            <span>派发</span>
          </button>
        </div>
      </div>

      {/* Active Manifest Section */}
      <div className="mt-3 max-h-56 space-y-2 overflow-y-auto pr-1 text-xs">
        {activeManifest ? (
          <div className="rounded-lg border border-gray-100 bg-white p-2.5 shadow-sm dark:border-gray-800 dark:bg-gray-800/50">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 font-mono text-[11px] font-semibold text-gray-800 dark:text-gray-200">
                <FileText className="h-3.5 w-3.5 text-indigo-500" />
                <span>{activeManifest.manifest_id}</span>
              </div>
              <span className="rounded bg-indigo-50 px-1.5 py-0.5 text-[10px] text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
                {activeManifest.execution_status}
              </span>
            </div>

            <div className="mt-1 text-gray-600 dark:text-gray-300">
              {activeManifest.task_instruction}
            </div>

            {activeManifest.output_summary ? (
              <div className="mt-2 rounded bg-emerald-50/70 p-2 text-[11px] text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300">
                <div className="font-semibold">产出工件摘要:</div>
                <div>{activeManifest.output_summary}</div>
              </div>
            ) : null}

            <div className="mt-2 flex items-center justify-between border-t border-gray-100 pt-2 text-[10px] text-gray-400 dark:border-gray-800">
              <span>交接总数: {snapshot?.total_handoffs ?? 0}</span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => void handleSync(activeManifest.manifest_id)}
                  disabled={isLoading}
                  className="text-indigo-600 hover:underline dark:text-indigo-400"
                >
                  拉取同步
                </button>
                {activeManifest.execution_status === 'dispatched' ? (
                  <button
                    type="button"
                    onClick={() => void handleSimulateComplete(activeManifest.manifest_id)}
                    disabled={isLoading}
                    className="text-emerald-600 hover:underline dark:text-emerald-400"
                  >
                    演练完成
                  </button>
                ) : null}
              </div>
            </div>
          </div>
        ) : (
          <div className="py-4 text-center text-gray-400">
            当前会话暂无派发中的混合交接任务
          </div>
        )}
      </div>

      {/* Footer */}
      {statusMessage ? (
        <div className="mt-2 border-t border-gray-100 pt-2 text-center text-[11px] text-gray-500 dark:border-gray-800 dark:text-gray-400">
          {statusMessage}
        </div>
      ) : null}
    </dialog>
  );
}

export default MixedFleetPresetCard;
