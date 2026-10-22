'use client';

import { useState, useCallback, useEffect } from 'react';
import { Eye, ShieldCheck, Activity, RefreshCw, Zap, Trash2 } from 'lucide-react';

export interface BotFocusSnapshotData {
  bot_id: string;
  is_viewport_active: boolean;
  last_active_turn: number;
  focus_score: number;
  updated_at: string;
}

export interface CompactionEvaluationData {
  should_compact: boolean;
  reason: string;
  current_tokens: number;
  max_context_tokens: number;
  cooldown_remaining: number;
  evaluated_at: string;
}

export interface MultiBotFocusIndicatorProps {
  chatId: string;
  initialSnapshots?: BotFocusSnapshotData[];
  initialFocusedBotId?: string | null;
  onMentionSelect?: (botId: string) => void;
  onDismiss?: () => void;
}

export function MultiBotFocusIndicator({
  chatId,
  initialSnapshots = [],
  initialFocusedBotId = null,
  onMentionSelect,
  onDismiss,
}: MultiBotFocusIndicatorProps) {
  const [snapshots, setSnapshots] = useState<BotFocusSnapshotData[]>(initialSnapshots);
  const [focusedBotId, setFocusedBotId] = useState<string | null>(initialFocusedBotId);
  const [evaluation, setEvaluation] = useState<CompactionEvaluationData | null>(null);
  const [activeTab, setActiveTab] = useState<'focus' | 'compaction' | 'streams'>('focus');
  const [isLoading, setIsLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const fetchFocusState = useCallback(async () => {
    if (!chatId) {
      return;
    }
    setIsLoading(true);
    try {
      const res = await fetch(`/api/chats/${chatId}/multi-bot/focus`);
      if (res.ok) {
        const json = await res.json();
        if (json.data) {
          setFocusedBotId(json.data.focused_bot_id ?? null);
          setSnapshots(json.data.snapshots ?? []);
        }
      }
    } catch {
      setStatusMessage('获取Bot焦点状态失败');
    } finally {
      setIsLoading(false);
    }
  }, [chatId]);

  useEffect(() => {
    if (initialSnapshots.length === 0) {
      void fetchFocusState();
    }
  }, [fetchFocusState, initialSnapshots.length]);

  const handleEvaluateCompaction = async () => {
    setIsLoading(true);
    setStatusMessage(null);
    try {
      const res = await fetch(`/api/chats/${chatId}/multi-bot/compaction/evaluate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          current_tokens: 9200,
          max_context_tokens: 10000,
          current_turn: 5,
        }),
      });
      if (res.ok) {
        const json = await res.json();
        setEvaluation(json.data);
      } else {
        setStatusMessage('压实评估请求失败');
      }
    } catch {
      setStatusMessage('网络异常');
    } finally {
      setIsLoading(false);
    }
  };

  const handlePruneStreams = async () => {
    setIsLoading(true);
    setStatusMessage(null);
    try {
      const res = await fetch(`/api/chats/${chatId}/multi-bot/streams/prune`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ timeout_seconds: 30.0 }),
      });
      if (res.ok) {
        const json = await res.json();
        setStatusMessage(`已清理 ${json.data.count ?? 0} 个僵尸流卡片`);
      }
    } catch {
      setStatusMessage('清理异常');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <dialog
      open
      aria-label="Multi-Bot Focus & Compaction Guard"
      className="fixed bottom-6 right-6 z-50 w-96 rounded-xl border border-gray-200 bg-white/95 p-4 shadow-2xl backdrop-blur-md transition-all dark:border-gray-800 dark:bg-gray-900/95 m-0"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-100 pb-3 dark:border-gray-800">
        <div className="flex items-center gap-2">
          <Eye className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
          <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
            多Bot焦点与防抖压实
          </h2>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => void fetchFocusState()}
            aria-label="刷新"
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
          onClick={() => setActiveTab('focus')}
          className={`flex-1 border-b-2 py-2 text-center transition-colors ${
            activeTab === 'focus'
              ? 'border-indigo-600 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400'
              : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400'
          }`}
        >
          Mention焦点
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('compaction')}
          className={`flex-1 border-b-2 py-2 text-center transition-colors ${
            activeTab === 'compaction'
              ? 'border-indigo-600 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400'
              : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400'
          }`}
        >
          防抖压实
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('streams')}
          className={`flex-1 border-b-2 py-2 text-center transition-colors ${
            activeTab === 'streams'
              ? 'border-indigo-600 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400'
              : 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400'
          }`}
        >
          流式卫士
        </button>
      </div>

      {/* Content */}
      <div className="mt-3 max-h-72 overflow-y-auto pr-1">
        {activeTab === 'focus' ? (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
              <span>当前推荐焦点:</span>
              <span className="font-semibold text-indigo-600 dark:text-indigo-400">
                {focusedBotId ? `@${focusedBotId}` : '无活跃注视'}
              </span>
            </div>
            {snapshots.length === 0 ? (
              <p className="py-6 text-center text-xs text-gray-400">暂无追踪的Bot视口记录</p>
            ) : (
              snapshots.map((snap) => {
                const isSelected = snap.bot_id === focusedBotId;
                return (
                  <div
                    key={snap.bot_id}
                    className={`flex items-center justify-between rounded-lg border p-2 text-xs transition-colors ${
                      isSelected
                        ? 'border-indigo-300 bg-indigo-50/50 dark:border-indigo-700 dark:bg-indigo-950/30'
                        : 'border-gray-100 bg-gray-50/60 dark:border-gray-800 dark:bg-gray-800/40'
                    }`}
                  >
                    <div>
                      <div className="flex items-center gap-1.5 font-medium text-gray-800 dark:text-gray-200">
                        <span>@{snap.bot_id}</span>
                        {snap.is_viewport_active ? (
                          <span className="rounded bg-emerald-100 px-1 py-0.5 text-[10px] text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400">
                            视口内
                          </span>
                        ) : null}
                      </div>
                      <span className="text-[10px] text-gray-400">
                        轮次: T{snap.last_active_turn} | 得分: {snap.focus_score.toFixed(1)}
                      </span>
                    </div>
                    {onMentionSelect ? (
                      <button
                        type="button"
                        onClick={() => onMentionSelect(snap.bot_id)}
                        className="rounded bg-indigo-600 px-2 py-1 text-[11px] text-white hover:bg-indigo-700"
                      >
                        提及
                      </button>
                    ) : null}
                  </div>
                );
              })
            )}
          </div>
        ) : null}

        {activeTab === 'compaction' ? (
          <div className="space-y-3 text-xs">
            <div className="rounded-lg bg-gray-50 p-2.5 dark:bg-gray-800/60">
              <div className="flex items-center gap-1.5 font-medium text-gray-700 dark:text-gray-300">
                <ShieldCheck className="h-4 w-4 text-emerald-600" />
                <span>防抖迟滞门禁规则</span>
              </div>
              <ul className="mt-1.5 list-inside list-disc space-y-0.5 text-[11px] text-gray-500 dark:text-gray-400">
                <li>高水位触发门槛: 90% Context Window</li>
                <li>防抖冷却周期: 3 Turns 最小间隔</li>
                <li>最小 Token 增量: 500 Tokens 阻断抖动</li>
              </ul>
            </div>

            {evaluation ? (
              <div
                className={`rounded-lg border p-2.5 ${
                  evaluation.should_compact
                    ? 'border-amber-300 bg-amber-50/60 dark:border-amber-700 dark:bg-amber-950/30'
                    : 'border-emerald-300 bg-emerald-50/60 dark:border-emerald-700 dark:bg-emerald-950/30'
                }`}
              >
                <div className="flex items-center gap-1.5 font-semibold">
                  <Activity className="h-4 w-4" />
                  <span>
                    {evaluation.should_compact ? '建议执行上下文压实' : '保持当前上下文 (防抖生效)'}
                  </span>
                </div>
                <p className="mt-1 text-[11px] text-gray-600 dark:text-gray-300">
                  {evaluation.reason}
                </p>
                {evaluation.cooldown_remaining > 0 ? (
                  <span className="mt-1 inline-block text-[10px] text-amber-600 dark:text-amber-400">
                    冷却剩余: {evaluation.cooldown_remaining} 轮
                  </span>
                ) : null}
              </div>
            ) : null}

            <button
              type="button"
              onClick={() => void handleEvaluateCompaction()}
              disabled={isLoading}
              className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-indigo-600 py-2 font-medium text-white transition-colors hover:bg-indigo-700 disabled:opacity-50"
            >
              <Zap className="h-3.5 w-3.5" />
              <span>运行防抖压实评估</span>
            </button>
          </div>
        ) : null}

        {activeTab === 'streams' ? (
          <div className="space-y-3 text-xs">
            <p className="text-gray-500 dark:text-gray-400">
              监控多Bot并发流式任务卡片，心跳超时（默认30秒）无响应时自动标记为废弃（Abandoned），彻底杜绝僵尸加载条。
            </p>
            <button
              type="button"
              onClick={() => void handlePruneStreams()}
              disabled={isLoading}
              className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-red-200 bg-red-50 py-2 font-medium text-red-600 transition-colors hover:bg-red-100 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-400"
            >
              <Trash2 className="h-3.5 w-3.5" />
              <span>扫描并清理超时僵尸流</span>
            </button>
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

export default MultiBotFocusIndicator;
