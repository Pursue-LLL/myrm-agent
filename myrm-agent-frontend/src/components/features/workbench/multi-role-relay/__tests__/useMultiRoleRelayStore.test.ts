import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useMultiRoleRelayStore } from '../useMultiRoleRelayStore';

describe('useMultiRoleRelayStore Zustand store', () => {
  beforeEach(() => {
    useMultiRoleRelayStore.getState().resetState();
  });

  it('initializes with default stages and first stage snapshot', () => {
    const state = useMultiRoleRelayStore.getState();
    expect(state.stages.length).toBe(3);
    expect(state.activeStageId).toBe('stage-analyst');
    expect(state.selectedSnapshot?.stageId).toBe('stage-researcher');
    expect(state.isDiffStudioOpen).toBe(false);
    expect(state.activeForkBranch).toBeNull();
  });

  it('selects stage snapshot when stage has an artifact', () => {
    useMultiRoleRelayStore.getState().selectStageSnapshot('stage-analyst');
    const state = useMultiRoleRelayStore.getState();

    expect(state.selectedSnapshot?.stageId).toBe('stage-analyst');
    expect(state.selectedSnapshot?.artifactName).toBe('商业护城河与定价建议.md');
  });

  it('controls diff studio modal visibility and target snapshot selection', () => {
    useMultiRoleRelayStore.getState().openDiffStudio('snap-analyst-1');
    expect(useMultiRoleRelayStore.getState().isDiffStudioOpen).toBe(true);
    expect(useMultiRoleRelayStore.getState().selectedSnapshot?.id).toBe('snap-analyst-1');

    useMultiRoleRelayStore.getState().closeDiffStudio();
    expect(useMultiRoleRelayStore.getState().isDiffStudioOpen).toBe(false);
  });

  it('creates fork branch and applies modification to stage snapshot', () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');

    useMultiRoleRelayStore.getState().selectStageSnapshot('stage-analyst');

    const branch = useMultiRoleRelayStore.getState().createFork(
      'conservative-tier',
      '# 修正后的定价策略\n- 统一上调至 $49/mo 并扩充算力准备金',
      '风险控制调整'
    );

    expect(branch).not.toBeNull();
    const branchId = branch?.id ?? '';
    useMultiRoleRelayStore.getState().applyForkBranch(branchId);

    const updatedState = useMultiRoleRelayStore.getState();
    expect(updatedState.isDiffStudioOpen).toBe(false);
    expect(updatedState.forkHistory.length).toBe(1);

    const analystStage = updatedState.stages.find((s) => s.id === 'stage-analyst');
    expect(analystStage?.snapshot?.version).toBe(2);
    expect(analystStage?.snapshot?.rawContent).toContain('$49/mo');

    expect(dispatchSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'myrm:relay-artifact-forked',
      })
    );

    dispatchSpy.mockRestore();
  });

  it('advances pipeline to next relay stage', () => {
    useMultiRoleRelayStore.getState().advancePipeline();
    const state = useMultiRoleRelayStore.getState();

    const analystStage = state.stages.find((s) => s.id === 'stage-analyst');
    const copywriterStage = state.stages.find((s) => s.id === 'stage-copywriter');

    expect(analystStage?.status).toBe('completed');
    expect(copywriterStage?.status).toBe('in_progress');
    expect(state.activeStageId).toBe('stage-copywriter');
  });
});
