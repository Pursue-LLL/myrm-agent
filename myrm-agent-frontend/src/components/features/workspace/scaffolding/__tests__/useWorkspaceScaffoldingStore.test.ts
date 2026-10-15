import { beforeEach, describe, expect, it } from 'vitest';
import { useWorkspaceScaffoldingStore } from '../useWorkspaceScaffoldingStore';
import { GeneratedScaffoldDoc } from '../workspaceScaffoldingTypes';

describe('useWorkspaceScaffoldingStore', () => {
  beforeEach(() => {
    useWorkspaceScaffoldingStore.getState().reset();
  });

  it('initializes with default state', () => {
    const state = useWorkspaceScaffoldingStore.getState();
    expect(state.proposals).toEqual({});
    expect(state.activeProposalId).toBeNull();
    expect(state.isPreviewModalOpen).toBe(false);
    expect(state.previewingDoc).toBeNull();
  });

  it('triggers scaffolding analysis and stores proposal', () => {
    const id = useWorkspaceScaffoldingStore
      .getState()
      .triggerScaffoldAnalysis('/demo-project', ['raw.pdf', 'notes.tmp']);

    expect(id).toBeDefined();
    const store = useWorkspaceScaffoldingStore.getState();
    expect(store.activeProposalId).toBe(id);
    const proposal = store.proposals[id];
    expect(proposal).toBeDefined();
    expect(proposal?.status).toBe('pending_review');
    expect(proposal?.moves).toHaveLength(2);
  });

  it('confirms pending proposal and updates status to confirmed', () => {
    const id = useWorkspaceScaffoldingStore
      .getState()
      .triggerScaffoldAnalysis('/demo-project', ['doc.pdf']);

    const success = useWorkspaceScaffoldingStore
      .getState()
      .confirmProposal(id);
    expect(success).toBe(true);

    const proposal = useWorkspaceScaffoldingStore.getState().proposals[id];
    expect(proposal?.status).toBe('confirmed');

    // 再次确认应返回 false
    const reconfirm = useWorkspaceScaffoldingStore
      .getState()
      .confirmProposal(id);
    expect(reconfirm).toBe(false);
  });

  it('cancels pending proposal and updates status to cancelled', () => {
    const id = useWorkspaceScaffoldingStore
      .getState()
      .triggerScaffoldAnalysis('/demo-project', ['doc.pdf']);

    const success = useWorkspaceScaffoldingStore
      .getState()
      .cancelProposal(id);
    expect(success).toBe(true);

    const proposal = useWorkspaceScaffoldingStore.getState().proposals[id];
    expect(proposal?.status).toBe('cancelled');

    // 取消后再确认应返回 false
    const reconfirm = useWorkspaceScaffoldingStore
      .getState()
      .confirmProposal(id);
    expect(reconfirm).toBe(false);
  });

  it('controls doc preview modal state', () => {
    const sampleDoc: GeneratedScaffoldDoc = {
      path: '/demo-project/AGENTS.md',
      title: 'AGENTS.md 规范',
      purpose: '红线守则',
      draftContent: '# 规约内容',
    };

    useWorkspaceScaffoldingStore.getState().openDocPreview(sampleDoc);
    expect(useWorkspaceScaffoldingStore.getState().isPreviewModalOpen).toBe(
      true,
    );
    expect(useWorkspaceScaffoldingStore.getState().previewingDoc).toEqual(
      sampleDoc,
    );

    useWorkspaceScaffoldingStore.getState().closeDocPreview();
    expect(useWorkspaceScaffoldingStore.getState().isPreviewModalOpen).toBe(
      false,
    );
    expect(useWorkspaceScaffoldingStore.getState().previewingDoc).toBeNull();
  });

  it('resets all state on reset()', () => {
    useWorkspaceScaffoldingStore
      .getState()
      .triggerScaffoldAnalysis('/ws', ['1.pdf']);
    useWorkspaceScaffoldingStore.getState().reset();

    const state = useWorkspaceScaffoldingStore.getState();
    expect(state.proposals).toEqual({});
    expect(state.activeProposalId).toBeNull();
    expect(state.isPreviewModalOpen).toBe(false);
  });
});
