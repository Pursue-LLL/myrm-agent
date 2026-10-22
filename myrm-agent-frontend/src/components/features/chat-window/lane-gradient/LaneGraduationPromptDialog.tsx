'use client';

/**
 * [INPUT]
 * - @/components/features/chat-window/lane-gradient/useLaneSemanticStore
 * - lucide-react (POS: Vector icons, zero native emojis)
 *
 * [OUTPUT]
 * - LaneGraduationPromptDialog (POS: In-session auto-graduation dialog & non-intrusive banner)
 *
 * [POS]
 * Implementation for Item 188 in-session auto-graduation.
 * Intercepts write/shell triggers in Chat Lane and seamlessly upgrades the session
 * to Workspace Lane while fully preserving conversation history and context.
 */

import React, { memo, useCallback } from 'react';
import {
  Sparkles,
  AlertCircle,
  HardDrive,
  Cloud,
  ArrowRight,
  X,
  Code2,
} from 'lucide-react';
import { useLaneSemanticStore } from './useLaneSemanticStore';

interface LaneGraduationPromptDialogProps {
  readonly onGraduated?: (targetMode: 'local_workspace' | 'cloud_sandbox') => void;
  readonly onDismissed?: () => void;
}

export const LaneGraduationPromptDialog = memo(function LaneGraduationPromptDialog({
  onGraduated,
  onDismissed,
}: LaneGraduationPromptDialogProps) {
  const isOpen = useLaneSemanticStore((s) => s.isGraduationDialogOpen);
  const pending = useLaneSemanticStore((s) => s.pendingGraduation);
  const graduateToWorkspace = useLaneSemanticStore((s) => s.graduateToWorkspace);
  const dismissGraduation = useLaneSemanticStore((s) => s.dismissGraduation);

  const handleGraduateLocal = useCallback(() => {
    graduateToWorkspace('local_workspace');
    if (onGraduated) {
      onGraduated('local_workspace');
    }
  }, [graduateToWorkspace, onGraduated]);

  const handleGraduateCloud = useCallback(() => {
    graduateToWorkspace('cloud_sandbox');
    if (onGraduated) {
      onGraduated('cloud_sandbox');
    }
  }, [graduateToWorkspace, onGraduated]);

  const handleDismiss = useCallback(() => {
    dismissGraduation();
    if (onDismissed) {
      onDismissed();
    }
  }, [dismissGraduation, onDismissed]);

  if (!isOpen) {
    return null;
  }

  const snippet = pending?.detectedSnippet ?? '';
  const reason = pending?.reason ?? '检测到代码写入或命令执行意图';
  const keyword = pending?.matchedKeyword ?? '';

  return (
    <dialog
      open
      aria-labelledby="lane-graduation-title"
      aria-describedby="lane-graduation-desc"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm m-0 max-w-none max-h-none w-full h-full border-0"
    >
      <div className="relative w-full max-w-lg rounded-xl border border-neutral-700/80 bg-neutral-900 p-6 shadow-2xl text-neutral-100 animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-sky-500/10 text-sky-400 border border-sky-500/20">
              <Sparkles className="w-5 h-5" aria-hidden="true" />
            </div>
            <div>
              <h2 id="lane-graduation-title" className="text-base font-semibold text-neutral-100">
                通道即时毕业引导
              </h2>
              <p id="lane-graduation-desc" className="text-xs text-neutral-400 mt-0.5">
                当前处于快速对话通道，已检测到越界工程意图
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={handleDismiss}
            className="p-1 rounded-md text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800 transition-colors"
            aria-label="关闭提示"
          >
            <X className="w-4 h-4" aria-hidden="true" />
          </button>
        </div>

        {/* Reason and Snippet */}
        <div className="mt-4 p-3 rounded-lg bg-neutral-800/60 border border-neutral-700/50 space-y-2">
          <div className="flex items-center gap-2 text-xs text-amber-400">
            <AlertCircle className="w-4 h-4 shrink-0" aria-hidden="true" />
            <span className="font-medium">{reason}</span>
          </div>

          {keyword ? (
            <div className="flex items-center gap-1.5 text-[11px] text-neutral-400">
              <span>触发标识：</span>
              <span className="px-1.5 py-0.5 rounded bg-neutral-700 font-mono text-neutral-200">
                {keyword}
              </span>
            </div>
          ) : null}

          {snippet ? (
            <div className="flex items-start gap-1.5 text-[11px] text-neutral-400 bg-neutral-900/60 p-2 rounded border border-neutral-800">
              <Code2 className="w-3.5 h-3.5 text-neutral-500 shrink-0 mt-0.5" aria-hidden="true" />
              <span className="font-mono text-neutral-300 break-all">{snippet}</span>
            </div>
          ) : null}
        </div>

        {/* Context Preservation Note */}
        <p className="mt-3 text-xs text-neutral-400 leading-relaxed">
          选择毕业到工作区通道后，将<strong className="text-neutral-200">完整保留当前会话的全部历史与上下文</strong>，
          无需重新开启会话即可解锁完整的代码修改与终端执行权限。
        </p>

        {/* Action Buttons */}
        <div className="mt-5 grid grid-cols-1 sm:grid-cols-2 gap-3">
          <button
            type="button"
            onClick={handleGraduateLocal}
            className="flex items-center justify-between p-3 rounded-lg border border-emerald-500/30 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 transition-all text-left group"
          >
            <div className="flex items-center gap-2.5">
              <HardDrive className="w-4 h-4 text-emerald-400" aria-hidden="true" />
              <div>
                <div className="font-medium text-xs">毕业到本地工作区</div>
                <div className="text-[10px] text-emerald-400/70">直接读写本地工程与文件</div>
              </div>
            </div>
            <ArrowRight className="w-4 h-4 opacity-60 group-hover:opacity-100 group-hover:translate-x-0.5 transition-transform" aria-hidden="true" />
          </button>

          <button
            type="button"
            onClick={handleGraduateCloud}
            className="flex items-center justify-between p-3 rounded-lg border border-indigo-500/30 bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-300 transition-all text-left group"
          >
            <div className="flex items-center gap-2.5">
              <Cloud className="w-4 h-4 text-indigo-400" aria-hidden="true" />
              <div>
                <div className="font-medium text-xs">毕业到云端沙箱</div>
                <div className="text-[10px] text-indigo-400/70">云端隔离执行，安全零污染</div>
              </div>
            </div>
            <ArrowRight className="w-4 h-4 opacity-60 group-hover:opacity-100 group-hover:translate-x-0.5 transition-transform" aria-hidden="true" />
          </button>
        </div>

        {/* Dismiss Footer */}
        <div className="mt-4 pt-3 border-t border-neutral-800 flex justify-end">
          <button
            type="button"
            onClick={handleDismiss}
            className="px-3 py-1.5 text-xs text-neutral-400 hover:text-neutral-200 transition-colors"
          >
            仅以对话模式继续（忽略）
          </button>
        </div>
      </div>
    </dialog>
  );
});
