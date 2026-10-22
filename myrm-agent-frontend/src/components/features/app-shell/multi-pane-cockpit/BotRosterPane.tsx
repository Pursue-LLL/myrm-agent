import React from 'react';
import {
  Users,
  ChevronLeft,
  ChevronRight,
  ArrowRight,
  Columns2,
  Columns3,
  Columns4,
} from 'lucide-react';
import { useMultiPaneCockpitStore } from './useMultiPaneCockpitStore';
import { ActiveBotPulseBadge } from './ActiveBotPulseBadge';
import type { CockpitPaneMode } from './multiPaneCockpitTypes';

export const BotRosterPane: React.FC = () => {
  const {
    bots,
    selectedBotId,
    paneMode,
    isRosterCollapsed,
    selectBot,
    toggleRosterCollapse,
    setPaneMode,
    handoffToBotSession,
  } = useMultiPaneCockpitStore();

  return (
    <aside
      aria-label="智能体团队名册"
      className={`flex flex-col border-r border-slate-800 bg-slate-900/95 transition-all duration-200 ${
        isRosterCollapsed ? 'w-16' : 'w-72'
      }`}
    >
      <div className="flex h-12 items-center justify-between border-b border-slate-800 px-3">
        {!isRosterCollapsed && (
          <div className="flex items-center space-x-2">
            <Users className="h-4 w-4 text-blue-400" />
            <span className="text-xs font-semibold text-slate-100">智能体团队 ({bots.length})</span>
          </div>
        )}
        <button
          type="button"
          onClick={toggleRosterCollapse}
          className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
          aria-label={isRosterCollapsed ? '展开名册' : '收起名册'}
        >
          {isRosterCollapsed ? (
            <ChevronRight className="h-4 w-4" />
          ) : (
            <ChevronLeft className="h-4 w-4" />
          )}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
        {bots.map((bot) => {
          const isSelected = bot.id === selectedBotId;
          const isActive = bot.pulse.isActive;

          if (isRosterCollapsed) {
            return (
              <button
                key={bot.id}
                type="button"
                onClick={() => {
                  selectBot(bot.id);
                }}
                className={`flex w-full justify-center rounded-lg p-2 transition-colors ${
                  isSelected ? 'bg-blue-600/20' : 'hover:bg-slate-800'
                }`}
                title={`${bot.name} (${bot.role})`}
              >
                <ActiveBotPulseBadge pulse={bot.pulse} avatarIconName={bot.avatarIconName} size="sm" />
              </button>
            );
          }

          return (
            <div
              key={bot.id}
              className={`group flex flex-col rounded-lg border p-2.5 transition-all ${
                isSelected
                  ? 'border-blue-500/50 bg-blue-950/20 shadow-sm'
                  : 'border-slate-800 bg-slate-850/60 hover:border-slate-700 hover:bg-slate-800/40'
              }`}
            >
              <div className="flex items-center justify-between">
                <button
                  type="button"
                  onClick={() => {
                    selectBot(bot.id);
                  }}
                  className="flex flex-1 items-center space-x-2.5 text-left"
                >
                  <ActiveBotPulseBadge
                    pulse={bot.pulse}
                    avatarIconName={bot.avatarIconName}
                    size="md"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center space-x-1.5">
                      <span className="truncate text-xs font-semibold text-slate-100">
                        {bot.name}
                      </span>
                      {isActive && (
                        <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-400" />
                      )}
                    </div>
                    <p className="truncate text-[11px] text-slate-400">{bot.role}</p>
                  </div>
                </button>

                {isActive && (
                  <button
                    type="button"
                    onClick={() => {
                      handoffToBotSession(bot.id);
                    }}
                    className="inline-flex items-center space-x-0.5 rounded bg-blue-500/10 px-1.5 py-1 text-[10px] font-medium text-blue-400 hover:bg-blue-500/20"
                    title="穿梭直达任务现场"
                  >
                    <span>穿梭</span>
                    <ArrowRight className="h-3 w-3" />
                  </button>
                )}
              </div>

              {isActive && bot.pulse.currentTaskTitle && (
                <div className="mt-2 rounded bg-slate-900/90 p-1.5 text-[10px] text-slate-300 border border-slate-800">
                  <div className="flex items-center justify-between text-slate-400">
                    <span className="truncate">{bot.pulse.currentTaskTitle}</span>
                    {bot.pulse.progressPercent !== undefined && (
                      <span className="font-mono text-blue-400">{bot.pulse.progressPercent}%</span>
                    )}
                  </div>
                  {bot.pulse.progressPercent !== undefined && (
                    <div className="mt-1 h-1 w-full overflow-hidden rounded bg-slate-800">
                      <div
                        className="h-full bg-blue-500 transition-all"
                        style={{ width: `${bot.pulse.progressPercent}%` }}
                      />
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {!isRosterCollapsed && (
        <div className="border-t border-slate-800 p-2.5">
          <div className="flex items-center justify-between text-[11px] text-slate-400 mb-1.5">
            <span>分栏布局</span>
            <span className="font-mono text-slate-300">{paneMode}</span>
          </div>
          <div className="grid grid-cols-3 gap-1">
            {(['two_pane', 'three_pane', 'four_pane'] as CockpitPaneMode[]).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => {
                  setPaneMode(mode);
                }}
                className={`inline-flex items-center justify-center space-x-1 rounded py-1 text-[10px] transition-colors ${
                  paneMode === mode
                    ? 'bg-blue-600 text-white font-medium'
                    : 'bg-slate-800 text-slate-400 hover:text-slate-200'
                }`}
              >
                {mode === 'two_pane' && <Columns2 className="h-3 w-3" />}
                {mode === 'three_pane' && <Columns3 className="h-3 w-3" />}
                {mode === 'four_pane' && <Columns4 className="h-3 w-3" />}
                <span>
                  {mode === 'two_pane' ? '2 栏' : mode === 'three_pane' ? '3 栏' : '4 栏'}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </aside>
  );
};
