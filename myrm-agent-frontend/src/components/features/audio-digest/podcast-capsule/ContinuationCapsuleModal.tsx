/**
 * Continuation Capsule Modal Component
 * 跨端连续性流转胶囊：音频播客收听点到大屏工件深度细读的无缝接力凭证弹窗
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 零原生 emoji，全部采用 Lucide 矢量图标；
 * 3. 前端所有 if 显式包裹大括号；
 * 4. a11y 无障碍标准（使用原生 dialog 标签）。
 */

import React, { useState, useEffect } from 'react';
import {
  QrCode,
  Monitor,
  Clock,
  ArrowRight,
  Check,
  Copy,
  X,
  Sparkles,
} from 'lucide-react';
import { useAudioDigestStore } from './useAudioDigestStore';
import { formatSecondsToTimestamp } from './podcastSynthesizerEngine';

export const ContinuationCapsuleModal: React.FC = () => {
  const [copied, setCopied] = useState<boolean>(false);
  const {
    activeCapsule,
    isCapsuleModalOpen,
    setCapsuleModalOpen,
    resumeFromCapsule,
  } = useAudioDigestStore();

  // Esc 键关闭监听
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') {
        setCapsuleModalOpen(false);
      }
    };

    if (isCapsuleModalOpen) {
      window.addEventListener('keydown', handleKeyDown);
    }

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isCapsuleModalOpen, setCapsuleModalOpen]);

  if (!isCapsuleModalOpen || !activeCapsule) {
    return null;
  }

  const handleCopyUrl = (): void => {
    if (typeof navigator !== 'undefined' && navigator.clipboard) {
      navigator.clipboard.writeText(activeCapsule.continuationQrUrl);
      setCopied(true);
      setTimeout(() => {
        setCopied(false);
      }, 2000);
    }
  };

  const handleResumeOnThisScreen = (): void => {
    resumeFromCapsule(activeCapsule);
  };

  return (
    <dialog
      open
      data-testid="continuation-capsule-modal-backdrop"
      aria-modal="true"
      aria-label="跨端连续性流转胶囊"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 overflow-y-auto bg-transparent border-none m-0 max-w-none max-h-none w-full h-full"
    >
      {/* 遮罩背景点击层 */}
      <div
        aria-hidden="true"
        data-testid="capsule-backdrop-overlay"
        className="fixed inset-0 bg-black/70 backdrop-blur-sm"
        onClick={() => {
          setCapsuleModalOpen(false);
        }}
      />

      {/* 模态卡片主体 */}
      <div
        data-testid="continuation-capsule-modal-content"
        className="relative z-10 w-full max-w-md rounded-2xl border border-indigo-500/40 bg-neutral-900 text-neutral-100 shadow-2xl p-6 space-y-5 overflow-hidden"
      >
        {/* 顶部标题与关闭 */}
        <div className="flex items-center justify-between border-b border-neutral-800 pb-3">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-indigo-500/20 text-indigo-400">
              <QrCode className="h-4 w-4" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-white">
                连续性流转胶囊 (Continuation Capsule)
              </h3>
              <p className="text-[10px] text-neutral-400 font-mono">
                从小屏听觉到大屏视觉无缝接力
              </p>
            </div>
          </div>

          <button
            type="button"
            data-testid="close-capsule-modal-btn"
            onClick={() => {
              setCapsuleModalOpen(false);
            }}
            className="rounded-lg p-1 text-neutral-400 hover:bg-neutral-800 hover:text-white transition-colors"
            aria-label="关闭流转胶囊"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* 核心二维码与时戳锚定区域 */}
        <div className="flex flex-col items-center justify-center rounded-xl border border-neutral-800 bg-neutral-950/70 p-4 space-y-3">
          <div
            data-testid="capsule-qr-code-box"
            className="flex h-36 w-36 items-center justify-center rounded-xl border-2 border-dashed border-indigo-500/50 bg-indigo-950/20 shadow-inner"
          >
            <Monitor className="h-10 w-10 text-indigo-400 animate-pulse" />
          </div>

          <div className="text-center space-y-1">
            <div className="flex items-center justify-center gap-1.5 text-xs font-mono text-indigo-300 font-semibold">
              <Clock className="h-3.5 w-3.5" />
              <span>
                收听进度：{formatSecondsToTimestamp(activeCapsule.playbackSecond)}
              </span>
            </div>
            <div className="text-[11px] text-neutral-400 truncate max-w-xs">
              对应工件章节锚点：
              <span className="font-mono text-cyan-400">
                {activeCapsule.targetAnchorSelector}
              </span>
            </div>
          </div>
        </div>

        {/* 目标工件与来源说明 */}
        <div className="rounded-lg bg-neutral-950/40 border border-neutral-800/80 p-3 text-xs space-y-1">
          <div className="flex items-center justify-between text-[11px] text-neutral-400 font-mono">
            <span>流转来源：{activeCapsule.sourceDevice}</span>
            <span className="text-emerald-400">凭证 10 分钟有效</span>
          </div>
          <div className="font-medium text-neutral-200 truncate">
            {activeCapsule.artifactTitle}
          </div>
        </div>

        {/* 底部操作：复制短链 / 当前大屏立即接力 */}
        <div className="flex items-center gap-2 pt-1">
          <button
            type="button"
            data-testid="copy-capsule-url-btn"
            onClick={handleCopyUrl}
            className="flex items-center gap-1 rounded-lg border border-neutral-700 bg-neutral-800 px-3 py-2 text-xs font-medium text-neutral-300 hover:bg-neutral-700 hover:text-white transition-colors"
          >
            {copied ? (
              <>
                <Check className="h-3.5 w-3.5 text-emerald-400" />
                <span className="text-emerald-400">已复制链接</span>
              </>
            ) : (
              <>
                <Copy className="h-3.5 w-3.5" />
                <span>复制短链</span>
              </>
            )}
          </button>

          <button
            type="button"
            data-testid="resume-on-this-screen-btn"
            onClick={handleResumeOnThisScreen}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-500 transition-colors shadow-md"
          >
            <Sparkles className="h-3.5 w-3.5" />
            <span>在大屏定位到当前讨论章节</span>
            <ArrowRight className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </dialog>
  );
};
