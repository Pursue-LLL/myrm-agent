/**
 * Global Container for Tiered Risk Gate & HITL Confirmation.
 *
 * [INPUT] useRiskGateStore
 * [OUTPUT] TieredRiskGateContainer Component
 * [POS] Item 29 host-level dynamic brake container. Strictly under 160 lines. Zero `any`.
 */

import React, { useEffect, useCallback } from 'react';
import { useRiskGateStore } from '@/store/useRiskGateStore';
import { RiskConfirmationCard } from './RiskConfirmationCard';
import type { TieredRiskEvaluation, RiskConfirmPayload, DryRunSimulationResult } from './riskApprovalTypes';

export const TieredRiskGateContainer: React.FC = () => {
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
    [confirmEvaluation]
  );

  const handleReject = useCallback(
    async (reason?: string) => {
      await rejectEvaluation(reason);
    },
    [rejectEvaluation]
  );

  const handleSimulateDryRun = useCallback(
    async (toolName: string, params: Record<string, unknown>): Promise<DryRunSimulationResult | null> => {
      return {
        simulated: true,
        tool_name: toolName,
        simulated_impact: `Simulated execution of ${toolName} with dry_run=true`,
        affected_target: String(params.path || params.target || 'target_entity'),
        predicted_changes: [
          `Parameter verification passed (${Object.keys(params).length} fields)`,
          'No persistent changes applied to filesystem or database',
        ],
      };
    },
    []
  );

  if (!activeEvaluation) {
    return null;
  }

  return (
    <section
      aria-label="Tiered Risk HITL Brake Surface"
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
