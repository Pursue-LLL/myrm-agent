'use client';

/**
 * [INPUT]
 * - @/components/primitives/button::Button (POS: 基础按钮组件)
 * - @/lib/utils/classnameUtils::cn (POS: 类名合并工具)
 * - @/services/wikiService::ConceptClaim (POS: 词条声明实体模型)
 * - @/lib/wiki/claimStatusDisplay::claimStatusClass/claimStatusLabel (POS: 声明状态样式与国际化标签)
 *
 * [OUTPUT]
 * - WikiConceptClaimsSection: 词条结构化声明（Claims）列表、证据链凭证下钻及治理操作组件
 *
 * [POS]
 * 词条结构化事实凭证展示层。负责 Claim 状态卡片渲染、证据链校验与一键治愈操作。
 */

import { Button } from '@/components/primitives/button';
import { cn } from '@/lib/utils/classnameUtils';
import type { ConceptClaim } from '@/services/wikiService';
import {
  claimStatusClass,
  claimStatusLabel,
  formatClaimConfidence,
  shouldShowClaimConfidence,
} from '@/lib/wiki/claimStatusDisplay';

interface WikiConceptClaimsSectionProps {
  claims: ConceptClaim[];
  locale: string;
  claimStatusLabels: Record<string, string>;
  onHealClaims?: () => void;
  onUpdateClaimStatus?: (claimId: string, status: 'supported' | 'contested') => void;
  t: (key: string, params?: Record<string, string | number>) => string;
}

export function WikiConceptClaimsSection({
  claims,
  locale,
  claimStatusLabels,
  onHealClaims,
  onUpdateClaimStatus,
  t,
}: WikiConceptClaimsSectionProps) {
  return (
    <div className="space-y-3 border-t border-border/60 pt-4">
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium">{t('claimsTitle')}</div>
        {claims.length > 0 && onHealClaims && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onHealClaims}
            className="h-7 text-xs px-2.5"
          >
            {t('claimsHealAction')}
          </Button>
        )}
      </div>
      {claims.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('claimsEmpty')}</p>
      ) : (
        <div className="space-y-3">
          {claims.map((claim) => (
            <div
              key={claim.id}
              className={cn(
                'rounded-lg border p-3 space-y-2',
                claim.status === 'unknown'
                  ? 'border-border/40 bg-muted/10 opacity-80'
                  : 'border-border/60 bg-muted/20',
              )}
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={cn(
                      'text-sm font-medium',
                      claim.status === 'unknown' && 'text-muted-foreground',
                    )}
                  >
                    {claim.text}
                  </span>
                  <span
                    className={cn(
                      'text-[10px] leading-4 px-1.5 py-0.5 rounded-full border',
                      claimStatusClass(claim.status),
                    )}
                  >
                    {claimStatusLabel(claim.status, claimStatusLabels)}
                  </span>
                  {shouldShowClaimConfidence(claim.confidence) && (
                    <span className="text-[10px] leading-4 px-1.5 py-0.5 rounded-full border bg-sky-500/10 text-sky-800 dark:text-sky-200 border-sky-500/20">
                      {formatClaimConfidence(claim.confidence, locale)}
                    </span>
                  )}
                </div>
                {onUpdateClaimStatus && (
                  <div className="flex items-center gap-1.5">
                    {claim.status !== 'supported' && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => onUpdateClaimStatus(claim.id, 'supported')}
                        className="h-6 text-[11px] px-2 text-emerald-600 hover:text-emerald-700 hover:bg-emerald-500/10 dark:text-emerald-400"
                      >
                        {t('claimsVerifyAction')}
                      </Button>
                    )}
                    {claim.status !== 'contested' && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => onUpdateClaimStatus(claim.id, 'contested')}
                        className="h-6 text-[11px] px-2 text-rose-600 hover:text-rose-700 hover:bg-rose-500/10 dark:text-rose-400"
                      >
                        {t('claimsContestAction')}
                      </Button>
                    )}
                  </div>
                )}
              </div>
              {claim.evidence.length > 0 && (
                <ul className="space-y-1 text-xs text-muted-foreground">
                  {claim.evidence.map((evidence, index) => (
                    <li key={`${claim.id}-${index}`} className="space-y-0.5">
                      {evidence.path && (
                        <div className="font-mono truncate">
                          {t('evidencePath')}: {evidence.path}
                          {evidence.lines ? ` · ${t('evidenceLines')}: ${evidence.lines}` : ''}
                        </div>
                      )}
                      {evidence.snapshot_status === 'verified' && (
                        <div className="text-[11px] text-emerald-700 dark:text-emerald-300">
                          {t('evidenceSnapshotVerified')}
                        </div>
                      )}
                      {evidence.snapshot_status === 'stale' && (
                        <div className="text-[11px] text-amber-700 dark:text-amber-300">
                          {t('evidenceSnapshotStale')}
                        </div>
                      )}
                      {evidence.snapshot_status === 'missing' && evidence.path && (
                        <div className="text-[11px] text-muted-foreground">
                          {t('evidenceSnapshotMissing')}
                        </div>
                      )}
                      {evidence.resource_uri ? (
                        <div className="text-[11px] text-muted-foreground font-mono break-all">
                          {t('evidenceResourceUri', { uri: evidence.resource_uri })}
                        </div>
                      ) : null}
                      {evidence.superseded_from_uri ? (
                        <div className="text-[11px] text-amber-700/90 dark:text-amber-300/90 font-mono break-all">
                          {t('evidenceSupersededFrom', { uri: evidence.superseded_from_uri })}
                        </div>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
