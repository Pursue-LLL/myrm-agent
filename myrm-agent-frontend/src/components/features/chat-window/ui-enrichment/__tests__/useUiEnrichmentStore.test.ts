import { beforeEach, describe, expect, it } from 'vitest';
import { AuthoritativeFactRecord, ModelJudgmentInput } from '../uiEnrichmentTypes';
import { useUiEnrichmentStore } from '../useUiEnrichmentStore';

describe('useUiEnrichmentStore', () => {
  beforeEach(() => {
    useUiEnrichmentStore.getState().reset();
  });

  const sampleFacts: AuthoritativeFactRecord[] = [
    {
      id: 'fact-hw-1',
      officialTitle: 'AI 加速卡 A100',
      officialPrice: 65000,
      officialCurrency: 'CNY',
      stockStatus: 'in_stock',
    },
    {
      id: 'fact-hw-2',
      officialTitle: 'AI 加速卡 H100',
      officialPrice: 220000,
      officialCurrency: 'CNY',
      stockStatus: 'low_stock',
    },
  ];

  it('initializes with default empty state', () => {
    const state = useUiEnrichmentStore.getState();
    expect(state.authoritativeFacts).toEqual({});
    expect(state.enrichedPresentations).toEqual({});
    expect(state.lastAuditLog).toBeNull();
  });

  it('seeds authoritative facts accurately', () => {
    useUiEnrichmentStore.getState().seedAuthoritativeFacts(sampleFacts);

    const store = useUiEnrichmentStore.getState();
    expect(store.authoritativeFacts['fact-hw-1']).toBeDefined();
    expect(store.authoritativeFacts['fact-hw-1']?.officialPrice).toBe(65000);
    expect(store.authoritativeFacts['fact-hw-2']?.stockStatus).toBe('low_stock');
  });

  it('processes model judgments and updates enrichedPresentations and auditLog', () => {
    useUiEnrichmentStore.getState().seedAuthoritativeFacts(sampleFacts);

    const judgments: ModelJudgmentInput[] = [
      {
        id: 'fact-hw-1',
        userNote: '性价比高',
        comparisonHighlight: '适合微调',
      },
      {
        id: 'unknown-gpu-888',
        userNote: '伪造型号',
      },
    ];

    const res = useUiEnrichmentStore
      .getState()
      .processModelJudgments(judgments, 'pres-enrich-test');

    expect(res.presentationId).toBe('pres-enrich-test');
    expect(res.items).toHaveLength(1);
    expect(res.items[0]?.officialTitle).toBe('AI 加速卡 A100');

    const store = useUiEnrichmentStore.getState();
    expect(store.enrichedPresentations['pres-enrich-test']).toBeDefined();
    expect(store.lastAuditLog).toEqual(res.auditLog);
    expect(store.lastAuditLog?.droppedUnknownIds).toContain('unknown-gpu-888');
  });

  it('clears and resets store properly', () => {
    useUiEnrichmentStore.getState().seedAuthoritativeFacts(sampleFacts);
    useUiEnrichmentStore.getState().clear();

    const state = useUiEnrichmentStore.getState();
    expect(state.authoritativeFacts).toEqual({});
    expect(state.enrichedPresentations).toEqual({});
    expect(state.lastAuditLog).toBeNull();
  });
});
