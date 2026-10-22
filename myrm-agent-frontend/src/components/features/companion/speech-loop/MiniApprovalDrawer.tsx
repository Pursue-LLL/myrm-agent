import React from 'react';
import {
  Check,
  X,
  FileCode,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import { usePetSpeechLoopStore } from './usePetSpeechLoopStore';

export interface MiniApprovalDrawerProps {
  className?: string;
}

export const MiniApprovalDrawer: React.FC<MiniApprovalDrawerProps> = ({
  className = '',
}) => {
  const {
    isApprovalDrawerOpen,
    approvalAction,
    toggleApprovalDrawer,
    approveAction,
    rejectAction,
  } = usePetSpeechLoopStore();

  if (!isApprovalDrawerOpen || !approvalAction) {
    return null;
  }

  const isHighRisk = approvalAction.riskLevel === 'high';

  return (
    <aside
      data-testid="mini-approval-drawer"
      aria-label="贴身微型拍板抽屉"
      className={`fixed right-4 bottom-24 z-50 w-72 rounded-2xl bg-zinc-900/95 backdrop-blur-xl border border-zinc-750 shadow-[0_12px_40px_rgba(0,0,0,0.6)] p-4 space-y-3 font-sans text-zinc-100 animate-fade-in ${className}`}
    >
      {/* 1. 顶部标题 */}
      <div className="flex items-center justify-between pb-2 border-b border-zinc-800">
        <div className="flex items-center gap-1.5">
          <div className="p-1 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
            <Sparkles className="w-3.5 h-3.5" />
          </div>
          <span className="text-xs font-bold text-zinc-200">
            贴身拍板与验收
          </span>
        </div>

        <button
          type="button"
          onClick={() => {
            toggleApprovalDrawer(false);
          }}
          aria-label="关闭拍板面板"
          className="p-1 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* 2. 核心结论与风险提示 */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-mono text-zinc-400 uppercase tracking-wider">
            方案摘要
          </span>
          <span
            className={`flex items-center gap-1 text-[10px] font-mono px-1.5 py-0.5 rounded-full border ${
              isHighRisk
                ? 'bg-rose-500/10 text-rose-300 border-rose-500/30'
                : 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30'
            }`}
          >
            {isHighRisk ? (
              <ShieldAlert className="w-2.5 h-2.5" />
            ) : (
              <ShieldCheck className="w-2.5 h-2.5" />
            )}
            <span>{isHighRisk ? '需重点复核' : '低风险变更'}</span>
          </span>
        </div>

        <p className="text-xs text-zinc-200 leading-snug font-medium">
          {approvalAction.summary}
        </p>
      </div>

      {/* 3. 拟变更文件清单 */}
      <div className="space-y-1">
        <span className="text-[10px] font-mono text-zinc-400">
          受影响文件 ({approvalAction.proposedFiles.length}):
        </span>
        <div className="space-y-1 max-h-24 overflow-y-auto">
          {approvalAction.proposedFiles.map((file, idx) => (
            <div
              key={`file-${idx}`}
              className="flex items-center gap-1.5 p-1 px-1.5 rounded bg-zinc-950 border border-zinc-850 text-[10px] font-mono text-zinc-300"
            >
              <FileCode className="w-3 h-3 text-indigo-400 shrink-0" />
              <span className="truncate">{file}</span>
            </div>
          ))}
        </div>
      </div>

      {/* 4. 底部双决策按钮 */}
      <div className="pt-2 flex items-center gap-2 border-t border-zinc-800">
        <button
          type="button"
          onClick={rejectAction}
          className="flex-1 py-1.5 px-2.5 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs font-medium transition-colors text-center"
        >
          修改撤回
        </button>

        <button
          type="button"
          onClick={approveAction}
          className="flex-1 py-1.5 px-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow transition-colors flex items-center justify-center gap-1"
        >
          <Check className="w-3.5 h-3.5" />
          <span>批准实施</span>
        </button>
      </div>
    </aside>
  );
};
