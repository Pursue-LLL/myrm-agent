'use client';

/**
 * [INPUT]
 * - store/chat/types::ContextBudget (POS: Per-turn context budget snapshot.)
 * - ./contextUsageFormat::formatTokens (POS: Compact K / M token count.)
 *
 * [OUTPUT]
 * - hasContextBreakdown: whether a budget carries any per-category token figure.
 * - ContextBreakdown: stacked usage bar with one row per context category and a health-zone badge.
 *
 * [POS]
 * Where the tokens of the context window went. Shown in the usage ring tooltip and at the top of the strategy panel.
 */

import { useTranslations } from 'next-intl';
import type { ContextBudget } from '@/store/chat/types';
import { formatTokens } from './contextUsageFormat';

export function hasContextBreakdown(budget: ContextBudget): boolean {
  return (
    budget.messages_estimated_tokens != null ||
    budget.bound_tools_overhead_tokens != null ||
    budget.other_tokens != null ||
    budget.system_prompt_tokens != null ||
    budget.memory_tokens != null ||
    budget.workspace_rules_tokens != null ||
    budget.mcp_tools_tokens != null ||
    budget.skills_tools_tokens != null ||
    budget.builtin_tools_tokens != null
  );
}

interface ContextBreakdownProps {
  budget: ContextBudget;
  className?: string;
}

export function ContextBreakdown({ budget, className }: ContextBreakdownProps) {
  const t = useTranslations('chat.contextUsage');

  if (!hasContextBreakdown(budget)) {
    return null;
  }

  // Fine-grained AgentLens 6-category rows if present, fallback to 3-bucket model
  const hasFineGrained =
    budget.system_prompt_tokens != null ||
    budget.memory_tokens != null ||
    budget.workspace_rules_tokens != null ||
    budget.mcp_tools_tokens != null ||
    budget.skills_tools_tokens != null;

  const rows = hasFineGrained
    ? [
        {
          key: 'messages',
          label: t('breakdownMessages'),
          value: budget.messages_estimated_tokens ?? 0,
          color: 'bg-primary-dark/70 dark:bg-primary-light/70',
        },
        {
          key: 'systemPrompt',
          label: t('breakdownSystemPrompt'),
          value: budget.system_prompt_tokens ?? 0,
          color: 'bg-indigo-500/80',
        },
        {
          key: 'mcpTools',
          label: t('breakdownMcpTools'),
          value: budget.mcp_tools_tokens ?? 0,
          color: 'bg-amber-500/80',
        },
        {
          key: 'skillsTools',
          label: t('breakdownSkillsTools'),
          value: budget.skills_tools_tokens ?? 0,
          color: 'bg-orange-500/80',
        },
        {
          key: 'builtinTools',
          label: t('breakdownBuiltinTools'),
          value: budget.builtin_tools_tokens ?? budget.bound_tools_overhead_tokens ?? 0,
          color: 'bg-yellow-500/80',
        },
        {
          key: 'memory',
          label: t('breakdownMemory'),
          value: budget.memory_tokens ?? 0,
          color: 'bg-emerald-500/80',
        },
        {
          key: 'workspaceRules',
          label: t('breakdownWorkspaceRules'),
          value: budget.workspace_rules_tokens ?? 0,
          color: 'bg-cyan-500/80',
        },
        {
          key: 'other',
          label: t('breakdownOther'),
          value: Math.max(
            0,
            (budget.other_tokens ?? 0) -
              (budget.system_prompt_tokens ?? 0) -
              (budget.memory_tokens ?? 0) -
              (budget.workspace_rules_tokens ?? 0),
          ),
          color: 'bg-muted-foreground/50',
        },
      ].filter((row) => row.value > 0)
    : [
        {
          key: 'messages',
          label: t('breakdownMessages'),
          value: budget.messages_estimated_tokens ?? 0,
          color: 'bg-primary-dark/70 dark:bg-primary-light/70',
        },
        {
          key: 'tools',
          label: t('breakdownTools'),
          value: budget.bound_tools_overhead_tokens ?? 0,
          color: 'bg-amber-500/80',
        },
        {
          key: 'other',
          label: t('breakdownOther'),
          value: budget.other_tokens ?? 0,
          color: 'bg-muted-foreground/50',
        },
      ].filter((row) => row.value > 0);

  const segmentTotal = rows.reduce((sum, row) => sum + row.value, 0) || budget.current_tokens;

  return (
    <div data-testid="context-budget-breakdown" className={className}>
      <div className="flex items-center justify-between text-[10px] font-medium text-muted-foreground mb-1.5">
        <span>{t('breakdownTitle')}</span>
        <span
          className={`text-[9px] px-1.5 py-0.2 rounded font-medium ${
            budget.usage_percent < 50
              ? 'text-emerald-600 bg-emerald-500/10'
              : budget.usage_percent < 75
                ? 'text-amber-600 bg-amber-500/10'
                : 'text-red-500 bg-red-500/10'
          }`}
          title={t('optimalHealthLineDesc')}
        >
          {budget.usage_percent < 50
            ? t('optimalZone')
            : budget.usage_percent < 75
              ? t('warningZone')
              : t('criticalZone')}
        </span>
      </div>
      <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-muted/40 mb-2">
        {rows.map((row) => (
          <span
            key={row.key}
            className={`${row.color} h-full`}
            style={{ width: `${Math.max(0, Math.min(100, (row.value / segmentTotal) * 100))}%` }}
            aria-hidden="true"
          />
        ))}
      </div>
      <div className="flex flex-col gap-1">
        {rows.map((row) => (
          <div key={row.key} className="flex items-center justify-between gap-3 text-[10px] tabular-nums">
            <span className="text-muted-foreground">{row.label}</span>
            <span className="text-foreground font-medium">{formatTokens(row.value)}</span>
          </div>
        ))}
        <div className="flex items-center justify-between gap-3 text-[10px] tabular-nums pt-1 border-t border-border/40">
          <span className="text-muted-foreground">{t('breakdownTotal')}</span>
          <span className="text-foreground font-semibold">{formatTokens(budget.current_tokens)}</span>
        </div>
      </div>
    </div>
  );
}
