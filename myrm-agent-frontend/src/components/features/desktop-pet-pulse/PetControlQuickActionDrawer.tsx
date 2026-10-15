/**
 * PetControlQuickActionDrawer.tsx
 * 桌面桌宠悬浮态微型控制抽屉：一键叫停/恢复、审批授权处理、快捷追问与主工作台快速唤起
 */

import React, { useState } from 'react';
import {
  ExternalLink,
  MessageSquare,
  Pause,
  Play,
  Send,
  ShieldAlert,
  ThumbsDown,
  ThumbsUp,
  X,
} from 'lucide-react';
import { useDesktopPetPulseStore } from './useDesktopPetPulseStore';

export interface PetControlQuickActionDrawerProps {
  className?: string;
  onSendFollowUp?: (text: string) => void;
  onApprovalDecision?: (approved: boolean) => void;
  onOpenMainWindow?: () => void;
}

export const PetControlQuickActionDrawer: React.FC<
  PetControlQuickActionDrawerProps
> = ({
  className = '',
  onSendFollowUp,
  onApprovalDecision,
  onOpenMainWindow,
}) => {
  const isQuickActionOpen = useDesktopPetPulseStore(
    (state) => state.isQuickActionOpen
  );
  const isPaused = useDesktopPetPulseStore((state) => state.isPaused);
  const activeApproval = useDesktopPetPulseStore((state) => state.activeApproval);
  const primaryAgent = useDesktopPetPulseStore((state) => state.primaryAgent);
  const toggleQuickAction = useDesktopPetPulseStore(
    (state) => state.toggleQuickAction
  );
  const togglePause = useDesktopPetPulseStore((state) => state.togglePause);
  const setActiveApproval = useDesktopPetPulseStore(
    (state) => state.setActiveApproval
  );
  const requestOpenMainWindow = useDesktopPetPulseStore(
    (state) => state.requestOpenMainWindow
  );

  const [followUpText, setFollowUpText] = useState('');

  if (!isQuickActionOpen) {
    return null;
  }

  const handleClose = (): void => {
    toggleQuickAction(false);
  };

  const handleOpenMain = (): void => {
    requestOpenMainWindow();
    if (onOpenMainWindow !== undefined) {
      onOpenMainWindow();
    }
  };

  const handleApproval = (approved: boolean): void => {
    setActiveApproval(null);
    if (onApprovalDecision !== undefined) {
      onApprovalDecision(approved);
    }
  };

  const handleSendFollowUp = (): void => {
    const text = followUpText.trim();
    if (text === '') {
      return;
    }
    if (onSendFollowUp !== undefined) {
      onSendFollowUp(text);
    }
    setFollowUpText('');
  };

  return (
    <section
      data-testid="pet-control-quick-drawer"
      aria-label="桌宠微型快捷控制抽屉"
      className={`absolute bottom-full mb-3 left-1/2 -translate-x-1/2 w-84 bg-slate-900/95 backdrop-blur-md border border-slate-700/80 rounded-2xl shadow-2xl p-3.5 z-50 flex flex-col gap-3 ${className}`}
    >
      {/* 顶部标题与智能体标识 */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-2">
        <div className="flex items-center gap-2">
          <span
            className="w-2 h-2 rounded-full"
            style={{
              backgroundColor: primaryAgent?.colorTheme ?? '#3b82f6',
            }}
          />
          <span className="text-xs font-semibold text-slate-200">
            {primaryAgent?.name ?? 'Myrm 桌面桌宠'}
          </span>
          <span className="text-[10px] text-slate-400">
            {isPaused ? '已暂停' : '监控中'}
          </span>
        </div>

        <div className="flex items-center gap-1">
          <button
            type="button"
            data-testid="drawer-open-main-btn"
            aria-label="唤起主工作台"
            onClick={handleOpenMain}
            className="p-1 rounded text-slate-400 hover:text-blue-400 hover:bg-slate-800 transition-colors"
            title="双击或点击展开完整主工作台"
          >
            <ExternalLink className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            data-testid="drawer-close-btn"
            aria-label="收起控制抽屉"
            onClick={handleClose}
            className="p-1 rounded text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* 待审批提醒卡片 */}
      {activeApproval !== null && (
        <div
          data-testid="drawer-approval-card"
          className="bg-amber-950/40 border border-amber-600/50 rounded-xl p-2.5 flex flex-col gap-2"
        >
          <div className="flex items-start gap-2">
            <ShieldAlert className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
            <div className="flex-1 text-left">
              <div className="text-xs font-semibold text-amber-300">
                {activeApproval.title}
              </div>
              <div className="text-[11px] text-amber-200/80 mt-0.5 line-clamp-2">
                {activeApproval.description}
              </div>
              {activeApproval.toolName !== undefined && (
                <div className="text-[10px] font-mono text-amber-400 mt-1">
                  工具: {activeApproval.toolName}
                </div>
              )}
            </div>
          </div>
          <div className="flex items-center justify-end gap-2 pt-1 border-t border-amber-800/40">
            <button
              type="button"
              data-testid="drawer-approval-reject-btn"
              onClick={() => handleApproval(false)}
              className="flex items-center gap-1 px-2.5 py-1 text-xs rounded bg-slate-800 text-slate-300 hover:bg-slate-700"
            >
              <ThumbsDown className="w-3 h-3 text-red-400" />
              <span>拒绝</span>
            </button>
            <button
              type="button"
              data-testid="drawer-approval-accept-btn"
              onClick={() => handleApproval(true)}
              className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded bg-amber-600 text-white hover:bg-amber-500 shadow"
            >
              <ThumbsUp className="w-3 h-3" />
              <span>允许执行</span>
            </button>
          </div>
        </div>
      )}

      {/* 快捷追问输入框 */}
      <div className="flex flex-col gap-1.5">
        <label
          htmlFor="drawer-quick-followup-input"
          className="text-[11px] text-slate-400 flex items-center gap-1"
        >
          <MessageSquare className="w-3 h-3 text-blue-400" />
          <span>气泡快速追问:</span>
        </label>
        <div className="flex items-center gap-1.5">
          <input
            id="drawer-quick-followup-input"
            data-testid="drawer-quick-followup-input"
            type="text"
            value={followUpText}
            onChange={(e) => setFollowUpText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                handleSendFollowUp();
              }
            }}
            placeholder="随时对任务回复或补充要求..."
            className="flex-1 text-xs bg-slate-950 border border-slate-700/80 rounded-lg px-2.5 py-1.5 text-slate-200 focus:outline-none focus:border-blue-500"
          />
          <button
            type="button"
            data-testid="drawer-send-followup-btn"
            disabled={followUpText.trim() === ''}
            onClick={handleSendFollowUp}
            className="p-1.5 rounded-lg bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed shadow transition-colors"
          >
            <Send className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* 底部控制工具栏 */}
      <div className="flex items-center justify-between pt-1 border-t border-slate-800 text-xs">
        <button
          type="button"
          data-testid="drawer-toggle-pause-btn"
          onClick={() => togglePause()}
          className={`flex items-center gap-1 px-2.5 py-1 rounded-lg border transition-colors ${
            isPaused
              ? 'bg-amber-500/20 text-amber-300 border-amber-500/40 hover:bg-amber-500/30'
              : 'bg-slate-800 text-slate-300 border-slate-700 hover:bg-slate-700'
          }`}
        >
          {isPaused ? (
            <>
              <Play className="w-3.5 h-3.5 text-emerald-400" />
              <span>恢复执行</span>
            </>
          ) : (
            <>
              <Pause className="w-3.5 h-3.5 text-amber-400" />
              <span>叫停任务</span>
            </>
          )}
        </button>

        <button
          type="button"
          data-testid="drawer-full-window-btn"
          onClick={handleOpenMain}
          className="flex items-center gap-1 text-slate-400 hover:text-slate-200 text-[11px]"
        >
          <span>回到主窗口</span>
          <ExternalLink className="w-3 h-3" />
        </button>
      </div>
    </section>
  );
};
