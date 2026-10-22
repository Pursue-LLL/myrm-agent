/**
 * [INPUT] ActiveSubagentSwimlane list from useInFlightSteerStore
 * [OUTPUT] ActiveSubagentSwimlanesBar (Horizontal swimlane strip showing concurrently active subagents with quick steer trigger)
 * [POS] Features -> Chat Window -> In-Flight Steer -> SwimlanesBar
 */

'use client';

import React from 'react';
import { Bot, Compass, Zap, Clock } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { useInFlightSteerStore } from './useInFlightSteerStore';
import { InFlightSteerPopover } from './InFlightSteerPopover';

export interface ActiveSubagentSwimlanesBarProps {
  className?: string;
}

export const ActiveSubagentSwimlanesBar: React.FC<ActiveSubagentSwimlanesBarProps> = ({
  className,
}) => {
  const { swimlanes, activePopoverSubagentId, openSteerPopover, closeSteerPopover } =
    useInFlightSteerStore();

  if (swimlanes.length === 0) {
    return null;
  }

  const activeSubagent = swimlanes.find((s) => s.id === activePopoverSubagentId);

  return (
    <div
      className={cn(
        'relative w-full overflow-x-auto py-2 px-3 bg-neutral-50/90 dark:bg-neutral-900/90 border-b border-neutral-200/80 dark:border-neutral-800/80 backdrop-blur-sm',
        className,
      )}
    >
      <div className="flex items-center gap-2.5 min-w-max">
        <div className="flex items-center gap-1.5 px-2 py-1 text-[11px] font-semibold text-neutral-500 dark:text-neutral-400 uppercase tracking-wider">
          <Bot size={13} className="text-indigo-500" />
          <span>活跃专家泳道 ({swimlanes.length})</span>
        </div>

        {swimlanes.map((subagent) => {
          const isRunning = subagent.status === 'running';
          const isStopped = subagent.status === 'stopped';
          const isSelected = activePopoverSubagentId === subagent.id;

          return (
            <div
              key={subagent.id}
              className={cn(
                'relative flex items-center gap-2 pl-2.5 pr-2 py-1 rounded-lg border text-xs transition-all shadow-sm',
                isSelected
                  ? 'border-indigo-500 bg-indigo-50/60 dark:bg-indigo-950/40'
                  : 'border-neutral-200 dark:border-neutral-750 bg-white dark:bg-neutral-850 hover:border-neutral-300 dark:hover:border-neutral-600',
              )}
            >
              {/* Status Pulse */}
              <div className="relative flex items-center justify-center">
                <span
                  className={cn(
                    'w-2 h-2 rounded-full',
                    isRunning
                      ? 'bg-emerald-500'
                      : isStopped
                      ? 'bg-neutral-400'
                      : 'bg-amber-500',
                  )}
                />
                {isRunning ? (
                  <span className="absolute w-3.5 h-3.5 rounded-full bg-emerald-500/30 animate-ping" />
                ) : null}
              </div>

              {/* Info */}
              <div className="flex flex-col min-w-0 max-w-[160px]">
                <div className="flex items-center gap-1">
                  <span className="font-semibold text-neutral-800 dark:text-neutral-200 truncate">
                    {subagent.name}
                  </span>
                  <span className="px-1 py-0.1 text-[9px] rounded bg-neutral-100 dark:bg-neutral-800 text-neutral-500 font-mono">
                    {subagent.role}
                  </span>
                </div>
                <span className="text-[10px] text-neutral-400 truncate">
                  {subagent.currentStep}
                </span>
              </div>

              {/* Metrics */}
              <div className="flex items-center gap-1.5 text-[10px] text-neutral-400 font-mono border-l border-neutral-100 dark:border-neutral-750 pl-2">
                <span className="inline-flex items-center gap-0.5" title="消耗 Tokens">
                  <Zap size={10} className="text-amber-500" />
                  {subagent.tokensUsed > 1000
                    ? `${(subagent.tokensUsed / 1000).toFixed(1)}k`
                    : subagent.tokensUsed}
                </span>
                <span className="inline-flex items-center gap-0.5" title="运行耗时">
                  <Clock size={10} />
                  {subagent.elapsedSeconds}s
                </span>
              </div>

              {/* Steer Button */}
              <button
                type="button"
                onClick={() => {
                  if (isSelected) {
                    closeSteerPopover();
                  } else {
                    openSteerPopover(subagent.id);
                  }
                }}
                className={cn(
                  'inline-flex items-center gap-1 px-1.5 py-1 rounded text-[11px] font-medium transition-colors',
                  isSelected
                    ? 'bg-indigo-600 text-white'
                    : 'text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-950/40',
                )}
                title="动态追加纠偏指令"
              >
                <Compass size={12} />
                <span>纠偏</span>
              </button>
            </div>
          );
        })}
      </div>

      {/* Floating Popover Container */}
      {activeSubagent ? (
        <div className="absolute top-full left-4 mt-2 z-50">
          <InFlightSteerPopover
            subagent={activeSubagent}
            onClose={closeSteerPopover}
          />
        </div>
      ) : null}
    </div>
  );
};

ActiveSubagentSwimlanesBar.displayName = 'ActiveSubagentSwimlanesBar';
