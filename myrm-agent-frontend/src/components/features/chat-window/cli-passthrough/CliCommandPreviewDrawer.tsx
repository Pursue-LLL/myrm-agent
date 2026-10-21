/**
 * [INPUT]
 * - react (POS: UI Framework)
 * - lucide-react (POS: Consistent vector icons)
 * - @/components/features/chat-window/cli-passthrough/cliPassthroughTypes
 * - @/components/features/chat-window/cli-passthrough/useCliPassthroughStore
 *
 * [OUTPUT]
 * - CliCommandPreviewDrawer (POS: Lightweight local terminal drawer for pass-through command execution)
 *
 * [POS]
 * Primary drawer UI for Item 194 (P0): DirectCliPassThroughWithContextVisibilitySwitchSuite.
 * Renders command output above message input, highlighting context visibility ('!' vs '!!').
 */

import React, { useState } from 'react';
import {
  Terminal,
  CheckCircle2,
  XCircle,
  ShieldAlert,
  Loader2,
  Copy,
  Check,
  Trash2,
  ChevronDown,
  Eye,
  EyeOff,
} from 'lucide-react';
import type {
  CliPassThroughMode,
  CliExecutionStatus,
} from './cliPassthroughTypes';
import { useCliPassthroughStore } from './useCliPassthroughStore';

export interface CliCommandPreviewDrawerProps {
  readonly onClose?: () => void;
  readonly className?: string;
}

function getModeBadge(mode: CliPassThroughMode) {
  if (mode === 'visible_to_context') {
    return {
      label: '上下文可见 · AI 感知',
      icon: <Eye className="w-3.5 h-3.5 text-blue-500" />,
      badgeClass: 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20',
    };
  }
  return {
    label: '仅本地自省 · 0 Token 消耗',
    icon: <EyeOff className="w-3.5 h-3.5 text-emerald-500" />,
    badgeClass: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20',
  };
}

function getStatusIndicator(status: CliExecutionStatus, exitCode: number | null, durationMs: number) {
  switch (status) {
    case 'running': {
      return (
        <div className="flex items-center gap-1.5 text-amber-500 text-xs">
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          <span>正在沙箱极速执行...</span>
        </div>
      );
    }
    case 'success': {
      return (
        <div className="flex items-center gap-1.5 text-emerald-500 text-xs">
          <CheckCircle2 className="w-3.5 h-3.5" />
          <span>执行成功 ({durationMs}ms)</span>
        </div>
      );
    }
    case 'failed': {
      return (
        <div className="flex items-center gap-1.5 text-rose-500 text-xs">
          <XCircle className="w-3.5 h-3.5" />
          <span>执行失败 (退出码: {exitCode ?? 1})</span>
        </div>
      );
    }
    case 'blocked_by_guard': {
      return (
        <div className="flex items-center gap-1.5 text-rose-500 text-xs font-semibold">
          <ShieldAlert className="w-3.5 h-3.5" />
          <span>安全策略已拦截高危指令</span>
        </div>
      );
    }
    default: {
      return null;
    }
  }
}

export const CliCommandPreviewDrawer: React.FC<CliCommandPreviewDrawerProps> = ({
  onClose,
  className = '',
}) => {
  const isDrawerOpen = useCliPassthroughStore((state) => state.isDrawerOpen);
  const activeCommand = useCliPassthroughStore((state) => state.activeCommand);
  const toggleDrawer = useCliPassthroughStore((state) => state.toggleDrawer);
  const clearHistory = useCliPassthroughStore((state) => state.clearHistory);

  const [copied, setCopied] = useState<boolean>(false);

  if (!isDrawerOpen || !activeCommand) {
    return null;
  }

  const handleClose = () => {
    toggleDrawer(false);
    if (onClose) {
      onClose();
    }
  };

  const handleCopyOutput = async () => {
    if (!activeCommand.output) {
      return;
    }
    try {
      await navigator.clipboard.writeText(activeCommand.output);
      setCopied(true);
      setTimeout(() => {
        setCopied(false);
      }, 2000);
    } catch {
      // 容错
    }
  };

  const modeBadge = getModeBadge(activeCommand.mode);

  return (
    <section
      aria-label="CLI 穿透执行抽屉"
      data-testid="cli-command-preview-drawer"
      className={`w-full rounded-xl border border-border/80 bg-card/95 backdrop-blur-md shadow-lg overflow-hidden transition-all mb-3 ${className}`}
    >
      {/* 抽屉头部 */}
      <div className="flex items-center justify-between border-b border-border/70 px-4 py-2.5 bg-muted/40">
        <div className="flex items-center gap-2">
          <Terminal className="w-4 h-4 text-primary" />
          <span className="font-semibold text-xs text-foreground font-mono">
            $ {activeCommand.command}
          </span>
          <div
            className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium ${modeBadge.badgeClass}`}
          >
            {modeBadge.icon}
            <span>{modeBadge.label}</span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {getStatusIndicator(activeCommand.status, activeCommand.exitCode, activeCommand.durationMs)}

          <button
            type="button"
            onClick={handleCopyOutput}
            title="复制命令输出"
            aria-label="复制命令输出"
            className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
          >
            {copied ? (
              <>
                <Check className="w-3.5 h-3.5 text-emerald-500" />
                <span className="text-emerald-500 text-[11px]">已复制</span>
              </>
            ) : (
              <>
                <Copy className="w-3.5 h-3.5" />
                <span className="text-[11px]">复制</span>
              </>
            )}
          </button>

          <button
            type="button"
            onClick={clearHistory}
            title="清空执行记录"
            aria-label="清空执行记录"
            className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-rose-500 transition-colors"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>

          <button
            type="button"
            onClick={handleClose}
            title="收起抽屉"
            aria-label="收起抽屉"
            className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
          >
            <ChevronDown className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* 终端输出区域 */}
      <div className="max-h-60 overflow-y-auto p-3.5 bg-slate-950 font-mono text-xs text-slate-200">
        {activeCommand.status === 'blocked_by_guard' ? (
          <div className="flex items-start gap-2 text-rose-400 bg-rose-950/40 border border-rose-900/60 rounded p-2.5">
            <ShieldAlert className="w-4 h-4 shrink-0 mt-0.5" />
            <div className="space-y-0.5">
              <div className="font-semibold text-rose-300">安全守卫阻断通知</div>
              <div className="text-[11px] text-rose-200">{activeCommand.output}</div>
            </div>
          </div>
        ) : activeCommand.output ? (
          <pre className="whitespace-pre-wrap break-all leading-relaxed">
            {activeCommand.output}
          </pre>
        ) : (
          <span className="text-slate-500">正在等待输出流...</span>
        )}
      </div>

      {/* 底部模式提示说明 */}
      <div className="px-4 py-1.5 bg-muted/20 border-t border-border/40 text-[11px] text-muted-foreground flex justify-between items-center">
        <span>
          {activeCommand.mode === 'visible_to_context'
            ? '提示：以 ! 开头的命令输出会自动作为 [USER_CMD_EXEC] 附件同步至上下文供 AI 查阅。'
            : '提示：以 !! 开头的命令输出仅供本地终端抽屉查看，绝对不写入上下文，零 Token 消耗。'}
        </span>
        <span className="text-[10px] text-muted-foreground/60">
          耗时: {activeCommand.durationMs}ms
        </span>
      </div>
    </section>
  );
};
