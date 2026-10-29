import React from 'react';
import { Sparkles, ArrowRight, X, ShieldAlert } from 'lucide-react';
import { useThreeModeStore } from './useThreeModeStore';

export const ThreeModeIntentGuidanceToast: React.FC = () => {
  const { intentGuidance, setMode, dismissIntentGuidance } = useThreeModeStore();

  if (!intentGuidance || !intentGuidance.hasWriteIntent) {
    return null;
  }

  const handleSwitchToCraft = () => {
    setMode('craft');
  };

  return (
    <aside
      data-testid="three-mode-intent-guidance-toast"
      aria-label="模式写意图检测提示"
      className="p-3 bg-amber-950/80 backdrop-blur-md border border-amber-500/40 rounded-2xl shadow-xl flex items-start justify-between gap-3 text-xs select-none animate-in fade-in slide-in-from-bottom-2 duration-200"
    >
      <div className="flex items-start gap-2.5">
        <div className="w-6 h-6 rounded-lg bg-amber-500/20 border border-amber-500/40 flex items-center justify-center shrink-0 mt-0.5 text-amber-300">
          <ShieldAlert className="w-3.5 h-3.5" />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 font-semibold text-amber-200">
            <span>写操作意图提醒</span>
            <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-amber-900/60 text-amber-300 border border-amber-700/60">
              只读保护中
            </span>
          </div>

          <p className="mt-1 text-slate-300 leading-relaxed text-[11px]">
            {intentGuidance.guidanceMessage}
          </p>

          <div className="mt-2 flex items-center gap-2">
            <button
              type="button"
              onClick={handleSwitchToCraft}
              className="flex items-center gap-1 px-3 py-1 rounded-lg bg-amber-600 hover:bg-amber-500 text-white font-medium text-xs transition-colors shadow-xs"
            >
              <Sparkles className="w-3 h-3" />
              <span>一键切换为 Craft 做一做</span>
              <ArrowRight className="w-3 h-3" />
            </button>

            <button
              type="button"
              onClick={dismissIntentGuidance}
              className="px-2.5 py-1 rounded-lg hover:bg-amber-900/40 text-amber-300/80 hover:text-amber-200 transition-colors text-xs"
            >
              保持问一问
            </button>
          </div>
        </div>
      </div>

      <button
        type="button"
        onClick={dismissIntentGuidance}
        className="p-1 rounded-lg text-amber-400/70 hover:text-amber-200 hover:bg-amber-900/40 transition-colors shrink-0"
        title="关闭提醒"
        aria-label="关闭提醒"
      >
        <X className="w-3.5 h-3.5" />
      </button>
    </aside>
  );
};
