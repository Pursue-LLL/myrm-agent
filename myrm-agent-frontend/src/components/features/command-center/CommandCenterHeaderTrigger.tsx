import React from 'react';
import { Gauge } from 'lucide-react';
import { useCommandCenterStore } from './useCommandCenterStore';

export const CommandCenterHeaderTrigger: React.FC = () => {
  const { openModal, health } = useCommandCenterStore();

  const isMac =
    typeof navigator !== 'undefined' &&
    /Mac|iPod|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
  const shortcutHint = isMac ? '⌘.' : 'Ctrl+.';

  const dotColor =
    health.status === 'healthy'
      ? 'bg-emerald-500'
      : health.status === 'warning'
      ? 'bg-amber-500'
      : 'bg-rose-500';

  return (
    <button
      type="button"
      onClick={() => openModal('sessions')}
      data-testid="command-center-header-trigger"
      className="inline-flex items-center gap-2 px-2.5 py-1.5 rounded-xl bg-slate-900/80 hover:bg-slate-800 border border-slate-700/80 text-slate-200 text-xs transition-all shadow-sm group select-none"
      title={`打开全局指挥驾驶舱 (${shortcutHint})`}
      aria-label="打开全局指挥驾驶舱"
    >
      <div className="relative flex items-center justify-center">
        <Gauge className="w-3.5 h-3.5 text-indigo-400 group-hover:text-indigo-300 transition-colors" />
        <span
          className={`absolute -top-0.5 -right-0.5 w-1.5 h-1.5 rounded-full ${dotColor} animate-pulse`}
        />
      </div>

      <span className="font-semibold text-slate-200 text-[11px]">驾驶舱</span>

      <span className="px-1.5 py-0.2 rounded bg-slate-800 text-[10px] font-mono text-slate-400 border border-slate-700/60 group-hover:text-slate-300">
        {shortcutHint}
      </span>
    </button>
  );
};
