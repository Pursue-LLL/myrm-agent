'use client';

import { useState } from 'react';
import { Shield, ShieldCheck, ShieldAlert, ShieldX, AlertTriangle, ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { Badge } from '@/components/primitives/badge';
import type { SkillTrap, SecurityScanSummary } from '@/store/skill/types';
import type { useTranslations } from 'next-intl';

/* ─── RequirementRow ─── */

interface RequirementRowProps {
  icon: React.ElementType;
  label: string;
  items: string[];
}

export function RequirementRow({ icon: Icon, label, items }: RequirementRowProps) {
  return (
    <div className="flex items-start gap-2">
      <Icon size={14} className="text-muted-foreground mt-0.5 shrink-0" />
      <div>
        <span className="text-xs text-muted-foreground">{label}</span>
        <div className="flex flex-wrap gap-1 mt-1">
          {items.map((item) => (
            <code key={item} className="text-xs px-1.5 py-0.5 rounded bg-muted font-mono">
              {item}
            </code>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ─── SecurityScanSection ─── */

const severityConfig: Record<string, { color: string; label: string }> = {
  critical: { color: 'text-red-600 dark:text-red-400', label: 'Critical' },
  high: { color: 'text-orange-600 dark:text-orange-400', label: 'High' },
  medium: { color: 'text-yellow-600 dark:text-yellow-400', label: 'Medium' },
  low: { color: 'text-blue-600 dark:text-blue-400', label: 'Low' },
};

function getScoreConfig(score: number) {
  if (score >= 80)
    return {
      icon: ShieldCheck,
      color: 'text-green-600 dark:text-green-400',
      bg: 'bg-green-50 dark:bg-green-950/30 border-green-200 dark:border-green-800',
    };
  if (score >= 50)
    return {
      icon: Shield,
      color: 'text-yellow-600 dark:text-yellow-400',
      bg: 'bg-yellow-50 dark:bg-yellow-950/30 border-yellow-200 dark:border-yellow-800',
    };
  if (score >= 25)
    return {
      icon: ShieldAlert,
      color: 'text-orange-600 dark:text-orange-400',
      bg: 'bg-orange-50 dark:bg-orange-950/30 border-orange-200 dark:border-orange-800',
    };
  return {
    icon: ShieldX,
    color: 'text-red-600 dark:text-red-400',
    bg: 'bg-red-50 dark:bg-red-950/30 border-red-200 dark:border-red-800',
  };
}

interface SecurityScanSectionProps {
  security: SecurityScanSummary;
  t: ReturnType<typeof useTranslations<'settings.skills'>>;
}

export function SecurityScanSection({ security, t }: SecurityScanSectionProps) {
  const [expanded, setExpanded] = useState(false);
  const { icon: ScoreIcon, color, bg } = getScoreConfig(security.score);
  const hasFindings = security.total_findings > 0;

  return (
    <div className={cn('rounded-lg border p-3', bg)}>
      <button
        className="w-full flex items-center justify-between"
        onClick={() => hasFindings && setExpanded((v) => !v)}
        disabled={!hasFindings}
        type="button"
      >
        <div className="flex items-center gap-2">
          <ScoreIcon size={18} className={color} />
          <span className={cn('text-sm font-medium', color)}>{t('card.securityScore', { score: security.score })}</span>
        </div>
        <div className="flex items-center gap-2">
          {hasFindings && (
            <span className="text-xs text-muted-foreground">
              {t('card.findings', { count: security.total_findings })}
            </span>
          )}
          {hasFindings && (
            <ChevronDown
              size={14}
              className={cn('text-muted-foreground transition-transform', expanded && 'rotate-180')}
            />
          )}
        </div>
      </button>

      {expanded && hasFindings && (
        <div className="mt-2 pt-2 border-t border-current/10 space-y-2">
          {(['critical', 'high', 'medium', 'low'] as const).map((severity) => {
            const cfg = severityConfig[severity];
            const items = security.findings.filter((f) => f.severity === severity);
            if (!cfg || items.length === 0) return null;
            return (
              <div key={severity}>
                <div className="flex items-center gap-1.5 mb-1">
                  <span className={cn('text-xs font-medium', cfg.color)}>{cfg.label}</span>
                  <span className="text-xs text-muted-foreground">({items.length})</span>
                </div>
                <div className="space-y-0.5 pl-3">
                  {items.map((finding, i) => (
                    <div key={`${finding.threat_type}-${i}`} className="text-xs text-muted-foreground">
                      <span className="font-mono text-[11px] opacity-70">[{finding.threat_type}]</span>{' '}
                      {finding.line_number != null && (
                        <span className="font-mono text-[11px] opacity-70">L{finding.line_number} </span>
                      )}
                      {finding.description}
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ─── KnownPitfallsSection ─── */

const trapSeverityConfig: Record<string, { color: string; icon: string }> = {
  critical: { color: 'text-red-600 dark:text-red-400', icon: '!!!' },
  high: { color: 'text-orange-600 dark:text-orange-400', icon: '!!' },
  medium: { color: 'text-yellow-600 dark:text-yellow-400', icon: '!' },
  low: { color: 'text-blue-600 dark:text-blue-400', icon: '~' },
};

export function KnownPitfallsSection({ traps }: { traps: SkillTrap[] }) {
  return (
    <div>
      <h4 className="text-sm font-medium mb-3 flex items-center gap-2">
        <AlertTriangle size={14} className="text-amber-500" />
        Known Pitfalls
        <Badge variant="secondary" className="text-xs">
          {traps.length}
        </Badge>
      </h4>
      <div className="space-y-2">
        {traps.map((trap, i) => {
          const cfg = trapSeverityConfig[trap.severity] || trapSeverityConfig.medium;
          return (
            <div key={`${trap.description}-${i}`} className="rounded-lg border bg-muted/30 p-2.5 text-sm">
              <div className="flex items-start gap-2">
                <span className={cn('font-mono text-xs font-bold shrink-0 mt-0.5', cfg.color)}>[{cfg.icon}]</span>
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-foreground">{trap.description}</p>
                  {trap.trigger_condition && (
                    <p className="text-xs text-muted-foreground mt-1">Trigger: {trap.trigger_condition}</p>
                  )}
                  {trap.mitigation && (
                    <p className="text-xs text-green-600 dark:text-green-400 mt-0.5">→ {trap.mitigation}</p>
                  )}
                  {trap.occurrence_count > 0 && (
                    <span className="text-[10px] text-muted-foreground/60 mt-1 inline-block">
                      x{trap.occurrence_count}
                    </span>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
