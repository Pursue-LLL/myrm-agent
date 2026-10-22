import React from 'react';
import {
  LayoutDashboard,
  Activity,
  GitFork,
  Sparkles,
  Send,
  X,
  Layers,
} from 'lucide-react';
import { useWorkspaceScopeStore } from './useWorkspaceScopeStore';
import type { DiscoveryChipItem } from './workspaceScopeTypes';

interface InteractiveDashboardDiscoveryChipProps {
  onInjectPrompt?: (prompt: string) => void;
}

export const InteractiveDashboardDiscoveryChip: React.FC<InteractiveDashboardDiscoveryChipProps> = ({
  onInjectPrompt,
}) => {
  const {
    discoveryChips,
    selectedChipResult,
    selectDiscoveryChip,
    clearSelectedChip,
  } = useWorkspaceScopeStore();

  const getIcon = (iconName: string): React.ReactElement => {
    switch (iconName) {
      case 'LayoutDashboard':
        return <LayoutDashboard className="w-3.5 h-3.5" />;
      case 'Activity':
        return <Activity className="w-3.5 h-3.5" />;
      case 'GitFork':
        return <GitFork className="w-3.5 h-3.5" />;
      default:
        return <Sparkles className="w-3.5 h-3.5" />;
    }
  };

  const handleChipClick = (chip: DiscoveryChipItem): void => {
    const prompt = selectDiscoveryChip(chip.id);
    if (prompt && onInjectPrompt) {
      onInjectPrompt(prompt);
    }
  };

  return (
    <section
      aria-label="交互式看板与微应用能力发现区"
      className="space-y-2.5 text-slate-100"
    >
      <div className="flex items-center gap-1.5 text-xs font-medium text-slate-400">
        <Sparkles className="w-3.5 h-3.5 text-amber-400" />
        <span>主动能力发现芯片 (Interactive Mini-App Discovery):</span>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {discoveryChips.map((chip) => (
          <button
            key={chip.id}
            type="button"
            onClick={() => handleChipClick(chip)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-all rounded-lg border bg-slate-900/80 hover:bg-slate-800 text-slate-200 border-slate-800 hover:border-slate-700 hover:text-white shadow-sm"
          >
            <span className="text-sky-400">{getIcon(chip.iconName)}</span>
            <span>{chip.label}</span>
          </button>
        ))}
      </div>

      {selectedChipResult && (
        <div className="p-3 border rounded-xl bg-slate-950/80 border-slate-800 space-y-2 animate-in fade-in zoom-in-95 duration-100">
          <div className="flex items-center justify-between text-xs">
            <span className="font-medium text-sky-300 flex items-center gap-1">
              <Layers className="w-3.5 h-3.5" /> 待注入微应用 Prompt 模板:
            </span>
            <button
              type="button"
              onClick={clearSelectedChip}
              className="p-1 rounded text-slate-400 hover:text-white hover:bg-slate-800"
              aria-label="关闭预览"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
          <p className="text-xs font-mono text-slate-300 bg-slate-900/80 p-2.5 rounded-lg border border-slate-800/80 leading-relaxed">
            {selectedChipResult}
          </p>
          <div className="flex justify-end">
            <button
              type="button"
              onClick={() => {
                if (onInjectPrompt) {
                  onInjectPrompt(selectedChipResult);
                }
                clearSelectedChip();
              }}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors border rounded-lg bg-sky-600 hover:bg-sky-500 text-white border-sky-500"
            >
              <Send className="w-3 h-3" />
              <span>立即执行生成</span>
            </button>
          </div>
        </div>
      )}
    </section>
  );
};
