import React, { useState } from 'react';
import {
  Send,
  ShieldAlert,
  CheckCircle,
  XCircle,
  Sparkles,
  ChevronUp,
  ChevronDown,
  Terminal,
} from 'lucide-react';
import { useMobileCompanionStore } from './useMobileCompanionStore';

export interface MobileRemoteSteeringBarProps {
  className?: string;
}

export const MobileRemoteSteeringBar: React.FC<MobileRemoteSteeringBarProps> = ({
  className = '',
}) => {
  const {
    activeTask,
    isRemoteSteeringOpen,
    approvePendingAction,
    sendRemoteSteering,
    toggleRemoteSteering,
  } = useMobileCompanionStore();

  const [instructionText, setInstructionText] = useState('');
  const [rejectReason, setRejectReason] = useState('');
  const [showRejectInput, setShowRejectInput] = useState(false);

  const pendingAppr = activeTask?.pendingApproval;

  const handleSendSteering = (e?: React.FormEvent) => {
    if (e) {
      e.preventDefault();
    }
    if (!instructionText.trim()) {
      return;
    }
    sendRemoteSteering(instructionText.trim());
    setInstructionText('');
  };

  const handleApprove = () => {
    approvePendingAction(true);
  };

  const handleReject = () => {
    approvePendingAction(false, rejectReason || '用户通过手机端拦截');
    setShowRejectInput(false);
    setRejectReason('');
  };

  const handleQuickChip = (text: string) => {
    sendRemoteSteering(text);
  };

  return (
    <div
      data-testid="mobile-remote-steering-bar"
      className={`fixed bottom-0 inset-x-0 z-40 bg-zinc-900/98 backdrop-blur-lg border-t border-zinc-800 shadow-[0_-8px_30px_rgba(0,0,0,0.6)] ${className}`}
    >
      {/* 1. 高危工具审批卡片 (仅当有待审批项时醒目展现) */}
      {pendingAppr && (
        <div className="p-3.5 bg-amber-500/10 border-b border-amber-500/30 text-xs animate-pulse-subtle">
          <div className="flex items-start gap-2.5">
            <div className="p-1.5 rounded-lg bg-amber-500/20 text-amber-400 shrink-0 mt-0.5">
              <ShieldAlert className="w-4 h-4" />
            </div>
            <div className="flex-1 space-y-1">
              <div className="flex items-center justify-between">
                <span className="font-bold text-amber-300">沙箱待审批操作</span>
                <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-amber-500/20 text-amber-200 border border-amber-500/30">
                  {pendingAppr.riskLevel.toUpperCase()} RISK
                </span>
              </div>
              <p className="text-zinc-200 leading-relaxed font-sans">{pendingAppr.description}</p>
              {pendingAppr.params.command && (
                <div className="flex items-center gap-1 font-mono text-[11px] bg-zinc-950/80 p-1.5 rounded border border-zinc-800 text-zinc-300">
                  <Terminal className="w-3 h-3 text-zinc-500" />
                  <span className="truncate">{pendingAppr.params.command}</span>
                </div>
              )}

              {/* 拒绝理由输入 */}
              {showRejectInput && (
                <div className="pt-1.5 space-y-1">
                  <input
                    type="text"
                    value={rejectReason}
                    onChange={(e) => {
                      setRejectReason(e.target.value);
                    }}
                    placeholder="输入拦截或打回原因..."
                    className="w-full px-2 py-1 text-xs bg-zinc-950 text-zinc-200 rounded border border-zinc-700 focus:outline-none focus:border-red-500 font-sans"
                  />
                </div>
              )}

              {/* 审批操作按钮 */}
              <div className="flex items-center justify-end gap-2 pt-1.5">
                {showRejectInput ? (
                  <>
                    <button
                      type="button"
                      onClick={() => {
                        setShowRejectInput(false);
                      }}
                      className="px-2.5 py-1 text-[11px] text-zinc-400 hover:text-zinc-200"
                    >
                      取消
                    </button>
                    <button
                      type="button"
                      onClick={handleReject}
                      className="flex items-center gap-1 px-3 py-1 rounded text-[11px] font-semibold bg-red-600 text-white hover:bg-red-500"
                    >
                      确认拦截
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      type="button"
                      onClick={() => {
                        setShowRejectInput(true);
                      }}
                      className="flex items-center gap-1 px-2.5 py-1 rounded text-[11px] text-red-400 hover:bg-red-950/40 border border-red-500/30 transition-colors"
                    >
                      <XCircle className="w-3 h-3" />
                      拒绝 / 拦截
                    </button>
                    <button
                      type="button"
                      onClick={handleApprove}
                      className="flex items-center gap-1 px-3.5 py-1 rounded text-[11px] font-semibold bg-emerald-600 text-white hover:bg-emerald-500 shadow transition-colors"
                    >
                      <CheckCircle className="w-3 h-3" />
                      授权继续
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 2. 可折叠微调输入面板 */}
      {isRemoteSteeringOpen && (
        <div className="p-3 border-b border-zinc-800 bg-zinc-950/60 space-y-2">
          <div className="flex items-center justify-between text-[11px] text-zinc-400">
            <span className="flex items-center gap-1">
              <Sparkles className="w-3 h-3 text-indigo-400" />
              随行非打断微调 (主任务沙箱步间平滑吸收)
            </span>
            <button
              type="button"
              onClick={() => {
                toggleRemoteSteering(false);
              }}
              className="text-zinc-500 hover:text-zinc-300"
            >
              收起
            </button>
          </div>

          <form onSubmit={handleSendSteering} className="flex gap-2">
            <input
              type="text"
              value={instructionText}
              onChange={(e) => {
                setInstructionText(e.target.value);
              }}
              placeholder="如：增加导出 Excel 按钮、调整计算系数为 1.2..."
              className="flex-1 px-3 py-1.5 text-xs bg-zinc-900 text-zinc-200 rounded-lg border border-zinc-750 focus:outline-none focus:border-indigo-500"
            />
            <button
              type="submit"
              disabled={!instructionText.trim()}
              className="px-3.5 py-1.5 text-xs font-semibold bg-indigo-600 text-white rounded-lg hover:bg-indigo-500 disabled:opacity-40 transition-colors flex items-center gap-1 shrink-0"
            >
              <Send className="w-3 h-3" />
              发送
            </button>
          </form>

          {/* 快捷微调芯片 */}
          <div className="flex items-center gap-1.5 overflow-x-auto text-[10px] text-zinc-300 pt-0.5">
            <button
              type="button"
              onClick={() => {
                handleQuickChip('增加 Excel 导出功能');
              }}
              className="px-2 py-0.5 rounded bg-zinc-800 border border-zinc-700 whitespace-nowrap"
            >
              + 增加 Excel 导出
            </button>
            <button
              type="button"
              onClick={() => {
                handleQuickChip('公式工时系数修改为 1.25');
              }}
              className="px-2 py-0.5 rounded bg-zinc-800 border border-zinc-700 whitespace-nowrap"
            >
              调整公式系数
            </button>
            <button
              type="button"
              onClick={() => {
                handleQuickChip('优化手机端窄屏表格自适应');
              }}
              className="px-2 py-0.5 rounded bg-zinc-800 border border-zinc-700 whitespace-nowrap"
            >
              优化表格窄屏适配
            </button>
          </div>
        </div>
      )}

      {/* 3. 底部轻量交互操作条 */}
      <div className="flex items-center justify-between p-2.5 px-4 text-xs">
        <button
          type="button"
          onClick={() => {
            toggleRemoteSteering();
          }}
          className="flex items-center gap-1 text-zinc-300 hover:text-indigo-400 font-medium transition-colors"
        >
          <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
          <span>手机随行遥控微调</span>
          {isRemoteSteeringOpen ? (
            <ChevronDown className="w-3.5 h-3.5 text-zinc-500" />
          ) : (
            <ChevronUp className="w-3.5 h-3.5 text-zinc-500" />
          )}
        </button>

        <span className="text-[10px] text-zinc-500 font-mono">
          WebSocket 实时信道已就绪
        </span>
      </div>
    </div>
  );
};
