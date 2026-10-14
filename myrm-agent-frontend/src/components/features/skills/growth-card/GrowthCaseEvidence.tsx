/**
 * [INPUT] SkillGrowthCaseSummary via @/services/skill/growth; useScanRiskText; @/lib/skills/scanRiskText::parseRiskSignals
 * [OUTPUT] GrowthCaseEvidence: 成长提案的证据面板组（验证证明、安全扫描发现、运行时失败、待审原因、应用失败）
 * [POS] features/skills/growth-card 卡片的只读证据区；扫描类别、严重度、待审信号与处置建议均以用户语言呈现
 */
'use client';

import { useTranslations } from 'next-intl';
import { ShieldCheck } from 'lucide-react';
import { useScanRiskText } from '@/components/features/skills/useScanRiskText';
import { Badge } from '@/components/primitives/badge';
import { parseRiskSignals } from '@/lib/skills/scanRiskText';
import { cn } from '@/lib/utils/classnameUtils';
import type { SkillGrowthCaseSummary } from '@/services/skill/growth';

export function GrowthCaseEvidence({ item }: { item: SkillGrowthCaseSummary }) {
  const t = useTranslations('settings.skills.growth');
  const scanText = useScanRiskText();
  const { verificationProof, securityScanSummary, runtimeFailure } = item;
  const findings = securityScanSummary?.findings ?? [];
  const riskSignals = parseRiskSignals(item.reasonCode);
  const riskRemediation = scanText.remediation(riskSignals);

  return (
    <>
      {verificationProof && (
        <div className="mt-4 rounded-xl border border-emerald-300/50 bg-emerald-50/50 p-3 dark:border-emerald-900/40 dark:bg-emerald-950/20">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground flex items-center gap-1.5">
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
              {t('verificationProofTitle')}
            </p>
            {verificationProof.blast_radius && (
              <span className="text-[11px] text-muted-foreground">
                {t('blastRadius', {
                  files: verificationProof.blast_radius.files ?? 1,
                  lines: verificationProof.blast_radius.lines ?? 0,
                })}
              </span>
            )}
          </div>
          {verificationProof.verification_summary && (
            <p className="mt-1.5 text-xs text-foreground font-medium">{verificationProof.verification_summary}</p>
          )}
        </div>
      )}

      {securityScanSummary && findings.length > 0 && (
        <div className="mt-4 rounded-xl border border-indigo-300/50 bg-indigo-50/40 p-3 dark:border-indigo-900/40 dark:bg-indigo-950/20">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium uppercase tracking-wide text-indigo-700 dark:text-indigo-300 inline-flex items-center gap-1.5">
              <ShieldCheck className="h-3.5 w-3.5" />
              <span>{t('securityScan.title', { count: findings.length })}</span>
            </p>
            <span className="font-mono text-xs font-semibold text-muted-foreground">
              {t('securityScan.score', { score: securityScanSummary.score })}
            </span>
          </div>
          <div className="mt-2 space-y-1.5">
            {findings.map((finding, idx) => (
              <div
                key={`${finding.threat_type}-${idx}`}
                className="flex items-start justify-between gap-2 rounded-lg bg-background/60 p-2 text-xs"
              >
                <div className="min-w-0 space-y-0.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline" className="text-[10px]">
                      {scanText.threatLabel(finding.threat_type)}
                    </Badge>
                    <span className="font-medium text-foreground">{finding.description}</span>
                  </div>
                  {finding.line_number && (
                    <span className="text-[10px] text-muted-foreground font-mono">
                      {t('securityScan.line', { line: finding.line_number })}
                    </span>
                  )}
                </div>
                <Badge
                  variant="outline"
                  className={cn(
                    'text-[10px] shrink-0',
                    finding.severity === 'critical' || finding.severity === 'high'
                      ? 'border-rose-500/50 text-rose-700 dark:text-rose-300'
                      : 'border-amber-500/50 text-amber-700 dark:text-amber-300',
                  )}
                >
                  {scanText.severityLabel(finding.severity)}
                </Badge>
              </div>
            ))}
          </div>
        </div>
      )}

      {runtimeFailure && (
        <div className="mt-4 rounded-xl border border-sky-300/50 bg-sky-50/60 p-3 dark:border-sky-900/40 dark:bg-sky-950/20">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {t('runtimeFailure.title')}
          </p>
          <div className="mt-2 grid gap-2 text-sm text-foreground md:grid-cols-2">
            <span className="min-w-0 truncate">{t('runtimeFailure.tool', { value: runtimeFailure.tool_name })}</span>
            <span className="min-w-0 truncate">
              {t('runtimeFailure.count', { value: runtimeFailure.failure_count })}
            </span>
            <span className="min-w-0 truncate">
              {t('runtimeFailure.confidence', {
                value: (runtimeFailure.attribution_confidence * 100).toFixed(0),
              })}
            </span>
            {runtimeFailure.loop_kind && (
              <span className="min-w-0 truncate">
                {t('runtimeFailure.loopKind', { value: runtimeFailure.loop_kind })}
              </span>
            )}
          </div>
          <p className="mt-2 break-words font-mono text-xs text-sky-900 dark:text-sky-100">
            {runtimeFailure.error_signature}
          </p>
        </div>
      )}

      {riskSignals.length > 0 && (
        <div className="mt-4 rounded-xl border border-amber-300/50 bg-amber-50/60 p-3 dark:border-amber-900/40 dark:bg-amber-950/20">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {t('riskInterceptionTitle')}
          </p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {riskSignals.map((signal) => (
              <Badge
                key={signal}
                variant="outline"
                className="text-[11px] border-amber-400 text-amber-700 dark:border-amber-700 dark:text-amber-300"
              >
                {scanText.signalLabel(signal)}
              </Badge>
            ))}
          </div>
          {riskRemediation && <p className="mt-2 text-sm text-muted-foreground">{riskRemediation}</p>}
        </div>
      )}

      {item.applyError && (
        <div className="mt-4 rounded-xl border border-orange-300/50 bg-orange-50/60 p-3 dark:border-orange-900/40 dark:bg-orange-950/20">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t('applyFailureTitle')}</p>
          <p className="mt-1 text-sm text-foreground">{item.applyError}</p>
          {item.remediation && riskSignals.length === 0 && (
            <p className="mt-2 text-sm text-muted-foreground">{item.remediation}</p>
          )}
        </div>
      )}
    </>
  );
}
