import React from 'react';
import {
  AlertTriangle,
  Building,
  CheckCircle2,
  HelpCircle,
  Key,
  Network,
  RotateCcw,
  Sparkles,
  Ticket,
  X,
} from 'lucide-react';
import { useProgressiveOnboardingStore } from './useProgressiveOnboardingStore';
import type { AttributionCategory } from './progressiveOnboardingTypes';

interface ProviderFailureAttributionCardProps {
  className?: string;
}

export const ProviderFailureAttributionCard: React.FC<ProviderFailureAttributionCardProps> = ({
  className = '',
}) => {
  const { failureAttribution, clearFailureAttribution } = useProgressiveOnboardingStore();

  if (!failureAttribution) {
    return null;
  }

  const { category, title, analogy, hint, rawError, actionText } = failureAttribution;

  const renderCategoryIcon = (cat: AttributionCategory): React.ReactElement => {
    switch (cat) {
      case 'key':
        return <Key className="w-4 h-4 text-amber-400" />;
      case 'url_endpoint':
        return <Building className="w-4 h-4 text-sky-400" />;
      case 'network':
        return <Network className="w-4 h-4 text-rose-400" />;
      case 'quota':
        return <Ticket className="w-4 h-4 text-purple-400" />;
      default:
        return <HelpCircle className="w-4 h-4 text-slate-400" />;
    }
  };

  return (
    <aside
      aria-label="模型测试连接失败新手归因指引卡片"
      className={`rounded-xl border border-amber-500/30 bg-slate-900/95 p-4 shadow-xl backdrop-blur-md transition-all ${className}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-amber-500/10 border border-amber-500/20">
            {renderCategoryIcon(category)}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h4 className="text-xs font-semibold text-white">{title}</h4>
              <span className="rounded bg-amber-500/20 px-1.5 py-0.2 font-mono text-[10px] text-amber-300">
                类比：{analogy}
              </span>
            </div>
            <p className="text-[11px] text-slate-300 mt-1 leading-relaxed">
              {hint}
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => {
            clearFailureAttribution();
          }}
          className="text-slate-400 hover:text-slate-200 transition-colors p-1"
          aria-label="关闭归因提示"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* 新手可读的明确行动指引 */}
      <div className="mt-3 rounded-lg bg-slate-950/80 border border-slate-800 p-2.5">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-emerald-400 mb-0.5">
          <CheckCircle2 className="w-3.5 h-3.5" />
          <span>新手解决指引</span>
        </div>
        <p className="text-xs text-slate-200 font-medium">
          {actionText}
        </p>

        {/* 原始异常折叠信息 */}
        <div className="mt-2 pt-2 border-t border-slate-800/80 flex items-center justify-between text-[10px] text-slate-500 font-mono">
          <span className="truncate max-w-sm">原始异常: {rawError}</span>
          <span>HTTP 语义已映射</span>
        </div>
      </div>
    </aside>
  );
};
