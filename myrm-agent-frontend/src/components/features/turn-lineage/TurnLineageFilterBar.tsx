import React from 'react';
import {
  Layers,
  User,
  Cpu,
  ArrowRightLeft,
  PanelRightClose,
  PanelRightOpen,
} from 'lucide-react';
import { useTurnLineageStore } from './useTurnLineageStore';
import { LineageFilterMode } from './turnLineageTypes';
import { filterTurns } from './turnLineageEngine';

export const TurnLineageFilterBar: React.FC = () => {
  const {
    turns,
    filterMode,
    setFilterMode,
    isRailExpanded,
    toggleRailExpanded,
  } = useTurnLineageStore();

  const filtered = filterTurns(turns, filterMode);

  const filterButtons: Array<{
    id: LineageFilterMode;
    label: string;
    icon: React.ComponentType<{ className?: string }>;
  }> = [
    { id: 'all', label: '全部轮次', icon: Layers },
    { id: 'user_only', label: '仅人工指令', icon: User },
    { id: 'automated_only', label: '定时自动化', icon: Cpu },
    { id: 'handoff_only', label: 'Agent 移交', icon: ArrowRightLeft },
  ];

  return (
    <div
      data-testid="turn-lineage-filter-bar"
      className="flex items-center justify-between px-3 py-2 bg-slate-950/80 backdrop-blur border-b border-slate-800 text-xs text-slate-300 select-none"
    >
      {/* 筛选按钮组 */}
      <div className="flex items-center gap-1.5">
        <span className="text-[11px] text-slate-500 font-mono hidden md:inline">
          溯源审计：
        </span>
        <div className="flex items-center bg-slate-900 border border-slate-800 rounded-xl p-0.5">
          {filterButtons.map((btn) => {
            const Icon = btn.icon;
            const isSelected = filterMode === btn.id;
            return (
              <button
                key={btn.id}
                type="button"
                onClick={() => setFilterMode(btn.id)}
                className={`flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium transition-all ${
                  isSelected
                    ? 'bg-indigo-600 text-white shadow-xs'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
                title={btn.label}
              >
                <Icon className="w-3 h-3" />
                <span>{btn.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* 轮次计数与时间轴轨道开关 */}
      <div className="flex items-center gap-3">
        <span className="text-[11px] font-mono text-slate-400">
          显示 <strong className="text-slate-100">{filtered.length}</strong> / {turns.length} 轮
        </span>

        <button
          type="button"
          onClick={toggleRailExpanded}
          className="flex items-center gap-1 px-2 py-1 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-400 hover:text-white transition-colors text-xs"
          title={isRailExpanded ? '收起溯源时间轴' : '展开溯源时间轴'}
          aria-label={isRailExpanded ? '收起时间轴' : '展开时间轴'}
        >
          {isRailExpanded ? (
            <PanelRightClose className="w-3.5 h-3.5" />
          ) : (
            <PanelRightOpen className="w-3.5 h-3.5" />
          )}
          <span className="hidden sm:inline">时间轴</span>
        </button>
      </div>
    </div>
  );
};
