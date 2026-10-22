/**
 * [INPUT]: VisualFailureFlightRecorderModalProps with slices list, current selection, and modal controls.
 * [OUTPUT]: High-fidelity Visual Failure Flight Recorder Modal with interactive short-loop playback and filmstrip.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/VisualFailureFlightRecorderModal.tsx
 */

import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
  VisualFailureFlightRecorderModalProps,
  VisualFailureSliceItem,
} from './visualFlightRecorderTypes';

function getFailureBadgeColor(kind: string): string {
  switch (kind) {
    case 'popup_overlay':
      return 'bg-amber-950 text-amber-300 border-amber-700/80';
    case 'captcha_slider':
      return 'bg-rose-950 text-rose-300 border-rose-700/80';
    case 'element_timeout':
      return 'bg-purple-950 text-purple-300 border-purple-700/80';
    case 'stuck_loop':
      return 'bg-orange-950 text-orange-300 border-orange-700/80';
    default:
      return 'bg-slate-850 text-slate-300 border-slate-700';
  }
}

export const VisualFailureFlightRecorderModal: React.FC<VisualFailureFlightRecorderModalProps> = ({
  isOpen,
  onClose,
  slices,
  selectedSliceId,
  onSelectSlice,
  onRefresh,
  isRefreshing = false,
}) => {
  const [internalSelectedId, setInternalSelectedId] = useState<string>(
    selectedSliceId || (slices.length > 0 ? slices[0].slice_id : '')
  );
  const [currentFrameIndex, setCurrentFrameIndex] = useState<number>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(true);
  const playTimerRef = useRef<number | null>(null);

  const activeSliceId = selectedSliceId || internalSelectedId;

  const currentSlice = useMemo<VisualFailureSliceItem | null>(() => {
    return slices.find((s) => s.slice_id === activeSliceId) || slices[0] || null;
  }, [slices, activeSliceId]);

  // Reset frame index on slice change
  useEffect(() => {
    setCurrentFrameIndex(0);
    setIsPlaying(true);
  }, [currentSlice?.slice_id]);

  // Auto playback loop (5 fps = 200ms per frame)
  useEffect(() => {
    if (!isPlaying || !currentSlice || currentSlice.frames.length <= 1) {
      if (playTimerRef.current) {
        window.clearInterval(playTimerRef.current);
        playTimerRef.current = null;
      }
      return;
    }

    playTimerRef.current = window.setInterval(() => {
      setCurrentFrameIndex((prev) => {
        const next = prev + 1;
        return next >= currentSlice.frames.length ? 0 : next;
      });
    }, 200);

    return () => {
      if (playTimerRef.current) {
        window.clearInterval(playTimerRef.current);
        playTimerRef.current = null;
      }
    };
  }, [isPlaying, currentSlice]);

  if (!isOpen) return null;

  const handleSelect = (sliceId: string) => {
    setInternalSelectedId(sliceId);
    if (onSelectSlice) {
      onSelectSlice(sliceId);
    }
  };

  const activeFrame = currentSlice && currentSlice.frames.length > 0
    ? currentSlice.frames[currentFrameIndex] || currentSlice.frames[0]
    : null;

  const totalFrames = currentSlice ? currentSlice.frames.length : 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fade-in">
      <div className="flex flex-col w-full max-w-5xl h-[88vh] bg-slate-950 text-slate-100 rounded-2xl border border-slate-800 shadow-2xl overflow-hidden">
        {/* Top Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-900/90">
          <div className="flex items-center gap-3">
            <span className="p-2 rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/20 text-lg">
              📼
            </span>
            <div>
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                智能体视觉故障黑匣子与卡顿回放
                <span className="px-2 py-0.5 rounded text-[10px] bg-slate-800 text-slate-400 font-mono">
                  15s Ring-Buffer / 5fps
                </span>
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">
                滚动录制虚拟桌面与浏览器操作，遭遇卡顿或崩溃自动截断切片，10 秒内一眼破案
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {onRefresh && (
              <button
                onClick={onRefresh}
                disabled={isRefreshing}
                className="p-1.5 text-xs bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg text-slate-300 transition-colors"
                title="刷新黑匣子"
              >
                🔄
              </button>
            )}
            <button
              onClick={onClose}
              className="px-3 py-1.5 text-xs font-medium bg-slate-800 hover:bg-slate-700 rounded-lg text-slate-300 transition-colors"
            >
              关闭
            </button>
          </div>
        </div>

        {/* Content Body */}
        <div className="grid grid-cols-1 lg:grid-cols-12 flex-1 min-h-0 divide-y lg:divide-y-0 lg:divide-x divide-slate-800">
          {/* Left Column: Failure Slice Selector */}
          <div className="lg:col-span-4 flex flex-col min-h-0 overflow-y-auto p-3 space-y-2.5 bg-slate-900/30">
            <div className="text-xs font-semibold uppercase tracking-wider text-slate-400 px-2 py-1">
              已捕获故障切片 ({slices.length})
            </div>

            {slices.length === 0 ? (
              <div className="text-center py-16 text-xs text-slate-500">
                暂无视觉故障切片，运行一切平稳
              </div>
            ) : (
              slices.map((slice) => {
                const isSelected = slice.slice_id === currentSlice?.slice_id;
                return (
                  <div
                    key={slice.slice_id}
                    onClick={() => handleSelect(slice.slice_id)}
                    className={`p-3 rounded-xl border text-xs cursor-pointer transition-all ${
                      isSelected
                        ? 'bg-amber-950/20 border-amber-500/50 shadow-md shadow-amber-950/20 ring-1 ring-amber-500/30'
                        : 'bg-slate-900/60 border-slate-800/80 hover:bg-slate-850 hover:border-slate-700'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-1.5 mb-1.5">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-mono border ${getFailureBadgeColor(
                          slice.failure_kind
                        )}`}
                      >
                        {slice.failure_kind}
                      </span>
                      <span className="text-[10px] text-slate-500 font-mono">
                        {slice.duration_seconds.toFixed(1)}s · {slice.total_frames} 帧
                      </span>
                    </div>

                    <div className="font-medium text-slate-200 line-clamp-1 mb-1">
                      {slice.root_cause_label}
                    </div>

                    <div className="flex items-center justify-between text-[10px] text-slate-400 pt-1.5 border-t border-slate-800/60 font-mono">
                      <span>Trace: {slice.trace_id}</span>
                      <span className="text-slate-500">{slice.session_id}</span>
                    </div>
                  </div>
                );
              })
            )}
          </div>

          {/* Right Column: Video/Frame Replay & Root-Cause Inspector */}
          <div className="lg:col-span-8 flex flex-col min-h-0 overflow-y-auto p-4 space-y-4 bg-slate-950">
            {currentSlice ? (
              <>
                {/* 10-Second Root Cause Diagnosis Banner */}
                <div className="p-3.5 rounded-xl bg-amber-950/30 border border-amber-600/40 flex items-start justify-between gap-3">
                  <div className="flex items-start gap-2.5">
                    <span className="text-xl">🚨</span>
                    <div>
                      <div className="text-xs font-bold text-amber-200 flex items-center gap-2">
                        <span>视觉排障定论:</span>
                        <span className="px-2 py-0.5 rounded bg-amber-900/60 text-amber-300 border border-amber-700/60 font-mono text-[11px]">
                          {currentSlice.failure_kind}
                        </span>
                      </div>
                      <p className="text-xs text-amber-100/90 mt-1 leading-relaxed">
                        {currentSlice.root_cause_label}
                      </p>
                    </div>
                  </div>
                  <span className="px-2 py-1 rounded bg-slate-900 border border-slate-700 text-slate-300 font-mono text-[10px]">
                    {currentSlice.slice_id}
                  </span>
                </div>

                {/* Main Visual Player Viewport */}
                <div className="relative aspect-video w-full rounded-xl bg-slate-900/80 border border-slate-800 flex items-center justify-center overflow-hidden shadow-inner group">
                  {activeFrame ? (
                    activeFrame.image_data_uri.startsWith('data:image') ||
                    activeFrame.image_data_uri.startsWith('http') ? (
                      <img
                        src={activeFrame.image_data_uri}
                        alt={`Frame ${activeFrame.frame_index}`}
                        className="w-full h-full object-contain"
                      />
                    ) : (
                      <div className="flex flex-col items-center justify-center p-6 text-center space-y-2 text-slate-400">
                        <span className="text-3xl">🖥️</span>
                        <span className="text-xs font-mono text-slate-300">
                          {activeFrame.image_data_uri}
                        </span>
                        <span className="text-[11px] text-slate-500">
                          {activeFrame.dom_event_summary || '无 DOM 输入事件'}
                        </span>
                      </div>
                    )
                  ) : (
                    <div className="text-xs text-slate-500">切片中无画面数据</div>
                  )}

                  {/* Top-Right HUD Overlay */}
                  <div className="absolute top-2.5 right-2.5 px-2.5 py-1 rounded-lg bg-slate-950/80 backdrop-blur border border-slate-700/80 text-[11px] font-mono text-slate-300 flex items-center gap-2">
                    <span className="text-amber-400">
                      帧 {totalFrames > 0 ? currentFrameIndex + 1 : 0} / {totalFrames}
                    </span>
                    {activeFrame && (
                      <span className="text-slate-500">
                        +{(currentFrameIndex * 0.2).toFixed(1)}s
                      </span>
                    )}
                  </div>

                  {/* Bottom-Left Action HUD Overlay */}
                  {activeFrame?.dom_event_summary && (
                    <div className="absolute bottom-2.5 left-2.5 px-2.5 py-1 rounded-lg bg-slate-950/80 backdrop-blur border border-slate-700/80 text-[10px] font-mono text-cyan-300 truncate max-w-[80%]">
                      ⚡ {activeFrame.dom_event_summary}
                    </div>
                  )}
                </div>

                {/* Player Controller Bar */}
                <div className="p-3 rounded-xl bg-slate-900/70 border border-slate-800 flex items-center gap-3">
                  <button
                    onClick={() => setIsPlaying((prev) => !prev)}
                    className="px-3 py-1.5 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/40 text-xs font-semibold flex items-center gap-1.5 transition-colors"
                  >
                    <span>{isPlaying ? '⏸️' : '▶️'}</span>
                    <span>{isPlaying ? '暂停' : '播放'}</span>
                  </button>

                  <button
                    onClick={() => {
                      setIsPlaying(false);
                      setCurrentFrameIndex((prev) => Math.max(0, prev - 1));
                    }}
                    disabled={currentFrameIndex === 0}
                    className="px-2 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs disabled:opacity-40"
                    title="上一帧"
                  >
                    ⏮️
                  </button>

                  {/* Scrubber slider */}
                  <div className="flex-1 flex items-center gap-2">
                    <input
                      type="range"
                      min={0}
                      max={Math.max(0, totalFrames - 1)}
                      value={currentFrameIndex}
                      onChange={(e) => {
                        setIsPlaying(false);
                        setCurrentFrameIndex(Number(e.target.value));
                      }}
                      className="w-full h-1.5 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-amber-500"
                    />
                  </div>

                  <button
                    onClick={() => {
                      setIsPlaying(false);
                      setCurrentFrameIndex((prev) => Math.min(totalFrames - 1, prev + 1));
                    }}
                    disabled={currentFrameIndex >= totalFrames - 1}
                    className="px-2 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs disabled:opacity-40"
                    title="下一帧"
                  >
                    ⏭️
                  </button>
                </div>

                {/* Filmstrip Reel */}
                <div className="space-y-1.5">
                  <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider flex items-center justify-between">
                    <span>逐帧定位胶卷 (Filmstrip Reel)</span>
                    <span className="text-[10px] text-slate-500 font-mono">
                      点击直接跳转至故障瞬间
                    </span>
                  </div>

                  <div className="flex items-center gap-1.5 overflow-x-auto p-2 rounded-xl bg-slate-900/50 border border-slate-800">
                    {currentSlice.frames.map((frame, idx) => {
                      const isCurrent = idx === currentFrameIndex;
                      return (
                        <div
                          key={`reel-${frame.frame_index}-${idx}`}
                          onClick={() => {
                            setIsPlaying(false);
                            setCurrentFrameIndex(idx);
                          }}
                          className={`flex-shrink-0 w-16 h-10 rounded-lg border cursor-pointer overflow-hidden relative transition-all ${
                            isCurrent
                              ? 'border-amber-400 ring-2 ring-amber-400/50 scale-105'
                              : 'border-slate-800 hover:border-slate-700 opacity-60 hover:opacity-100'
                          }`}
                        >
                          <div className="w-full h-full bg-slate-800 flex items-center justify-center text-[9px] font-mono text-slate-400">
                            #{idx + 1}
                          </div>
                          {idx === totalFrames - 1 && (
                            <span className="absolute bottom-0 right-0 px-1 text-[8px] bg-rose-600 text-white font-bold">
                              崩溃
                            </span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              </>
            ) : (
              <div className="text-center py-24 text-xs text-slate-500">
                请从左侧选择一条视觉故障切片进行回放
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
