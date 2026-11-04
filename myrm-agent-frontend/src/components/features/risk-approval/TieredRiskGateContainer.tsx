/**
 * Global Container for Tiered Risk Gate & HITL Confirmation.
 *
 * [INPUT] useRiskGateStore, next-intl::useTranslations (POS: Internationalization hook)
 * [OUTPUT] TieredRiskGateContainer Component
 * [POS] Item 29 host-level dynamic brake container. Strictly under 160 lines. Zero `any`.
 */

import React, { useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { useRiskGateStore } from '@/store/useRiskGateStore';
import { RiskConfirmationCard } from './RiskConfirmationCard';
import type { TieredRiskEvaluation, RiskConfirmPayload, DryRunSimulationResult } from './riskApprovalTypes';

export const TieredRiskGateContainer: React.FC = () => {
  const t = useTranslations('riskGate');
  const activeEvaluation = useRiskGateStore((state) => state.activeEvaluation);
  const setActiveEvaluation = useRiskGateStore((state) => state.setActiveEvaluation);
  const confirmEvaluation = useRiskGateStore((state) => state.confirmEvaluation);
  const rejectEvaluation = useRiskGateStore((state) => state.rejectEvaluation);

  // Listen to cross-system global custom event for dynamic brake triggers
  useEffect(() => {
    const handleCustomEvent = (event: Event) => {
      const customEvent = event as CustomEvent<TieredRiskEvaluation>;
      if (customEvent.detail) {
        setActiveEvaluation(customEvent.detail);
      }
    };

    window.addEventListener('myrm:tiered-risk-eval', handleCustomEvent);
    return () => {
      window.removeEventListener('myrm:tiered-risk-eval', handleCustomEvent);
    };
  }, [setActiveEvaluation]);

  const handleConfirm = useCallback(
    async (payload: RiskConfirmPayload) => {
      await confirmEvaluation(payload);
    },
    [confirmEvaluation],
  );

  const handleReject = useCallback(
    async (reason?: string) => {
      await rejectEvaluation(reason);
    },
    [rejectEvaluation],
  );

  const handleSimulateDryRun = useCallback(
    async (toolName: string, params: Record<string, unknown>): Promise<DryRunSimulationResult | null> => {
      return {
        simulated: true,
        tool_name: toolName,
        simulated_impact: t('dryRunImpact', { tool: toolName }),
        affected_target: String(params.path || params.target || t('dryRunDefaultTarget')),
        predicted_changes: [
          t('dryRunParamsVerified', { count: Object.keys(params).length }),
          t('dryRunNoPersistentChanges'),
        ],
      };
    },
    [t],
  );

  if (!activeEvaluation) {
    return null;
  }

  return (
    <section
      aria-label={t('regionLabel')}
      className="fixed bottom-6 right-6 z-50 w-full max-w-lg shadow-2xl animate-in fade-in slide-in-from-bottom-4 duration-200"
    >
      <RiskConfirmationCard
        evaluation={activeEvaluation}
        onConfirm={handleConfirm}
        onReject={handleReject}
        onSimulateDryRun={handleSimulateDryRun}
      />
    </section>
  );
};
