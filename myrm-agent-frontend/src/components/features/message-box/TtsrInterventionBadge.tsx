/**
 * [INPUT]
 * - lib/utils/classnameUtils::cn (POS: CSS 类名条件拼接工具)
 * 
 * [OUTPUT]
 * - TtsrInterventionBadge: 渲染流规则拦截与动态防御提示徽章，提供友好无感的用户安全保障反馈
 * 
 * [POS]
 * 消息气泡功能组件层。负责将流式中途触发的零税安全干预优雅呈现给终端用户，避免技术细节泄露。
 */

import React, { useState } from 'react';
import { ShieldAlert, Sparkles, ChevronDown, ChevronRight, RotateCcw } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';

export interface TtsrInterventionBadgeProps {
  ruleId: string;
  ruleName: string;
  reminder: string;
  target?: 'assistant' | 'thinking' | 'tool_args' | 'all';
  retryCount?: number;
  maxRetries?: number;
  timestamp?: string | number | Date;
  className?: string;
}

const formatTimestamp = (raw?: string | number | Date): string | null => {
  if (!raw) {
    return null;
  }
  try {
    const date = raw instanceof Date ? raw : new Date(raw);
    if (Number.isNaN(date.getTime())) {
      return null;
    }
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return null;
  }
};

const resolveScopeLabel = (target?: string): string => {
  switch (target) {
    case 'tool_args':
      return 'Command & Execution Safety';
    case 'assistant':
      return 'Content & Sensitive Data Safety';
    case 'thinking':
      return 'Reasoning & Policy Compliance';
    default:
      return 'Active Stream Safety';
  }
};

export const TtsrInterventionBadge: React.FC<TtsrInterventionBadgeProps> = ({
  ruleId,
  ruleName,
  reminder,
  target = 'all',
  retryCount = 1,
  maxRetries = 2,
  timestamp,
  className,
}) => {
  const [expanded, setExpanded] = useState(false);
  const formattedTime = formatTimestamp(timestamp);
  const detailsId = `ttsr-details-${ruleId}`;
  const scopeLabel = resolveScopeLabel(target);

  return (
    <output
      aria-live="polite"
      className={cn(
        'group relative my-2 mx-auto max-w-3xl w-full rounded-lg border px-3.5 py-2.5 transition-all duration-200',
        'border-amber-500/25 bg-amber-500/[0.04] text-amber-950 hover:border-amber-500/40',
        'dark:border-amber-400/20 dark:bg-amber-400/[0.03] dark:text-amber-100 dark:hover:border-amber-400/35',
        'shadow-xs backdrop-blur-xs',
        className
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-amber-500/15 text-amber-600 dark:bg-amber-400/20 dark:text-amber-300">
            <ShieldAlert className="h-3 w-3" aria-hidden="true" />
          </div>

          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-xs font-medium tracking-tight text-amber-800 dark:text-amber-200">
              {ruleName || 'Active Safety Guard'}
            </span>

            <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-mono font-medium bg-amber-500/10 text-amber-700 dark:bg-amber-400/15 dark:text-amber-300">
              <Sparkles className="h-2.5 w-2.5" aria-hidden="true" />
              <span>Active Defense</span>
            </span>

            {retryCount > 0 && (
              <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-mono text-muted-foreground bg-muted">
                <RotateCcw className="h-2.5 w-2.5" aria-hidden="true" />
                <span>
                  Auto-Corrected ({retryCount}/{maxRetries})
                </span>
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {formattedTime && (
            <span className="text-[10px] text-muted-foreground/70 font-mono tracking-tight hidden sm:inline">
              {formattedTime}
            </span>
          )}

          {reminder && (
            <button
              type="button"
              onClick={() => setExpanded((prev) => !prev)}
              aria-expanded={expanded}
              aria-controls={detailsId}
              className={cn(
                'inline-flex items-center gap-1 text-[11px] font-medium text-amber-700/80 hover:text-amber-900',
                'dark:text-amber-300/80 dark:hover:text-amber-100 transition-colors cursor-pointer'
              )}
            >
              <span>{expanded ? 'Hide Safety Guidance' : 'View Safety Guidance'}</span>
              {expanded ? (
                <ChevronDown className="h-3 w-3" aria-hidden="true" />
              ) : (
                <ChevronRight className="h-3 w-3" aria-hidden="true" />
              )}
            </button>
          )}
        </div>
      </div>

      {expanded && reminder && (
        <div
          id={detailsId}
          className="mt-2.5 pt-2 border-t border-amber-500/15 dark:border-amber-400/10 text-xs leading-relaxed text-amber-900/90 dark:text-amber-200/90 font-mono bg-amber-500/5 dark:bg-amber-400/5 p-2 rounded-md"
        >
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">
            Protected Scope: {scopeLabel}
          </div>
          <p className="whitespace-pre-wrap">{reminder}</p>
        </div>
      )}
    </output>
  );
};
