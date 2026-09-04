'use client';

/**
 * [INPUT] services/wikiService (POS: Wiki REST 客户端)
 * [OUTPUT] useWikiConceptClaimActions: 词条 Claim 状态更新与证据修复操作
 * [POS] Settings Wiki 词条声明与证据链交互 Hook
 */
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { wikiService, Concept } from '@/services/wikiService';
import { getWikiOperationErrorMessage } from './wikiTreeUtils';

export interface UseWikiConceptClaimActionsProps {
  selectedConcept: Concept | null;
  setSelectedConcept: (concept: Concept | null) => void;
  agentScopeId?: string;
  onVaultMutated?: () => void;
}

export function useWikiConceptClaimActions({
  selectedConcept,
  setSelectedConcept,
  agentScopeId,
  onVaultMutated,
}: UseWikiConceptClaimActionsProps) {
  const t = useTranslations('settings.knowledge.wiki');

  const handleUpdateClaimStatus = async (claimId: string, status: 'supported' | 'contested') => {
    if (!selectedConcept) {
      return;
    }
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
      const refreshed = await wikiService.getConcept(selectedConcept.name, agentScopeId);
      setSelectedConcept(refreshed);
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
    try {
      const result = await wikiService.healConceptClaims([selectedConcept.name], agentScopeId);
      if (result.total_healed_evidence > 0) {
        toast.success(t('claimsHealSuccess', { count: result.total_healed_evidence }));
      } else {
        toast.info(t('claimsHealNone'));
      }
      const refreshed = await wikiService.getConcept(selectedConcept.name, agentScopeId);
      setSelectedConcept(refreshed);
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
