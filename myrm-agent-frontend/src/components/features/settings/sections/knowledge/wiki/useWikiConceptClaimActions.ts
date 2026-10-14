'use client';

/**
 * [INPUT] services/wikiService (POS: Wiki REST 客户端)
 * [OUTPUT] useWikiConceptClaimActions: 词条 Claim 状态更新与证据修复操作
 * [POS] Settings Wiki 词条声明与证据链交互 Hook
 */
import type { RefObject } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { wikiService, Concept } from '@/services/wikiService';
import { getWikiOperationErrorMessage } from './wikiTreeUtils';

export interface UseWikiConceptClaimActionsProps {
  selectedConcept: Concept | null;
  setSelectedConcept: (concept: Concept | null) => void;
  /** 与词条选择共用的请求计数：操作期间改选或重置后，迟到的刷新结果不再写入选中词条 */
  selectRequestRef: RefObject<number>;
  agentScopeId?: string | null;
  onVaultMutated?: () => void;
}

export function useWikiConceptClaimActions({
  selectedConcept,
  setSelectedConcept,
  selectRequestRef,
  agentScopeId,
  onVaultMutated,
}: UseWikiConceptClaimActionsProps) {
  const t = useTranslations('settings.wiki.concepts');

  const refreshSelectedConcept = async (name: string, requestId: number) => {
    const refreshed = await wikiService.getConcept(name, agentScopeId);
    if (requestId === selectRequestRef.current) {
      setSelectedConcept(refreshed);
    }
  };

  const handleUpdateClaimStatus = async (claimId: string, status: 'supported' | 'contested') => {
    if (!selectedConcept) {
      return;
    }
    const requestId = selectRequestRef.current;
    const currentClaims = selectedConcept.claims || [];
    const patchClaims = currentClaims.map((c) => ({
      id: c.id,
      text: c.text,
      status: c.id === claimId ? status : c.status,
      confidence: c.confidence,
      evidence: c.evidence,
    }));
    try {
      await wikiService.applyWiki(
        {
          op: 'update_metadata',
          concept_name: selectedConcept.name,
          claims: patchClaims,
        },
        agentScopeId,
        'settings',
      );
      await refreshSelectedConcept(selectedConcept.name, requestId);
      toast.success(t('claimsStatusUpdated'));
      onVaultMutated?.();
    } catch (error) {
      toast.error(getWikiOperationErrorMessage(error, t('updateFailed')));
    }
  };

  const handleHealClaims = async () => {
    if (!selectedConcept) {
      return;
    }
    const requestId = selectRequestRef.current;
    try {
      const result = await wikiService.healConceptClaims([selectedConcept.name], agentScopeId);
      if (result.total_healed_evidence > 0) {
        toast.success(t('claimsHealSuccess', { count: result.total_healed_evidence }));
      } else {
        toast.info(t('claimsHealNone'));
      }
      await refreshSelectedConcept(selectedConcept.name, requestId);
      onVaultMutated?.();
    } catch (error) {
      toast.error(getWikiOperationErrorMessage(error, t('operationFailed')));
    }
  };

  return {
    handleUpdateClaimStatus,
    handleHealClaims,
  };
}
