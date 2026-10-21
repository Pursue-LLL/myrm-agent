'use client';

import { useState } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/primitives/button';

interface AuditFinding {
  checker: string;
  severity: string;
  title: string;
  description: string;
  recommendation: string;
  source_location: string;
}

export interface AuditResult {
  score: number;
  risk_level: string;
  findings: AuditFinding[];
  total_findings: number;
  finding_counts: Record<string, number>;
}

const RISK_LEVEL_STYLES: Record<string, { bg: string; text: string; border: string }> = {
  safe: { bg: 'bg-emerald-500/10', text: 'text-emerald-600 dark:text-emerald-400', border: 'border-emerald-500/30' },
  low: { bg: 'bg-blue-500/10', text: 'text-blue-600 dark:text-blue-400', border: 'border-blue-500/30' },
  medium: { bg: 'bg-amber-500/10', text: 'text-amber-600 dark:text-amber-400', border: 'border-amber-500/30' },
  high: { bg: 'bg-orange-500/10', text: 'text-orange-600 dark:text-orange-400', border: 'border-orange-500/30' },
  critical: { bg: 'bg-destructive/10', text: 'text-destructive', border: 'border-destructive/30' },
};

const SEVERITY_BORDER: Record<string, string> = {
  critical: 'border-l-destructive/70',
  high: 'border-l-orange-500/70',
  medium: 'border-l-amber-500/70',
  low: 'border-l-blue-500/70',
  info: 'border-l-muted',
};

const ALL_CHECKERS = [
  'tool_exposure',
  'mcp_auth',
  'skill_aggregate',
  'subagent_risk',
  'cron_risk',
  'policy_gap',
] as const;

type CheckerKey = (typeof ALL_CHECKERS)[number];

const CHECKER_ICON_COLORS: Record<CheckerKey, string> = {
  tool_exposure: 'text-orange-500',
  mcp_auth: 'text-violet-500',
  skill_aggregate: 'text-sky-500',
  subagent_risk: 'text-rose-500',
  cron_risk: 'text-amber-500',
  policy_gap: 'text-slate-500',
};

interface PolicyFixConfig {
  type: 'toggle' | 'navigate';
  targetId: string;
}

const POLICY_FIX_MAP: Record<string, PolicyFixConfig> = {
  'Domain HITL approval not enabled': { type: 'toggle', targetId: 'domain-hitl-switch' },
  'Filesystem tools enabled without path policy': { type: 'navigate', targetId: 'allowed-roots-section' },
  'Network tools enabled without network policy': { type: 'navigate', targetId: 'network-allowlist-section' },
  'No capability restrictions configured': { type: 'navigate', targetId: 'capabilities-section' },
};

function groupFindingsByChecker(findings: AuditFinding[]): Record<string, AuditFinding[]> {
  const groups: Record<string, AuditFinding[]> = {};
  for (const f of findings) {
    if (!groups[f.checker]) {
      groups[f.checker] = [];
    }
    groups[f.checker].push(f);
  }
  return groups;
}

export function HealthScoreCard({
  result,
  loading,
  t,
  onFixToggle,
}: {
  result: AuditResult | null;
  loading: boolean;
  t: (key: string, values?: Record<string, string | number>) => string;
  onFixToggle?: (targetId: string) => void;
}) {
  const [expandedChecker, setExpandedChecker] = useState<string | null>(null);

  if (loading) {
    return (
      <div className="rounded-xl border border-border bg-card p-4 animate-pulse">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-full bg-muted" />
          <div className="space-y-2 flex-1">
            <div className="h-4 w-32 bg-muted rounded" />
            <div className="h-3 w-48 bg-muted rounded" />
          </div>
        </div>
      </div>
    );
  }

  if (!result) {
    return null;
  }

  const style = RISK_LEVEL_STYLES[result.risk_level] || RISK_LEVEL_STYLES.medium;
  const grouped = groupFindingsByChecker(result.findings);

  return (
    <div className={cn('rounded-xl border bg-card p-4 space-y-3', style.border)}>
      <div className="flex items-center gap-3">
        <div
          className={cn(
            'flex items-center justify-center h-10 w-10 rounded-full text-sm font-bold',
            style.bg,
            style.text,
          )}
        >
          {result.score}
        </div>
        <div>
          <h3 className="text-sm font-medium text-foreground">{t('healthScoreTitle')}</h3>
          <p className={cn('text-xs font-medium capitalize', style.text)}>{result.risk_level}</p>
        </div>
      </div>

      <div className="grid gap-1.5 pt-2 border-t border-border/50">
        {ALL_CHECKERS.map((checker) => {
          const issues = grouped[checker] || [];
          const hasIssues = issues.length > 0;
          const isExpanded = expandedChecker === checker;

          return (
            <div key={checker}>
              <button
                type="button"
                disabled={!hasIssues}
                onClick={() => {
                  if (!hasIssues) {
                    return;
                  }
                  setExpandedChecker(isExpanded ? null : checker);
                }}
                className={cn(
                  'w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs transition-colors',
                  hasIssues ? 'bg-muted/50 hover:bg-muted cursor-pointer' : 'cursor-default',
                )}
              >
                <span className={cn('font-medium', CHECKER_ICON_COLORS[checker])}>{t(`checkers.${checker}`)}</span>
                <span
                  className={cn(
                    'text-xs font-medium',
                    hasIssues ? 'text-amber-600 dark:text-amber-400' : 'text-emerald-600 dark:text-emerald-400',
                  )}
                >
                  {hasIssues ? t('checkerIssues', { count: issues.length }) : t('checkerPass')}
                </span>
              </button>

              {isExpanded && hasIssues && (
                <div className="ml-3 mt-1 mb-2 space-y-1.5">
                  {issues.map((finding, idx) => {
                    const fixConfig = checker === 'policy_gap' ? POLICY_FIX_MAP[finding.title] : undefined;
                    return (
                      <div
                        key={idx}
                        className={cn(
                          'text-xs space-y-0.5 pl-2 border-l-2 flex items-start justify-between gap-2',
                          SEVERITY_BORDER[finding.severity] || 'border-l-muted',
                        )}
                      >
                        <div className="min-w-0 flex-1">
                          <p className="font-medium text-foreground">{finding.title}</p>
                          <p className="text-muted-foreground">{finding.recommendation}</p>
                        </div>
                        {fixConfig && onFixToggle && (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="shrink-0 h-6 px-2 text-[10px] text-primary hover:text-primary"
                            onClick={(e) => {
                              e.stopPropagation();
                              onFixToggle(fixConfig.targetId);
                            }}
                          >
                            {fixConfig.type === 'toggle' ? t('fixAction') : t('configureAction')}
                          </Button>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
