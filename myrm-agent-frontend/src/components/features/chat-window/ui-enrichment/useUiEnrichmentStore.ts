import { create } from 'zustand';
import { enrichModelJudgmentsWithAuthoritativeFacts } from './uiEnrichmentEngine';
import {
  AuthoritativeFactRecord,
  EnrichedPresentationResult,
  EnrichmentAuditLog,
  ModelJudgmentInput,
} from './uiEnrichmentTypes';

interface UiEnrichmentState {
  authoritativeFacts: Record<string, AuthoritativeFactRecord>;
  enrichedPresentations: Record<string, EnrichedPresentationResult>;
  lastAuditLog: EnrichmentAuditLog | null;

  seedAuthoritativeFacts: (facts: AuthoritativeFactRecord[]) => void;
  processModelJudgments: (
    judgments: ModelJudgmentInput[],
    presentationId?: string,
  ) => EnrichedPresentationResult;
  clear: () => void;
  reset: () => void;
}

export const useUiEnrichmentStore = create<UiEnrichmentState>((set, get) => ({
  authoritativeFacts: {},
  enrichedPresentations: {},
  lastAuditLog: null,

  seedAuthoritativeFacts: (facts: AuthoritativeFactRecord[]): void => {
    set((state) => {
      const next = { ...state.authoritativeFacts };
      for (const f of facts) {
        next[f.id] = f;
      }
      return { authoritativeFacts: next };
    });
  },

  processModelJudgments: (
    judgments: ModelJudgmentInput[],
    presentationId?: string,
  ): EnrichedPresentationResult => {
    const result = enrichModelJudgmentsWithAuthoritativeFacts(
      judgments,
      get().authoritativeFacts,
      presentationId,
    );

    set((state) => ({
      enrichedPresentations: {
        ...state.enrichedPresentations,
        [result.presentationId]: result,
      },
      lastAuditLog: result.auditLog,
    }));

    return result;
  },

  clear: (): void => {
    set({
      authoritativeFacts: {},
      enrichedPresentations: {},
      lastAuditLog: null,
    });
  },

  reset: (): void => {
    set({
      authoritativeFacts: {},
      enrichedPresentations: {},
      lastAuditLog: null,
    });
  },
}));
