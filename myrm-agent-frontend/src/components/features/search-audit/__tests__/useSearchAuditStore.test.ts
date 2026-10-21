import { describe, it, expect, beforeEach } from 'vitest';
import { useSearchAuditStore } from '../useSearchAuditStore';
import { SearchAuditSession, AuditCitationItem, SubQueryTrace } from '../searchAuditTypes';
import { calculateSourceQualityMatrix } from '../searchAuditEngine';

describe('useSearchAuditStore', () => {
  const mockTrace: SubQueryTrace = {
    subQueryId: 'sq-1',
    queryText: 'MoE routing architecture',
    category: 'academic',
    latencyMs: 380,
    payloadBytes: 12000,
    isFullText: true,
    hasAiRewrite: false,
    timestamp: Date.now(),
  };

  const mockCitation: AuditCitationItem = {
    id: 'cite-1',
    url: 'https://arxiv.org/abs/2401.00001',
    domain: 'arxiv.org',
    title: 'DeepSeekMoE: Towards Ultimate Expert Specialization',
    rawSnippet: 'DeepSeekMoE architecture introduces fine-grained expert segmentation...',
    fullTextSnippet: 'Section 2. Architecture Overview: Fine-grained experts with shared routing...',
    subQueryId: 'sq-1',
    qualityMatrix: calculateSourceQualityMatrix('https://arxiv.org/abs/2401.00001', true, false),
  };

  const mockSession: SearchAuditSession = {
    auditSessionId: 'audit-001',
    parentMessageId: 'msg-999',
    totalLatencyMs: 380,
    totalPayloadBytes: 12000,
    averageQualityScore: 95,
    traces: [mockTrace],
    citations: [mockCitation],
    createdAt: Date.now(),
  };

  beforeEach(() => {
    useSearchAuditStore.getState().clearSession();
  });

  it('initializes with default closed state and waterfall tab', () => {
    const state = useSearchAuditStore.getState();
    expect(state.isDrawerOpen).toBe(false);
    expect(state.activeSession).toBeNull();
    expect(state.selectedCitation).toBeNull();
    expect(state.activeTab).toBe('waterfall');
  });

  it('opens audit drawer with session data', () => {
    useSearchAuditStore.getState().openAuditDrawer(mockSession);

    const state = useSearchAuditStore.getState();
    expect(state.isDrawerOpen).toBe(true);
    expect(state.activeSession?.auditSessionId).toBe('audit-001');
    expect(state.selectedCitation?.id).toBe('cite-1');
    expect(state.activeTab).toBe('waterfall');
  });

  it('opens audit drawer and targets initial citation directly', () => {
    useSearchAuditStore.getState().openAuditDrawer(mockSession, 'cite-1');

    const state = useSearchAuditStore.getState();
    expect(state.isDrawerOpen).toBe(true);
    expect(state.selectedCitation?.id).toBe('cite-1');
    expect(state.activeTab).toBe('evidence_compare');
  });

  it('toggles drawer and tab transitions properly', () => {
    useSearchAuditStore.getState().openAuditDrawer(mockSession);
    expect(useSearchAuditStore.getState().isDrawerOpen).toBe(true);

    useSearchAuditStore.getState().closeAuditDrawer();
    expect(useSearchAuditStore.getState().isDrawerOpen).toBe(false);

    useSearchAuditStore.getState().toggleAuditDrawer(true);
    expect(useSearchAuditStore.getState().isDrawerOpen).toBe(true);

    useSearchAuditStore.getState().setActiveTab('quality_matrix');
    expect(useSearchAuditStore.getState().activeTab).toBe('quality_matrix');
  });

  it('clears active session state cleanly', () => {
    useSearchAuditStore.getState().openAuditDrawer(mockSession);
    useSearchAuditStore.getState().clearSession();

    const state = useSearchAuditStore.getState();
    expect(state.isDrawerOpen).toBe(false);
    expect(state.activeSession).toBeNull();
    expect(state.selectedCitation).toBeNull();
  });
});
