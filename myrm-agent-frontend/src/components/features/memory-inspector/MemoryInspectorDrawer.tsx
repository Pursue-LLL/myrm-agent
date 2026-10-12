/**
 * Memory Inspector & Epistemic Veracity Governance Drawer.
 *
 * [INPUT] MemoryInspectorDrawerProps (isOpen, onClose, memories, sessionId, callbacks)
 * [OUTPUT] JSX.Element - Interactive slide-over drawer for memory explanation and governance
 * [POS] Item 30 main inspector drawer. Strictly under 380 lines. Zero `any`.
 */

import React, { useState } from 'react';
import {
  Brain,
  X,
  Sparkles,
  Edit3,
  Trash2,
  Check,
  RotateCcw,
  Clock,
  Layers,
  ArrowUpRight,
  TrendingUp,
} from 'lucide-react';
import type { EpistemicMemoryItem, MemoryInspectorDrawerProps } from './memoryInspectorTypes';
import { EpistemicBadge } from './EpistemicBadge';

export const MemoryInspectorDrawer: React.FC<MemoryInspectorDrawerProps> = ({
  isOpen,
  onClose,
  memories,
  sessionId,
  onPromote,
  onCorrect,
  onForget,
  className = '',
}) => {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!isOpen) {
    return null;
  }

  const handleStartEdit = (item: EpistemicMemoryItem) => {
    setEditingId(item.id);
    setEditText(item.content);
  };

  const handleCancelEdit = () => {
    setEditingId(null);
    setEditText('');
  };

  const handleSaveEdit = async (memoryId: string) => {
    if (!onCorrect || !editText.trim()) {
      return;
    }
    setIsSubmitting(true);
    try {
      await onCorrect(memoryId, editText.trim());
      setEditingId(null);
      setEditText('');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handlePromote = async (memoryId: string) => {
    if (!onPromote) {
      return;
    }
    setIsSubmitting(true);
    try {
      await onPromote(memoryId, 'assertion');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleForget = async (memoryId: string) => {
    if (!onForget) {
      return;
    }
    setIsSubmitting(true);
    try {
      await onForget(memoryId);
    } finally {
      setIsSubmitting(false);
    }
  };

  const assertionCount = memories.filter((m) => m.epistemic_tier === 'assertion').length;
  const observationCount = memories.filter((m) => m.epistemic_tier === 'observation').length;
  const beliefCount = memories.filter((m) => m.epistemic_tier === 'belief').length;

  return (
    <dialog
      open
      aria-modal="true"
      aria-label="记忆透视与认识论治理抽屉"
      className="fixed inset-0 z-50 overflow-hidden bg-black/40 backdrop-blur-xs flex justify-end animate-in fade-in duration-200 border-none m-0 p-0 w-full h-full max-w-none max-h-none"
    >
      <aside
        aria-label="记忆透视与治理侧边抽屉"
        className={`w-full max-w-lg bg-white dark:bg-slate-900 border-l border-slate-200 dark:border-slate-800 shadow-2xl flex flex-col h-full animate-in slide-in-from-right duration-200 ${className}`}
      >
        {/* 抽屉头部 */}
        <header className="p-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="p-2 rounded-xl bg-violet-500/10 text-violet-600 dark:text-violet-400">
              <Brain className="w-5 h-5" />
            </div>
            <div className="min-w-0">
              <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 truncate">
                记忆透视镜与治理抽屉
              </h3>
              <p className="text-xs text-slate-500 dark:text-slate-400 truncate">
                会话: <span className="font-mono">{sessionId || '当前会话'}</span>
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            aria-label="关闭透视抽屉"
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </header>

        {/* 认识论等级分布卡片 */}
        <div className="px-4 py-3 bg-slate-50/70 dark:bg-slate-950/40 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between text-xs">
          <span className="text-slate-500 dark:text-slate-400 font-medium">
            共引用 {memories.length} 条长程记忆
          </span>
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
              <span className="w-2 h-2 rounded-full bg-emerald-500" />
              断言 {assertionCount}
            </span>
            <span className="inline-flex items-center gap-1 text-sky-600 dark:text-sky-400">
              <span className="w-2 h-2 rounded-full bg-sky-500" />
              观察 {observationCount}
            </span>
            <span className="inline-flex items-center gap-1 text-amber-600 dark:text-amber-400">
              <span className="w-2 h-2 rounded-full bg-amber-500" />
              信念 {beliefCount}
            </span>
          </div>
        </div>

        {/* 记忆条目列表 */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3.5">
          {memories.length === 0 ? (
            <div className="py-12 text-center text-slate-400 dark:text-slate-500 text-xs">
              当前会话未引用任何长程记忆
            </div>
          ) : (
            memories.map((item) => (
              <article
                key={item.id}
                className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/80 p-3.5 shadow-2xs space-y-2.5 transition-all hover:border-slate-300 dark:hover:border-slate-700"
              >
                {/* 条目顶栏：徽章与相似度 */}
                <div className="flex items-center justify-between gap-2">
                  <EpistemicBadge tier={item.epistemic_tier} confidenceScore={item.confidence_score} />
                  <div className="flex items-center gap-1.5 text-xs text-slate-500 font-mono">
                    <TrendingUp className="w-3.5 h-3.5 text-slate-400" />
                    <span>相似度 {Math.round(item.similarity_score * 100)}%</span>
                  </div>
                </div>

                {/* 文本内容与就地编辑模式 */}
                {editingId === item.id ? (
                  <div className="space-y-2">
                    <textarea
                      value={editText}
                      onChange={(e) => setEditText(e.target.value)}
                      rows={3}
                      className="w-full text-xs p-2.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-950 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-violet-500"
                    />
                    <div className="flex justify-end gap-2">
                      <button
                        type="button"
                        onClick={handleCancelEdit}
                        className="px-2.5 py-1 text-xs rounded border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800"
                      >
                        取消
                      </button>
                      <button
                        type="button"
                        disabled={isSubmitting}
                        onClick={() => handleSaveEdit(item.id)}
                        className="inline-flex items-center gap-1 px-2.5 py-1 text-xs rounded bg-violet-600 text-white hover:bg-violet-700 disabled:opacity-50"
                      >
                        <Check className="w-3 h-3" />
                        保存修正
                      </button>
                    </div>
                  </div>
                ) : (
                  <p className="text-xs text-slate-800 dark:text-slate-200 leading-relaxed font-sans">
                    {item.content}
                  </p>
                )}

                {/* 证据溯源链条 */}
                {item.provenance_chain.length > 0 && (
                  <div className="pt-2 border-t border-slate-100 dark:border-slate-800/80 text-[11px] text-slate-500 space-y-1">
                    <span className="font-semibold text-slate-400 block uppercase tracking-wider text-[10px]">
                      证据溯源
                    </span>
                    <ul className="space-y-0.5">
                      {item.provenance_chain.map((prov, i) => (
                        <li key={i} className="flex items-center gap-1 font-mono truncate">
                          <Layers className="w-3 h-3 shrink-0 opacity-60" />
                          <span className="truncate">{prov}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* 元数据指标 */}
                <div className="flex items-center gap-3 pt-1 text-[11px] text-slate-400 font-mono">
                  <span className="inline-flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    召回 {item.hit_count} 次
                  </span>
                  {item.source_session_id && (
                    <span className="truncate max-w-[140px]">源: {item.source_session_id}</span>
                  )}
                </div>

                {/* 三大治理操作工具栏 */}
                <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100 dark:border-slate-800">
                  {item.epistemic_tier === 'belief' && onPromote && (
                    <button
                      type="button"
                      disabled={isSubmitting}
                      onClick={() => handlePromote(item.id)}
                      className="inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/40 hover:bg-emerald-100 dark:hover:bg-emerald-900/60 transition-colors disabled:opacity-50"
                    >
                      <ArrowUpRight className="w-3 h-3" />
                      升格为事实
                    </button>
                  )}

                  {editingId !== item.id && onCorrect && (
                    <button
                      type="button"
                      disabled={isSubmitting}
                      onClick={() => handleStartEdit(item)}
                      className="inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                    >
                      <Edit3 className="w-3 h-3" />
                      就地纠偏
                    </button>
                  )}

                  {onForget && (
                    <button
                      type="button"
                      disabled={isSubmitting}
                      onClick={() => handleForget(item.id)}
                      className="inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/40 transition-colors disabled:opacity-50"
                    >
                      <Trash2 className="w-3 h-3" />
                      物理遗忘
                    </button>
                  )}
                </div>
              </article>
            ))
          )}
        </div>
      </aside>
    </dialog>
  );
};
