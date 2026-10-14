/**
 * [INPUT] @/services/skill/growth::SecurityScanFindingDetailDto,RuntimeFailureEvidence (POS: 技能进化（growth）客户端)
 * [OUTPUT] GrowthTechnicalDetails: 默认收起的「技术细节」折叠区，原样展示扫描器描述、运行时错误签名与应用失败原文
 * [POS] features/skills/growth-card 证据区的出口：这些文本来自扫描器与运行时、不随界面语言本地化，
 *       主区域只显示本地化结论，需要排查时再展开，避免普通用户直接读到技术原文
 */
'use client';

import type { ReactNode } from 'react';
import { useTranslations } from 'next-intl';
import { IconChevronDown } from '@/components/features/icons/PremiumIcons';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/primitives/collapsible';
import type { RuntimeFailureEvidence, SecurityScanFindingDetailDto } from '@/services/skill/growth';

interface GrowthTechnicalDetailsProps {
  findings: readonly SecurityScanFindingDetailDto[];
  runtimeFailure: RuntimeFailureEvidence | null;
  applyError: string | null;
  /** Advice text from the server; only passed when no localized advice already covers it. */
  remediation: string | null;
}

function DetailSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{title}</p>
      {children}
    </div>
  );
}

const MONO_TEXT = 'break-words font-mono text-xs text-foreground/90';

export function GrowthTechnicalDetails({
  findings,
  runtimeFailure,
  applyError,
  remediation,
}: GrowthTechnicalDetailsProps) {
  const t = useTranslations('settings.skills.growth');

  const runtimeText = runtimeFailure
    ? [runtimeFailure.loop_kind, runtimeFailure.error_signature].filter(Boolean).join(' / ')
    : '';
  if (findings.length === 0 && !runtimeText && !applyError && !remediation) {
    return null;
  }

  return (
    <Collapsible className="mt-3">
      <CollapsibleTrigger className="group inline-flex items-center gap-1 py-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground">
        <IconChevronDown className="h-3.5 w-3.5 transition-transform group-data-[state=open]:rotate-180" />
        {t('technical.toggle')}
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="mt-2 max-h-64 space-y-3 overflow-auto rounded-xl border border-border/60 bg-muted/30 p-3">
          {findings.length > 0 && (
            <DetailSection title={t('technical.findings')}>
              <ul className="space-y-1">
                {findings.map((finding, idx) => (
                  <li key={`${finding.threat_type}-${idx}`} className={MONO_TEXT}>
                    {finding.line_number != null && (
                      <span className="mr-2 text-muted-foreground">
                        {t('securityScan.line', { line: finding.line_number })}
                      </span>
                    )}
                    {finding.description}
                  </li>
                ))}
              </ul>
            </DetailSection>
          )}
          {runtimeText && (
            <DetailSection title={t('runtimeFailure.title')}>
              <p className={MONO_TEXT}>{runtimeText}</p>
            </DetailSection>
          )}
          {applyError && (
            <DetailSection title={t('applyFailureTitle')}>
              <p className={MONO_TEXT}>{applyError}</p>
            </DetailSection>
          )}
          {remediation && (
            <DetailSection title={t('technical.advice')}>
              <p className="break-words text-xs text-muted-foreground">{remediation}</p>
            </DetailSection>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
