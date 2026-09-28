'use client';

import { memo, useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import {
  AlertTriangle,
  ShieldCheck,
  ShieldAlert,
  Wrench,
  ChevronDown,
  ChevronUp,
  FileCode,
} from 'lucide-react';
import { Badge } from '@/components/primitives/badge';
import type { LocalSkillPreviewItem } from '@/store/skill/types';

interface LocalSkillPreviewCardProps {
  skill: LocalSkillPreviewItem;
  isSelected: boolean;
  onToggle: (skillId: string) => void;
  allowUntrusted?: boolean;
}

export const LocalSkillPreviewCard = memo(
  ({ skill, isSelected, onToggle, allowUntrusted = false }: LocalSkillPreviewCardProps) => {
    const t = useTranslations('settings.skills.local');
    const [isFindingsExpanded, setIsFindingsExpanded] = useState(false);

    const score = skill.security_score ?? (skill.security?.score ?? (skill.is_safe ? 100 : 40));
    const isSecurityBlocked = score < 50;
    const isActionBlocked = isSecurityBlocked && !allowUntrusted;
    const findings = skill.security?.findings ?? [];

    const handleCardClick = useCallback(() => {
      if (isActionBlocked) {
        return;
      }
      if (skill.skill_id) {
        onToggle(skill.skill_id);
      }
    }, [isActionBlocked, skill.skill_id, onToggle]);

    const handleCheckboxChange = useCallback(
      (e: React.ChangeEvent<HTMLInputElement>) => {
        e.stopPropagation();
        if (isActionBlocked) {
          return;
        }
        if (skill.skill_id) {
          onToggle(skill.skill_id);
        }
      },
      [isActionBlocked, skill.skill_id, onToggle],
    );

    const toggleFindings = useCallback((e: React.MouseEvent) => {
      e.stopPropagation();
      setIsFindingsExpanded((prev) => !prev);
    }, []);

    return (
      <div
        data-testid={`preview-skill-card-${skill.name}`}
        className={`rounded-lg border p-3 shadow-xs transition-colors ${
          isActionBlocked
            ? 'border-destructive/40 bg-destructive/5 dark:bg-destructive/10 cursor-not-allowed opacity-90'
            : isSecurityBlocked
              ? isSelected
                ? 'border-amber-500/60 bg-amber-500/10 dark:bg-amber-500/15 cursor-pointer'
                : 'border-amber-500/40 bg-amber-500/5 dark:bg-amber-500/10 hover:border-amber-500/60 cursor-pointer'
              : isSelected
                ? 'border-primary/60 bg-primary/5 dark:bg-primary/10 cursor-pointer'
                : 'border-border bg-card hover:border-border/90 cursor-pointer'
        }`}
        onClick={handleCardClick}
      >
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-start gap-2.5 min-w-0 flex-1">
            <input
              type="checkbox"
              data-testid={`preview-skill-checkbox-${skill.name}`}
              checked={isSelected && !isActionBlocked}
              disabled={isActionBlocked}
              onChange={handleCheckboxChange}
              className={`mt-1 h-3.5 w-3.5 rounded border-gray-300 text-primary focus:ring-primary shrink-0 ${
                isActionBlocked ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'
              }`}
              onClick={(e) => e.stopPropagation()}
            />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-medium text-sm text-foreground">{skill.name}</span>
                <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                  v{skill.version}
                </Badge>
                {skill.category && (
                  <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                    {skill.category}
                  </Badge>
                )}
                {skill.is_conflicted ? (
                  <Badge variant="destructive" className="text-[10px] px-1.5 py-0 gap-1">
                    <AlertTriangle className="h-2.5 w-2.5" />
                    {t('previewDialog.conflicted')}
                  </Badge>
                ) : null}

                {/* Preflight Security Gate Scoring Badge */}
                {isSecurityBlocked ? (
                  <Badge
                    variant="destructive"
                    data-testid="security-score-badge-blocked"
                    className="text-[10px] px-1.5 py-0 gap-1"
                  >
                    <ShieldAlert className="h-2.5 w-2.5" />
                    <span>{score}分 · {t('previewDialog.securityBlocked')}</span>
                  </Badge>
                ) : score >= 80 ? (
                  <Badge
                    variant="outline"
                    data-testid="security-score-badge-safe"
                    className="text-[10px] px-1.5 py-0 border-emerald-500/40 text-emerald-600 dark:text-emerald-400 gap-1"
                  >
                    <ShieldCheck className="h-2.5 w-2.5" />
                    <span>{score}分 · {t('previewDialog.safe')}</span>
                  </Badge>
                ) : (
                  <Badge
                    variant="outline"
                    data-testid="security-score-badge-warning"
                    className="text-[10px] px-1.5 py-0 border-amber-500/40 text-amber-600 dark:text-amber-400 gap-1"
                  >
                    <ShieldAlert className="h-2.5 w-2.5" />
                    <span>{score}分 · {t('previewDialog.warning')}</span>
                  </Badge>
                )}
              </div>

              {skill.description && (
                <p className="text-xs text-muted-foreground mt-1 line-clamp-2 leading-relaxed">
                  {skill.description}
                </p>
              )}
            </div>
          </div>
          <span className="text-[10px] font-mono text-muted-foreground shrink-0 bg-muted px-1.5 py-0.5 rounded">
            {skill.relative_path}
          </span>
        </div>

        {/* Conflict Alert Banner */}
        {skill.conflict_reason && (
          <div className="mt-2 text-[11px] text-destructive bg-destructive/10 rounded px-2 py-1 flex items-center gap-1.5 ml-6">
            <AlertTriangle className="h-3 w-3 shrink-0" />
            <span>{skill.conflict_reason}</span>
          </div>
        )}

        {/* Security Gate Hard Stop Line Banner */}
        {isSecurityBlocked && (
          <div
            data-testid="security-blocked-notice"
            className="mt-2 text-[11px] font-medium text-destructive bg-destructive/15 border border-destructive/30 rounded px-2 py-1.5 flex items-center gap-1.5 ml-6"
          >
            <ShieldAlert className="h-3.5 w-3.5 shrink-0" />
            <span>{t('previewDialog.securityBlockedTooltip')}</span>
          </div>
        )}

        {/* Tool Dependencies */}
        {(skill.required_tools?.length ?? 0) > 0 && (
          <div className="mt-2 flex items-center gap-1.5 flex-wrap ml-6">
            <Wrench className="h-3 w-3 text-muted-foreground shrink-0" />
            <span className="text-[10px] text-muted-foreground">{t('previewDialog.tools')}:</span>
            {skill.required_tools.map((tool) => (
              <Badge key={tool} variant="outline" className="text-[9px] px-1 py-0 font-mono">
                {tool}
              </Badge>
            ))}
          </div>
        )}

        {/* Findings Inspection Toggle & Drawer */}
        {findings.length > 0 && (
          <div className="mt-2.5 ml-6 pt-1 border-t border-border/40">
            <button
              type="button"
              data-testid="toggle-findings-btn"
              onClick={toggleFindings}
              className="inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground transition-colors font-medium"
            >
              {isFindingsExpanded ? (
                <>
                  <ChevronUp className="h-3 w-3" />
                  <span>{t('previewDialog.hideFindings')}</span>
                </>
              ) : (
                <>
                  <ChevronDown className="h-3 w-3" />
                  <span>{t('previewDialog.showFindings', { count: findings.length })}</span>
                </>
              )}
            </button>

            {isFindingsExpanded && (
              <div
                data-testid="findings-inspection-panel"
                className="mt-2 space-y-1.5 bg-muted/30 rounded p-2 text-xs border border-border/60"
              >
                {findings.map((finding, idx) => (
                  <div
                    key={`${finding.threat_type}-${idx}`}
                    className="flex items-start gap-1.5 text-[11px] leading-snug"
                  >
                    <FileCode className="h-3 w-3 text-destructive shrink-0 mt-0.5" />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="font-mono font-medium text-destructive">
                          {finding.threat_type}
                        </span>
                        <Badge variant="outline" className="text-[9px] px-1 py-0 uppercase">
                          {finding.severity}
                        </Badge>
                        {finding.line_number !== null && (
                          <span className="font-mono text-muted-foreground text-[10px]">
                            {t('previewDialog.line', { line: finding.line_number })}
                          </span>
                        )}
                      </div>
                      <p className="text-muted-foreground mt-0.5 text-[10px]">
                        {finding.description}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    );
  },
);

LocalSkillPreviewCard.displayName = 'LocalSkillPreviewCard';
