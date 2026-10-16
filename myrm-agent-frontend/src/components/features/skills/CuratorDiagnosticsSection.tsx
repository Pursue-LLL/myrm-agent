'use client';

import { memo, useMemo } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { Archive, Loader2, RotateCcw, ShieldAlert, ShieldCheck } from 'lucide-react';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import type { SkillDoctorDiagnosticsResponse, SkillDoctorFindingItem, SkillRemediationAction } from '@/services/skill';

const TYPE_LABEL_KEYS = {
  wrong_but_frequent: 'doctor.typeWrongButFrequent',
  hoarding_bloat: 'doctor.typeHoarding',
  stale_pinned: 'doctor.typeStalePinned',
} as const satisfies Record<SkillDoctorFindingItem['finding_type'], string>;

interface CuratorDiagnosticsSectionProps {
  diagnostics: SkillDoctorDiagnosticsResponse;
  remediatingSkill: string | null;
  onRemediate: (skillName: string, action: SkillRemediationAction) => void;
}

const CuratorDiagnosticsSection = memo(
  ({ diagnostics, remediatingSkill, onRemediate }: CuratorDiagnosticsSectionProps) => {
    const t = useTranslations('settings.skills.curator');
    const tCard = useTranslations('settings.skills.card');
    const locale = useLocale();
    const percentFormat = useMemo(
      () => new Intl.NumberFormat(locale, { style: 'percent', maximumFractionDigits: 1 }),
      [locale],
    );

    const describeFinding = (finding: SkillDoctorFindingItem): string => {
      switch (finding.finding_type) {
        case 'wrong_but_frequent':
          return t('doctor.findingWrongButFrequent', {
            count: finding.details.observed_count,
            rate: percentFormat.format(finding.success_rate),
          });
        case 'stale_pinned':
          return t('doctor.findingStalePinned', { days: finding.details.days_inactive });
        case 'hoarding_bloat':
          return t('doctor.findingHoarding', {
            active: finding.details.active_count,
            max: finding.details.max_skills,
            excess: finding.details.excess,
          });
      }
    };

    const hasFindings = diagnostics.findings.length > 0;

    return (
      <div
        data-testid="curator-diagnostics"
        className={`p-3.5 rounded-lg border transition-all ${
          hasFindings
            ? 'bg-amber-500/5 dark:bg-amber-500/10 border-amber-500/30'
            : 'bg-emerald-500/5 dark:bg-emerald-500/10 border-emerald-500/20'
        }`}
      >
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            {hasFindings ? (
              <ShieldAlert className="h-4 w-4 text-amber-500" />
            ) : (
              <ShieldCheck className="h-4 w-4 text-emerald-500" />
            )}
            <span className="text-xs font-semibold">
              {hasFindings
                ? t('doctor.titleAttention', { count: diagnostics.findings.length })
                : t('doctor.titleHealthy')}
            </span>
          </div>
          <Badge
            variant="outline"
            className={`text-[11px] font-mono px-2 py-0.5 ${
              diagnostics.health_score >= 85
                ? 'border-emerald-500/30 text-emerald-700 dark:text-emerald-400 bg-emerald-500/10'
                : 'border-amber-500/30 text-amber-800 dark:text-amber-400 bg-amber-500/10'
            }`}
          >
            {diagnostics.health_score}/100
          </Badge>
        </div>

        {!hasFindings ? (
          <p className="text-xs text-muted-foreground">{t('doctor.allHealthyDesc')}</p>
        ) : (
          <div className="space-y-2 mt-2.5">
            {diagnostics.findings.map((f, idx) => {
              const busy = remediatingSkill === f.skill_name;
              return (
                <div
                  key={`${f.skill_name}-${idx}`}
                  data-testid="curator-diagnostic-row"
                  className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 p-2.5 rounded bg-background/60 border border-border/60 text-xs"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      {f.finding_type !== 'hoarding_bloat' && (
                        <span className="font-medium text-foreground">{f.skill_name}</span>
                      )}
                      {f.pinned && (
                        <Badge variant="secondary" className="text-[10px] h-4 px-1.5 bg-muted">
                          {tCard('pinned')}
                        </Badge>
                      )}
                      <Badge
                        variant="outline"
                        className={`text-[10px] h-4 px-1.5 ${
                          f.severity === 'critical'
                            ? 'border-destructive/40 text-red-700 dark:text-red-400 bg-destructive/10'
                            : 'border-amber-500/40 text-amber-800 dark:text-amber-400 bg-amber-500/10'
                        }`}
                      >
                        {t(TYPE_LABEL_KEYS[f.finding_type])}
                      </Badge>
                    </div>
                    <p className="text-[11px] text-muted-foreground">{describeFinding(f)}</p>
                  </div>

                  {f.finding_type !== 'hoarding_bloat' && (
                    <div className="flex items-center gap-1.5 shrink-0">
                      {f.pinned && (
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={busy}
                          onClick={() => onRemediate(f.skill_name, 'unpin_and_archive')}
                          className="h-6 px-2 text-[11px] gap-1 border-amber-500/30 hover:bg-amber-500/10"
                        >
                          {busy ? (
                            <Loader2 className="h-3 w-3 animate-spin" />
                          ) : (
                            <Archive className="h-3 w-3 text-amber-500" />
                          )}
                          <span>{t('doctor.actionUnpinArchive')}</span>
                        </Button>
                      )}
                      {!f.pinned && f.finding_type === 'wrong_but_frequent' && (
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={busy}
                          onClick={() => onRemediate(f.skill_name, 'archive')}
                          className="h-6 px-2 text-[11px] gap-1 border-amber-500/30 hover:bg-amber-500/10"
                        >
                          {busy ? (
                            <Loader2 className="h-3 w-3 animate-spin" />
                          ) : (
                            <Archive className="h-3 w-3 text-amber-500" />
                          )}
                          <span>{t('doctor.actionArchive')}</span>
                        </Button>
                      )}
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={busy}
                        onClick={() => onRemediate(f.skill_name, 'reset_stats')}
                        className="h-6 px-2 text-[11px] gap-1 text-muted-foreground hover:text-foreground"
                        title={t('doctor.actionResetTooltip')}
                      >
                        <RotateCcw className="h-3 w-3" />
                        <span>{t('doctor.actionReset')}</span>
                      </Button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    );
  },
);

CuratorDiagnosticsSection.displayName = 'CuratorDiagnosticsSection';

export default CuratorDiagnosticsSection;
