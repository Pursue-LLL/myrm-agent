'use client';
/* oxlint-disable jsx-a11y/prefer-tag-over-role, jsx-a11y/no-noninteractive-element-interactions */

/**
 * LiveTakeoverDrawer Component.
 * Live screen PIP viewport and floating takeover control bar.
 * Adheres to Cursor Live Takeover paradigm with zero emojis.
 */

import React, { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  HandMetal,
  Loader2,
  Maximize2,
  MousePointer,
  Radio,
  Tv,
  User,
  X,
} from 'lucide-react';
import { MachineNode, TakeoverState } from './machinesTypes';
import { MachinesService } from './machinesService';

interface LiveTakeoverDrawerProps {
  isOpen: boolean;
  machine: MachineNode | null;
  onClose: () => void;
  onStatusChange?: () => void;
}

export const LiveTakeoverDrawer: React.FC<LiveTakeoverDrawerProps> = ({
  isOpen,
  machine,
  onClose,
  onStatusChange,
}) => {
  let t = (key: string): string => key;
  try {
    const translation = useTranslations('machines');
    t = (key: string): string => translation(key);
  } catch {
    // Fallback in test suites
  }

  const [controlState, setControlState] = useState<TakeoverState>('agent');
  const [isUpdating, setIsUpdating] = useState<boolean>(false);
  const [cursorPos, setCursorPos] = useState<{ x: number; y: number }>({ x: 320, y: 180 });

  useEffect(() => {
    if (machine) {
      setControlState(machine.status === 'takeover' ? 'human_takeover' : 'agent');
    }
  }, [machine]);

  const handleToggleTakeover = async (): Promise<void> => {
    if (!machine) {
      return;
    }

    setIsUpdating(true);
    try {
      if (controlState === 'agent') {
        await MachinesService.initiateTakeover(machine.machine_id);
        setControlState('human_takeover');
      } else {
        await MachinesService.releaseTakeover(machine.machine_id);
        setControlState('agent');
      }
      if (onStatusChange) {
        onStatusChange();
      }
    } finally {
      setIsUpdating(false);
    }
  };

  const handleScreenMouseMove = (e: React.MouseEvent<HTMLDivElement>): void => {
    if (controlState === 'human_takeover') {
      const rect = e.currentTarget.getBoundingClientRect();
      setCursorPos({
        x: Math.round(e.clientX - rect.left),
        y: Math.round(e.clientY - rect.top),
      });
    }
  };

  if (!isOpen || !machine) {
    return null;
  }

  const isHumanTakingOver = controlState === 'human_takeover';

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="live-takeover-title"
      className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm"
    >
      <div className="relative w-full max-w-2xl h-full bg-slate-900 border-l border-slate-800 shadow-2xl flex flex-col overflow-hidden animate-in slide-in-from-right duration-200">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-950/60">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-indigo-500/10 text-indigo-400">
              <Tv className="w-5 h-5" />
            </div>
            <div>
              <h2 id="live-takeover-title" className="text-base font-semibold text-slate-100 flex items-center gap-2">
                <span>{machine.display_name}</span>
                <span className="text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-400 font-mono">
                  {machine.ip_address}
                </span>
              </h2>
              <p className="text-xs text-slate-400 mt-0.5 flex items-center gap-1.5">
                <Radio className="w-3 h-3 text-emerald-400 animate-pulse" />
                <span>60 FPS • 低延迟加密流</span>
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Takeover Status Alert Bar */}
        {isHumanTakingOver && (
          <div className="flex items-center justify-between px-6 py-2.5 bg-amber-950/40 border-b border-amber-900/60 text-xs text-amber-200 animate-in fade-in duration-150">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
              <div>
                <span className="font-semibold mr-1.5">{t('takingOverTitle')}:</span>
                <span className="text-amber-300/90 text-[11px]">{t('takingOverDesc')}</span>
              </div>
            </div>
          </div>
        )}

        {/* Simulated Remote Screen Viewport */}
        <div className="flex-1 p-6 flex flex-col justify-between overflow-y-auto bg-slate-950/40">
          <div
            role="region"
            aria-label="Remote Screen Viewport"
            onMouseMove={handleScreenMouseMove}
            className={`relative w-full aspect-video rounded-2xl bg-slate-950 border-2 transition-all flex items-center justify-center overflow-hidden select-none ${
              isHumanTakingOver
                ? 'border-amber-500 shadow-2xl shadow-amber-500/20 ring-2 ring-amber-500/30'
                : 'border-slate-800'
            }`}
          >
            {/* Screen Content Representation */}
            <div className="absolute inset-0 p-4 font-mono text-xs text-slate-600 flex flex-col justify-between pointer-events-none">
              <div className="flex items-center justify-between text-[11px] text-slate-500 border-b border-slate-900 pb-2">
                <span>Display: 1920x1080@60Hz</span>
                <span>WebRTC: 2.1 Mbps • 14ms latency</span>
              </div>

              <div className="text-center py-10 space-y-2">
                <div className="inline-block p-3 rounded-full bg-slate-900/60 border border-slate-800 text-slate-400">
                  {isHumanTakingOver ? (
                    <User className="w-6 h-6 text-amber-400" />
                  ) : (
                    <Bot className="w-6 h-6 text-indigo-400" />
                  )}
                </div>
                <div className="text-xs text-slate-300 font-sans">
                  {isHumanTakingOver ? '人工接管操控中 • 键鼠透传开启' : '智能体自主任务执行中'}
                </div>
                <div className="text-[11px] text-slate-500 font-sans">
                  {isHumanTakingOver ? `光标位置: (${cursorPos.x}, ${cursorPos.y})` : '正在执行自动化浏览器检索与表单填写'}
                </div>
              </div>

              <div className="flex items-center justify-between text-[10px] text-slate-600">
                <span>Node: {machine.hostname}</span>
                <span>OS: {machine.platform}</span>
              </div>
            </div>

            {/* Simulated Live Cursor */}
            {isHumanTakingOver && (
              <div
                style={{ left: cursorPos.x, top: cursorPos.y }}
                className="absolute w-3.5 h-3.5 pointer-events-none -translate-x-1 -translate-y-1 transition-transform duration-75 text-amber-400 drop-shadow"
              >
                <MousePointer className="w-4 h-4 fill-amber-400" />
              </div>
            )}
          </div>

          {/* Floating Takeover Controller Bar */}
          <div className="mt-6 p-4 rounded-2xl bg-slate-900 border border-slate-800 flex items-center justify-between gap-4 shadow-xl">
            <div className="flex items-center gap-3">
              <div
                className={`p-2 rounded-xl border ${
                  isHumanTakingOver
                    ? 'bg-amber-500/15 border-amber-500/30 text-amber-400'
                    : 'bg-indigo-500/15 border-indigo-500/30 text-indigo-400'
                }`}
              >
                {isHumanTakingOver ? <HandMetal className="w-5 h-5" /> : <Bot className="w-5 h-5" />}
              </div>
              <div>
                <span className="text-xs font-semibold text-slate-200 block">
                  {isHumanTakingOver ? '控制权: 人类接管 (Human Control)' : '控制权: 智能体自治 (Agent Autonomous)'}
                </span>
                <span className="text-[11px] text-slate-400">
                  {isHumanTakingOver ? '点击交还按钮即刻无缝恢复 Agent 自主调度' : '遭遇滑块、验证码或特殊交互时可随时接管'}
                </span>
              </div>
            </div>

            <button
              type="button"
              onClick={handleToggleTakeover}
              disabled={isUpdating}
              className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-medium shadow-lg transition-all active:scale-[0.98] shrink-0 ${
                isHumanTakingOver
                  ? 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-emerald-600/20'
                  : 'bg-amber-600 hover:bg-amber-500 text-white shadow-amber-600/20'
              }`}
            >
              {isUpdating ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : isHumanTakingOver ? (
                <CheckCircle2 className="w-3.5 h-3.5" />
              ) : (
                <HandMetal className="w-3.5 h-3.5" />
              )}
              <span>{isHumanTakingOver ? t('resumeBtn') : t('takeoverBtn')}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
