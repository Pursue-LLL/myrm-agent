import React from 'react';
import { Zap, Clock, CheckCircle2, X, Sparkles } from 'lucide-react';
import { useWysiwygEditorStore } from './useWysiwygEditorStore';

export interface ZeroTokenSaveBannerProps {
  className?: string;
}

export const ZeroTokenSaveBanner: React.FC<ZeroTokenSaveBannerProps> = ({
  className = '',
}) => {
  const { lastCommitReport } = useWysiwygEditorStore();

  if (!lastCommitReport) {
    return null;
  }

  return (
    <output
      data-testid="zero-token-save-banner"
      aria-live="polite"
      className={`block p-3 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 text-xs font-sans text-emerald-200 space-y-2 shadow-lg backdrop-blur-md animate-fade-in ${className}`}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 font-bold text-emerald-300">
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          <span>工件版本 v{lastCommitReport.version} 就地极速保存成功</span>
          <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 flex items-center gap-0.5">
            <Zap className="w-3 h-3 text-amber-400" />
            0 Token 消耗
          </span>
        </div>

        <div className="flex items-center gap-2 font-mono text-[10px] text-zinc-400">
          <span className="flex items-center gap-0.5">
            <Clock className="w-3 h-3 text-emerald-400" />
            {lastCommitReport.latencyMs}ms
          </span>
        </div>
      </div>

      <div className="p-2 rounded-xl bg-zinc-950/70 border border-emerald-500/20 space-y-1 font-mono text-[11px]">
        <div className="flex items-center gap-1 text-zinc-300">
          <Sparkles className="w-3 h-3 text-amber-400 shrink-0" />
          <span>
            免模型全量重写，净省去预估 <strong>~{lastCommitReport.tokenSavedCount}</strong> Token，彻底杜绝代码随机漂移与业务逻辑改坏！
          </span>
        </div>
        <p className="text-[10px] text-zinc-500 truncate pt-0.5 border-t border-zinc-850">
          上下文同步: {lastCommitReport.contextIngressPrompt}
        </p>
      </div>
    </output>
  );
};
