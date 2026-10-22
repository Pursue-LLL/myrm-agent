'use client';

import { useState, useCallback, useEffect } from 'react';
import { Layers, GitMerge, FileCode, CheckCircle2, AlertTriangle, ArrowRight, Download, RefreshCw } from 'lucide-react';

export interface WaveTaskItemData {
  task_id: string;
  stage: string;
  title: string;
  role: string;
  model_override?: string | null;
  status: 'pending' | 'in_progress' | 'completed' | 'failed' | 'blocked';
  output_summary?: string | null;
}

export interface WaveProgressData {
  session_id: string;
  current_stage: string;
  tasks: WaveTaskItemData[];
  is_completed: boolean;
  updated_at: string;
}

export interface WavePresetConfigData {
  preset_id: string;
  name: string;
  description: string;
  role_model_routing: Record<string, string>;
}

export interface CodingWavePresetModalProps {
  chatId?: string;
  initialProgress?: WaveProgressData | null;
  initialPreset?: WavePresetConfigData | null;
  onApplyPreset?: (preset: WavePresetConfigData) => void;
  onDismiss?: () => void;
}

export function CodingWavePresetModal({
  chatId,
  initialProgress = null,
  initialPreset = null,
  onApplyPreset,
  onDismiss,
}: CodingWavePresetModalProps) {
  const [progress, setProgress] = useState<WaveProgressData | null>(initialProgress);
  const [preset, setPreset] = useState<WavePresetConfigData | null>(initialPreset);
  const [isLoading, setIsLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<'pipeline' | 'routing' | 'export'>('pipeline');
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const fetchProgress = useCallback(async () => {
    if (!chatId) {
      return;
    }
    setIsLoading(true);
    try {
      const res = await fetch(`/api/chats/${chatId}/coding-wave/progress`);
      if (res.ok) {
        const json = await res.json();
        setProgress(json.data);
      }
    } catch {
      setStatusMessage('获取波次进度失败');
    } finally {
      setIsLoading(false);
    }
  }, [chatId]);

  const fetchPreset = useCallback(async () => {
    try {
      const res = await fetch('/api/agents/coding-wave/preset');
      if (res.ok) {
        const json = await res.json();
        setPreset(json.data);
      }
    } catch {
      setStatusMessage('获取预置配置失败');
    }
  }, []);

  useEffect(() => {
    if (!initialPreset) {
      void fetchPreset();
    }
  }, [fetchPreset, initialPreset]);

  useEffect(() => {
    if (!initialProgress && chatId) {
      void fetchProgress();
    }
  }, [chatId, fetchProgress, initialProgress]);

  const handleInitSession = async () => {
    if (!chatId) {
      return;
    }
    setIsLoading(true);
    setStatusMessage(null);
    try {
      const res = await fetch(`/api/chats/${chatId}/coding-wave/sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      if (res.ok) {
        const json = await res.json();
        setProgress(json.data);
        setStatusMessage('波次开发流水线已初始化');
      }
    } catch {
      setStatusMessage('初始化流水线异常');
    } finally {
      setIsLoading(false);
    }
  };

  const handleAdvanceStage = async () => {
    if (!chatId) {
      return;
    }
    setIsLoading(true);
    setStatusMessage(null);
    try {
      const res = await fetch(`/api/chats/${chatId}/coding-wave/advance`, {
        method: 'POST',
      });
      if (res.ok) {
        const json = await res.json();
        setProgress(json.data);
        setStatusMessage(`波次阶段已推进至: ${json.data.current_stage}`);
      } else {
        const errJson = await res.json();
        setStatusMessage(`门禁拦截: ${errJson.detail ?? '阶段内仍有未完成任务'}`);
      }
    } catch {
      setStatusMessage('推进阶段异常');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <dialog
      open
      aria-label="Coding Agent Wave Pipeline Modal"
      className="fixed bottom-6 right-6 z-50 m-0 w-[420px] rounded-xl border border-gray-200 bg-white/95 p-4 shadow-2xl backdrop-blur-md transition-all dark:border-gray-800 dark:bg-gray-900/95"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-100 pb-3 dark:border-gray-800">
        <div className="flex items-center gap-2">
          <Layers className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
          <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
            全栈开发 Wave 波次编排
          </h2>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => void fetchProgress()}
            aria-label="刷新进度"
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

      {/* Tabs */}
      <div className="mt-2 flex border-b border-gray-100 text-xs font-medium dark:border-gray-800">
        <button
          type="button"
          onClick={() => setActiveTab('pipeline')}
          className={`flex-1 border-b-2 py-2 text-center transition-colors ${
            activeTab === 'pipeline'
              ? 'border-indigo-600 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400'
              : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400'
          }`}
        >
          波次流水线
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('routing')}
          className={`flex-1 border-b-2 py-2 text-center transition-colors ${
            activeTab === 'routing'
              ? 'border-indigo-600 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400'
              : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400'
          }`}
        >
          三模型角色分工
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('export')}
          className={`flex-1 border-b-2 py-2 text-center transition-colors ${
            activeTab === 'export'
              ? 'border-indigo-600 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400'
              : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400'
          }`}
        >
          进度工件
        </button>
      </div>

      {/* Content */}
      <div className="mt-3 max-h-72 overflow-y-auto pr-1 text-xs">
        {activeTab === 'pipeline' ? (
          <div className="space-y-3">
            {progress ? (
              <div className="space-y-2">
                <div className="flex items-center justify-between rounded-lg bg-indigo-50/60 p-2 text-xs font-medium text-indigo-900 dark:bg-indigo-950/40 dark:text-indigo-300">
                  <span>当前阶段: {progress.current_stage.toUpperCase()}</span>
                  <span className="text-[11px]">
                    {progress.is_completed ? '🎉 全部波次已完成' : '流水线进行中'}
                  </span>
                </div>

                <div className="space-y-1.5">
                  {progress.tasks.map((task) => (
                    <div
                      key={task.task_id}
                      className="flex items-center justify-between rounded-lg border border-gray-100 bg-gray-50/50 p-2 dark:border-gray-800 dark:bg-gray-800/40"
                    >
                      <div className="flex items-center gap-1.5">
                        {task.status === 'completed' ? (
                          <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                        ) : task.status === 'in_progress' ? (
                          <GitMerge className="h-4 w-4 animate-pulse text-indigo-500" />
                        ) : (
                          <AlertTriangle className="h-4 w-4 text-gray-300" />
                        )}
                        <div>
                          <div className="font-medium text-gray-800 dark:text-gray-200">
                            {task.title}
                          </div>
                          <div className="text-[10px] text-gray-400">
                            角色: {task.role} | 模型: {task.model_override ?? '默认'}
                          </div>
                        </div>
                      </div>
                      <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-600 dark:bg-gray-700 dark:text-gray-300">
                        {task.status}
                      </span>
                    </div>
                  ))}
                </div>

                <button
                  type="button"
                  onClick={() => void handleAdvanceStage()}
                  disabled={isLoading || progress.is_completed}
                  className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-indigo-600 py-2 font-medium text-white transition-colors hover:bg-indigo-700 disabled:opacity-50"
                >
                  <ArrowRight className="h-3.5 w-3.5" />
                  <span>门禁核验并推进下一阶段</span>
                </button>
              </div>
            ) : (
              <div className="py-6 text-center text-gray-400">
                <p>当前会话尚未挂载 Wave 波次流水线</p>
                <button
                  type="button"
                  onClick={() => void handleInitSession()}
                  disabled={isLoading}
                  className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700"
                >
                  <FileCode className="h-3.5 w-3.5" />
                  <span>一键启动开发流水线</span>
                </button>
              </div>
            )}
          </div>
        ) : null}

        {activeTab === 'routing' ? (
          <div className="space-y-3">
            <div className="rounded-lg bg-gray-50 p-2.5 dark:bg-gray-800/60">
              <span className="font-medium text-gray-800 dark:text-gray-200">
                云规划 + 本地/MoE 编码多模型协同架构
              </span>
              <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                将顶层架构蓝图规划交给超长上下文大模型，将密集高频编码分派给高速模型，再由对立模型执行代码审查与 QA。
              </p>
            </div>

            {preset ? (
              <div className="space-y-1.5">
                {Object.entries(preset.role_model_routing).map(([role, model]) => (
                  <div
                    key={role}
                    className="flex items-center justify-between rounded-lg border border-gray-100 p-2 dark:border-gray-800"
                  >
                    <span className="font-mono text-gray-700 dark:text-gray-300">{role}</span>
                    <span className="rounded bg-indigo-50 px-2 py-0.5 font-mono text-[11px] text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
                      {model}
                    </span>
                  </div>
                ))}
              </div>
            ) : null}

            {onApplyPreset && preset ? (
              <button
                type="button"
                onClick={() => onApplyPreset(preset)}
                className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-emerald-600 py-2 font-medium text-white transition-colors hover:bg-emerald-700"
              >
                <span>将此多模型路由保存至 Agent Profile</span>
              </button>
            ) : null}
          </div>
        ) : null}

        {activeTab === 'export' ? (
          <div className="space-y-3">
            <p className="text-gray-500 dark:text-gray-400">
              导出结构化 <code className="rounded bg-gray-100 px-1 py-0.5 dark:bg-gray-800">orchestration_progress.json</code>，记录阶段交接与模型产出凭据。
            </p>
            <a
              href={`/api/chats/${chatId}/coding-wave/export-json`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-gray-200 py-2 font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-800"
            >
              <Download className="h-3.5 w-3.5" />
              <span>下载 orchestration_progress.json</span>
            </a>
          </div>
        ) : null}
      </div>

      {statusMessage ? (
        <div className="mt-2 text-center text-[11px] text-gray-500 dark:text-gray-400">
          {statusMessage}
        </div>
      ) : null}
    </dialog>
  );
}

export default CodingWavePresetModal;
