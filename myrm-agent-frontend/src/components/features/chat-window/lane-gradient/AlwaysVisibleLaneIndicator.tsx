'use client';

/**
 * [INPUT]
 * - @/store/useChatStore (POS: Downstream connection for current execution context)
 * - @/components/features/chat-window/lane-gradient/useLaneSemanticStore
 * - @/components/features/chat-window/lane-gradient/laneSemanticEngine
 * - lucide-react (POS: Vector icons, zero native emojis)
 *
 * [OUTPUT]
 * - AlwaysVisibleLaneIndicator (POS: Always-visible lane indicator for chat top bar or toolbar)
 *
 * [POS]
 * Persistent visual indicator solving Item 188. Answers the user's immediate question:
 * "What lane am I in, and what can/cannot this lane do right now?"
 */

import React, { memo, useState, useMemo, useCallback } from 'react';
import {
  MessageSquare,
  HardDrive,
  Cloud,
  ChevronDown,
  ArrowUpRight,
  CheckCircle2,
  XCircle,
  Folder,
} from 'lucide-react';
import useChatStore from '@/store/useChatStore';
import { resolveLaneGradientSpec, formatLaneDisplay } from './laneSemanticEngine';
import { useLaneSemanticStore } from './useLaneSemanticStore';
import type { LaneGradientSpec } from './laneSemanticTypes';

interface AlwaysVisibleLaneIndicatorProps {
  readonly className?: string;
}

export const AlwaysVisibleLaneIndicator = memo(function AlwaysVisibleLaneIndicator({
  className = '',
}: AlwaysVisibleLaneIndicatorProps) {
  const [popoverOpen, setPopoverOpen] = useState(false);

  const actionMode = useChatStore((s) => s.actionMode);
  const sandboxMode = useChatStore((s) => s.sandboxMode);
  const workspaceDir = useChatStore((s) => s.workspaceDir);

  const manualLaneOverride = useLaneSemanticStore((s) => s.manualLaneOverride);
  const openGraduationDialog = useLaneSemanticStore((s) => s.openGraduationDialog);

  const spec: LaneGradientSpec = useMemo(() => {
    const computed = resolveLaneGradientSpec(actionMode, sandboxMode, workspaceDir);
    if (manualLaneOverride) {
      if (manualLaneOverride === 'chat' && computed.laneType === 'workspace') {
        return resolveLaneGradientSpec('fast', false, null);
      }
    }
    return computed;
  }, [actionMode, sandboxMode, workspaceDir, manualLaneOverride]);

  const display = useMemo(() => {
    return formatLaneDisplay(spec);
  }, [spec]);

  const togglePopover = useCallback(() => {
    setPopoverOpen((prev) => !prev);
  }, []);

  const handleRequestUpgrade = useCallback(() => {
    setPopoverOpen(false);
    openGraduationDialog();
  }, [openGraduationDialog]);

  const renderLaneIcon = () => {
    if (spec.envMode === 'cloud_sandbox') {
      return <Cloud className="w-3.5 h-3.5 text-indigo-400" aria-hidden="true" />;
    }
    if (spec.envMode === 'local_workspace') {
      return <HardDrive className="w-3.5 h-3.5 text-emerald-400" aria-hidden="true" />;
    }
    return <MessageSquare className="w-3.5 h-3.5 text-sky-400" aria-hidden="true" />;
  };

  const badgeBgClass = useMemo(() => {
    if (spec.badgeColor === 'indigo') {
      return 'bg-indigo-500/10 text-indigo-300 border-indigo-500/30';
    }
    if (spec.badgeColor === 'emerald') {
      return 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30';
    }
    return 'bg-sky-500/10 text-sky-300 border-sky-500/30';
  }, [spec.badgeColor]);

  return (
    <div className={`relative inline-block text-xs select-none ${className}`}>
      {/* Persistent Indicator Pill */}
      <button
        type="button"
        onClick={togglePopover}
        className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border transition-colors hover:opacity-90 focus:outline-none focus:ring-1 focus:ring-sky-500 ${badgeBgClass}`}
        aria-haspopup="dialog"
        aria-expanded={popoverOpen}
        aria-label={`当前运行通道：${display.title}`}
      >
        {renderLaneIcon()}
        <span className="font-medium">{display.title}</span>
        {spec.envMode === 'local_workspace' && workspaceDir ? (
          <span className="max-w-[100px] truncate text-emerald-400/80 hidden sm:inline" title={workspaceDir}>
            ({workspaceDir.split(/[/\\]/).pop()})
          </span>
        ) : null}
        <ChevronDown
          className={`w-3 h-3 opacity-60 transition-transform ${popoverOpen ? 'rotate-180' : ''}`}
          aria-hidden="true"
        />
      </button>

      {/* Expanded Gradient Inspection Popover */}
      {popoverOpen ? (
        <section
          aria-label="通道能力与环境详情"
          className="absolute left-0 mt-1.5 w-72 rounded-lg border border-neutral-700/80 bg-neutral-900/95 p-3.5 shadow-xl backdrop-blur-md z-50 text-neutral-200 animate-in fade-in zoom-in-95 duration-100"
        >
          <div className="flex items-center justify-between pb-2 border-b border-neutral-800">
            <div className="flex items-center gap-2">
              {renderLaneIcon()}
              <span className="font-semibold text-sm">{display.title}</span>
            </div>
            <span
              className={`px-1.5 py-0.5 text-[10px] font-semibold rounded border ${badgeBgClass}`}
            >
              {display.badgeText}
            </span>
          </div>

          <p className="mt-2 text-[11px] text-neutral-400 leading-relaxed">
            {display.description}
          </p>

          {/* Directory Details if Local Workspace */}
          {spec.envMode === 'local_workspace' && workspaceDir ? (
            <div className="mt-2.5 flex items-center gap-1.5 px-2 py-1.5 rounded bg-neutral-800/60 text-[11px] text-neutral-300">
              <Folder className="w-3.5 h-3.5 text-emerald-400 shrink-0" aria-hidden="true" />
              <span className="truncate" title={workspaceDir}>
                {workspaceDir}
              </span>
            </div>
          ) : null}

          {/* Capabilities Grid */}
          <div className="mt-3 space-y-1.5 text-[11px]">
            <div className="font-medium text-neutral-400">通道能力梯度：</div>
            <div className="grid grid-cols-2 gap-1.5 pt-1">
              <div className="flex items-center gap-1">
                {spec.canWriteFiles ? (
                  <CheckCircle2 className="w-3 h-3 text-emerald-400" aria-hidden="true" />
                ) : (
                  <XCircle className="w-3 h-3 text-neutral-500" aria-hidden="true" />
                )}
                <span className={spec.canWriteFiles ? 'text-neutral-200' : 'text-neutral-500'}>
                  磁盘写入
                </span>
              </div>
              <div className="flex items-center gap-1">
                {spec.canExecCommands ? (
                  <CheckCircle2 className="w-3 h-3 text-emerald-400" aria-hidden="true" />
                ) : (
                  <XCircle className="w-3 h-3 text-neutral-500" aria-hidden="true" />
                )}
                <span className={spec.canExecCommands ? 'text-neutral-200' : 'text-neutral-500'}>
                  终端命令
                </span>
              </div>
              <div className="flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3 text-emerald-400" aria-hidden="true" />
                <span className="text-neutral-200">网页检索</span>
              </div>
              <div className="flex items-center gap-1">
                {spec.laneType === 'workspace' ? (
                  <CheckCircle2 className="w-3 h-3 text-emerald-400" aria-hidden="true" />
                ) : (
                  <XCircle className="w-3 h-3 text-neutral-500" aria-hidden="true" />
                )}
                <span className={spec.laneType === 'workspace' ? 'text-neutral-200' : 'text-neutral-500'}>
                  多工件产出
                </span>
              </div>
            </div>
          </div>

          {/* Upgrade CTA if in Chat Lane */}
          {spec.laneType === 'chat' ? (
            <div className="mt-3 pt-2.5 border-t border-neutral-800">
              <button
                type="button"
                onClick={handleRequestUpgrade}
                className="w-full flex items-center justify-center gap-1.5 py-1.5 px-3 rounded bg-sky-600 hover:bg-sky-500 text-white font-medium text-xs transition-colors"
              >
                <span>升级到工作区通道</span>
                <ArrowUpRight className="w-3.5 h-3.5" aria-hidden="true" />
              </button>
            </div>
          ) : null}
        </section>
      ) : null}
    </div>
  );
});
