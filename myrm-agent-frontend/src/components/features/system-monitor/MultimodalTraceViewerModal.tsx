/**
 * [INPUT]: MultimodalTraceViewerModalProps with trace records and pin actions.
 * [OUTPUT]: MultimodalTraceViewerModal React component for in-place 3-step inspection and decoupled media preview.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/MultimodalTraceViewerModal.tsx
 */

import React, { useState } from 'react';
import {
  MediaModalityType,
  MediaReferenceItem,
  MediaVisibilityStateType,
  MultimodalStepKind,
  MultimodalTraceRecordItem,
  MultimodalTraceStepItem,
  MultimodalTraceViewerModalProps,
} from './multimodalTraceTypes';

export const MultimodalTraceViewerModal: React.FC<MultimodalTraceViewerModalProps> = ({
  isOpen,
  onClose,
  traces,
  selectedTraceId,
  onSelectTrace,
  onPinGoldenEval,
  onRefresh,
  isRefreshing = false,
}) => {
  const [activeTraceId, setActiveTraceId] = useState<string>(
    selectedTraceId || (traces.length > 0 ? traces[0].trace_id : '')
  );
  const [isPinning, setIsPinning] = useState<boolean>(false);
  const [zoomImageUrl, setZoomImageUrl] = useState<string | null>(null);

  if (!isOpen) return null;

  const currentTrace = traces.find((t) => t.trace_id === activeTraceId) || traces[0];

  const handleSelect = (id: string) => {
    setActiveTraceId(id);
    if (onSelectTrace) {
      onSelectTrace(id);
    }
  };

  const handlePin = async () => {
    if (!currentTrace || !onPinGoldenEval || isPinning) return;
    try {
      setIsPinning(true);
      await onPinGoldenEval(currentTrace.trace_id, 'visual_regression');
    } finally {
      setIsPinning(false);
    }
  };

  const getModalityBadge = (modality: MediaModalityType) => {
    switch (modality) {
      case 'image':
        return { label: '📷 图片', cls: 'border-sky-500/40 bg-sky-500/10 text-sky-300' };
      case 'audio':
        return { label: '🎙️ 音频', cls: 'border-amber-500/40 bg-amber-500/10 text-amber-300' };
      case 'video':
        return { label: '🎥 视频', cls: 'border-purple-500/40 bg-purple-500/10 text-purple-300' };
      case 'document':
      default:
        return { label: '📄 文档', cls: 'border-zinc-500/40 bg-zinc-500/10 text-zinc-300' };
    }
  };

  const getVisibilityBadge = (state: MediaVisibilityStateType) => {
    switch (state) {
      case 'ready':
        return { text: '● 可预览 (Ready)', cls: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30' };
      case 'uploading':
        return { text: '○ 上传中 (Uploading)', cls: 'text-amber-400 bg-amber-500/10 border-amber-500/30' };
      case 'expired':
        return { text: '✕ 签名过期 (Expired)', cls: 'text-rose-400 bg-rose-500/10 border-rose-500/30' };
      case 'purged':
      default:
        return { text: '— TTL已归档 (Purged)', cls: 'text-zinc-500 bg-zinc-800/40 border-zinc-700/30' };
    }
  };

  const getStepBadge = (stepKind: MultimodalStepKind) => {
    switch (stepKind) {
      case 'input':
        return { title: '① 输入 (Input)', cls: 'border-sky-500/30 bg-sky-500/10 text-sky-400' };
      case 'execution':
        return { title: '② 执行 (Execution)', cls: 'border-amber-500/30 bg-amber-500/10 text-amber-400' };
      case 'feedback':
      default:
        return { title: '③ 反馈 (Feedback)', cls: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400' };
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm">
      <div className="flex h-[90vh] w-full max-w-6xl flex-col rounded-2xl border border-zinc-800 bg-zinc-950 text-zinc-100 shadow-2xl">
        {/* 顶部标题栏 */}
        <div className="flex items-center justify-between border-b border-zinc-800 px-6 py-4">
          <div className="flex items-center space-x-3">
            <span className="text-lg font-bold tracking-tight text-white">
              多模态 Trace 原位三步排查与媒体引用解耦大盘
            </span>
            <span className="rounded-full border border-sky-500/40 bg-sky-500/10 px-2.5 py-0.5 text-xs text-sky-300">
              OTel GenAI 规范对齐
            </span>
          </div>
          <div className="flex items-center space-x-3">
            {onRefresh && (
              <button
                onClick={onRefresh}
                disabled={isRefreshing}
                className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
              >
                {isRefreshing ? '刷新中...' : '刷新'}
              </button>
            )}
            <button
              onClick={onClose}
              className="rounded-lg p-1.5 text-zinc-400 hover:bg-zinc-800 hover:text-white"
              aria-label="关闭窗口"
            >
              ✕
            </button>
          </div>
        </div>

        {/* 主体两栏布局 */}
        <div className="flex flex-1 overflow-hidden">
          {/* 左侧 Trace 导航栏 */}
          <div className="w-80 border-r border-zinc-800 bg-zinc-950/60 p-4 overflow-y-auto space-y-2">
            <div className="mb-2 text-xs font-medium text-zinc-400">调用链列表 ({traces.length})</div>
            {traces.length === 0 ? (
              <div className="py-8 text-center text-xs text-zinc-500">暂无多模态 Trace 记录</div>
            ) : (
              traces.map((t) => {
                const isActive = t.trace_id === (currentTrace ? currentTrace.trace_id : '');
                return (
                  <button
                    key={t.trace_id}
                    onClick={() => handleSelect(t.trace_id)}
                    className={`w-full text-left rounded-lg p-3 transition border text-xs ${
                      isActive
                        ? 'border-sky-500/50 bg-sky-950/20 text-white'
                        : 'border-zinc-800/80 bg-zinc-900/40 text-zinc-300 hover:bg-zinc-800/60'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono font-medium truncate max-w-[140px]">{t.trace_id}</span>
                      {t.pinned_for_golden_eval && (
                        <span className="rounded bg-amber-500/20 text-amber-300 px-1 py-0.2 text-[10px]">
                          ★ Golden Eval
                        </span>
                      )}
                    </div>
                    <div className="mt-1 text-zinc-400 truncate">{t.prompt_summary}</div>
                    <div className="mt-2 flex items-center space-x-1.5">
                      {t.media_references.map((m) => {
                        const badge = getModalityBadge(m.modality);
                        return (
                          <span
                            key={m.media_id}
                            className={`rounded border px-1.5 py-0.5 text-[10px] ${badge.cls}`}
                          >
                            {badge.label}
                          </span>
                        );
                      })}
                    </div>
                  </button>
                );
              })
            )}
          </div>

          {/* 右侧 Trace 详情与三步排查看板 */}
          {currentTrace ? (
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {/* 头部元数据 & 加星锁控制 */}
              <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-zinc-800 bg-zinc-900/40 p-4">
                <div>
                  <div className="flex items-center space-x-2">
                    <span className="font-mono text-sm font-bold text-white">{currentTrace.trace_id}</span>
                    <span className="text-xs text-zinc-400 font-mono">({currentTrace.session_id})</span>
                  </div>
                  <p className="mt-1 text-xs text-zinc-300">{currentTrace.prompt_summary}</p>
                </div>
                <div>
                  <button
                    onClick={() => {
                      void handlePin();
                    }}
                    disabled={currentTrace.pinned_for_golden_eval || isPinning}
                    className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                      currentTrace.pinned_for_golden_eval
                        ? 'border border-amber-500/40 bg-amber-500/10 text-amber-300 cursor-default'
                        : 'border border-zinc-700 bg-zinc-800 text-zinc-200 hover:bg-zinc-700'
                    }`}
                  >
                    {currentTrace.pinned_for_golden_eval
                      ? `★ 已沉淀为黄金评测样本 (${currentTrace.golden_eval_category || 'visual_regression'})`
                      : '☆ 沉淀为黄金评测样本 (Pin to Golden Eval)'}
                  </button>
                </div>
              </div>

              {/* 媒体引用与原位临时签名预览 */}
              <div className="space-y-3">
                <h4 className="text-xs font-semibold text-zinc-300 tracking-wide uppercase">
                  解耦媒体引用与原位预览 (Decoupled Media References)
                </h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {currentTrace.media_references.length === 0 ? (
                    <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-4 text-xs text-zinc-500">
                      本调用链未关联独立媒体引用
                    </div>
                  ) : (
                    currentTrace.media_references.map((media: MediaReferenceItem) => {
                      const visBadge = getVisibilityBadge(media.visibility_state);
                      const modBadge = getModalityBadge(media.modality);
                      return (
                        <div
                          key={media.media_id}
                          className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 flex flex-col justify-between space-y-3"
                        >
                          <div>
                            <div className="flex items-center justify-between">
                              <span className={`rounded border px-2 py-0.5 text-xs ${modBadge.cls}`}>
                                {modBadge.label}
                              </span>
                              <span className={`rounded-full border px-2 py-0.5 text-[10px] ${visBadge.cls}`}>
                                {visBadge.text}
                              </span>
                            </div>
                            <div className="mt-2 text-xs font-mono text-zinc-300 truncate">{media.uri}</div>
                            <div className="mt-1 text-[11px] text-zinc-500">
                              大小: {(media.file_size_bytes / 1024).toFixed(1)} KB | SHA256: {media.sha256_hash.slice(0, 12)}...
                            </div>
                          </div>

                          {/* 原位预览容器 */}
                          {media.presigned_preview_url && media.visibility_state === 'ready' && (
                            <div className="relative rounded-lg border border-zinc-800 bg-black/60 p-2 overflow-hidden flex items-center justify-center max-h-48">
                              {media.modality === 'image' && (
                                <img
                                  src={media.presigned_preview_url}
                                  alt={media.media_id}
                                  onClick={() => setZoomImageUrl(media.presigned_preview_url)}
                                  className="max-h-44 object-contain rounded cursor-pointer hover:opacity-90"
                                />
                              )}
                              {media.modality === 'audio' && (
                                <audio controls src={media.presigned_preview_url} className="w-full" />
                              )}
                              {media.modality === 'video' && (
                                <video controls src={media.presigned_preview_url} className="max-h-44 rounded" />
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })
                  )}
                </div>
              </div>

              {/* 三步排查时间线看板 */}
              <div className="space-y-3">
                <h4 className="text-xs font-semibold text-zinc-300 tracking-wide uppercase">
                  三步排查诊断看板 (Input ➔ Execution ➔ Feedback 3-Step Inspector)
                </h4>
                <div className="space-y-3">
                  {currentTrace.steps.length === 0 ? (
                    <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-4 text-xs text-zinc-500">
                      暂无三步排查阶段数据
                    </div>
                  ) : (
                    currentTrace.steps.map((step: MultimodalTraceStepItem) => {
                      const stepBadge = getStepBadge(step.step_type);
                      return (
                        <div
                          key={step.step_index}
                          className="rounded-xl border border-zinc-800/80 bg-zinc-900/40 p-4 space-y-2"
                        >
                          <div className="flex items-center justify-between">
                            <span className={`rounded border px-2 py-0.5 text-xs font-medium ${stepBadge.cls}`}>
                              {stepBadge.title}
                            </span>
                            <span className="text-[11px] text-zinc-500">
                              {new Date(step.timestamp_ms).toLocaleTimeString()}
                            </span>
                          </div>
                          <p className="text-xs text-zinc-200">{step.description}</p>
                          {step.media_ids.length > 0 && (
                            <div className="flex items-center space-x-2 pt-1 text-[11px] text-zinc-400">
                              <span>关联媒体:</span>
                              {step.media_ids.map((mid) => (
                                <span key={mid} className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-zinc-300">
                                  {mid}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      );
                    })
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center text-xs text-zinc-500">
              请选择左侧调用链查看详情
            </div>
          )}
        </div>
      </div>

      {/* 图片放大预览模态框 */}
      {zoomImageUrl && (
        <div
          onClick={() => setZoomImageUrl(null)}
          className="fixed inset-0 z-60 flex items-center justify-center bg-black/90 p-4"
        >
          <img
            src={zoomImageUrl}
            alt="Zoom preview"
            className="max-h-[90vh] max-w-[90vw] rounded-lg shadow-2xl object-contain"
          />
        </div>
      )}
    </div>
  );
};
