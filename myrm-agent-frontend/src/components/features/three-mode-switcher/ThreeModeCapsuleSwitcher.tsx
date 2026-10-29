import React from 'react';
import { MessageSquare, FileText, Sparkles, ShieldCheck } from 'lucide-react';
import { useThreeModeStore } from './useThreeModeStore';
import { OFFICE_MODES } from './threeModeEngine';
import { OfficeWorkspaceMode } from './threeModeTypes';

export const ThreeModeCapsuleSwitcher: React.FC = () => {
  const { currentMode, setMode, toggleMatrix } = useThreeModeStore();

  const modes: Array<{
    id: OfficeWorkspaceMode;
    label: string;
    sub: string;
    icon: React.ComponentType<{ className?: string }>;
    activeColor: string;
  }> = [
    {
      id: 'ask',
      label: '问一问',
      sub: '只读问答',
      icon: MessageSquare,
      activeColor: 'bg-emerald-600 text-white shadow-xs',
    },
    {
      id: 'plan',
      label: '想一想',
      sub: '审慎规划',
      icon: FileText,
      activeColor: 'bg-indigo-600 text-white shadow-xs',
    },
    {
      id: 'craft',
      label: '做一做',
      sub: '全自动执行',
      icon: Sparkles,
      activeColor: 'bg-amber-600 text-white shadow-xs',
    },
  ];

  const currentMetadata = OFFICE_MODES[currentMode];

  return (
    <div
      data-testid="three-mode-capsule-switcher"
      className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 p-2 bg-slate-950/80 backdrop-blur-md border border-slate-800 rounded-2xl text-xs select-none"
    >
      {/* 三态切换胶囊 */}
      <div className="flex items-center gap-1 bg-slate-900 p-1 rounded-xl border border-slate-800/80">
        {modes.map((item) => {
          const Icon = item.icon;
          const isSelected = currentMode === item.id;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => setMode(item.id)}
              data-testid={`mode-capsule-btn-${item.id}`}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                isSelected
                  ? item.activeColor
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
              }`}
              title={`${item.label} (${item.sub})`}
            >
              <Icon className="w-3.5 h-3.5" />
              <span>{item.label}</span>
              <span className="text-[10px] opacity-75 hidden md:inline">
                · {item.sub}
              </span>
            </button>
          );
        })}
      </div>

      {/* 当前心智说明与权限透视入口 */}
      <div className="flex items-center justify-between sm:justify-end gap-2.5 px-1">
        <span className="text-[11px] font-mono text-slate-400 truncate max-w-[240px]">
          {currentMetadata.tagline}
        </span>

        <button
          type="button"
          onClick={toggleMatrix}
          data-testid="three-mode-security-matrix-trigger"
          className="flex items-center gap-1 px-2 py-1 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-slate-200 border border-slate-800 transition-colors text-xs shrink-0"
          title="查看三态安全权限保护伞"
          aria-label="查看权限说明"
        >
          <ShieldCheck className="w-3.5 h-3.5 text-indigo-400" />
          <span className="hidden sm:inline">安全说明</span>
        </button>
      </div>
    </div>
  );
};
