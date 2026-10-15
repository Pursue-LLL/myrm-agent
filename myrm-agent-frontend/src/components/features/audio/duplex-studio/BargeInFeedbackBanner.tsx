import React from 'react';
import { Zap, X, CornerDownRight, CheckCircle2 } from 'lucide-react';
import { useDuplexVoiceStore } from './useDuplexVoiceStore';

export interface BargeInFeedbackBannerProps {
  className?: string;
}

export const BargeInFeedbackBanner: React.FC<BargeInFeedbackBannerProps> = ({
  className = '',
}) => {
  const { bargeInState, dismissBargeInBanner } = useDuplexVoiceStore();

  if (!bargeInState) {
    return null;
  }

  return (
    <output
      data-testid="barge-in-feedback-banner"
      aria-live="polite"
      className={`block p-3 rounded-2xl bg-amber-500/10 border border-amber-500/30 text-xs font-sans text-amber-200 space-y-2 shadow-lg backdrop-blur-md animate-fade-in ${className}`}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 font-bold text-amber-300">
          <Zap className="w-4 h-4 text-amber-400 animate-pulse" />
          <span>全双工实时插话打断生效 (Zero-Latency Barge-In)</span>
        </div>

        <button
          type="button"
          onClick={dismissBargeInBanner}
          aria-label="关闭打断反馈"
          className="p-1 rounded-lg text-amber-400/80 hover:text-amber-200 hover:bg-amber-500/20 transition-colors"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* 截断与自愈细节 */}
      <div className="p-2 rounded-xl bg-zinc-950/70 border border-amber-500/20 space-y-1 font-mono text-[11px]">
        {bargeInState.interruptedAgentMessage && (
          <div className="text-zinc-400 truncate">
            <span className="text-zinc-500">已截断播报: </span>
            「{bargeInState.interruptedAgentMessage}」
          </div>
        )}

        <div className="flex items-center gap-1 text-amber-300">
          <CornerDownRight className="w-3.5 h-3.5 text-amber-400 shrink-0" />
          <span className="font-semibold truncate">
            用户纠偏: {bargeInState.userInterruptionSnippet}
          </span>
        </div>

        <div className="pt-1 flex items-center gap-1 text-[10px] text-emerald-400 border-t border-zinc-800">
          <CheckCircle2 className="w-3 h-3 text-emerald-400 shrink-0" />
          <span>上下文已无感平滑自愈，直接无缝执行最新纠偏意图</span>
        </div>
      </div>
    </output>
  );
};
