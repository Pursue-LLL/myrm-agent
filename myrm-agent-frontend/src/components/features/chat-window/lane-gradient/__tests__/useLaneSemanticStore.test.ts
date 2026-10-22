import { describe, it, expect, beforeEach } from 'vitest';
import { act } from '@testing-library/react';
import useChatStore from '@/store/useChatStore';
import { useLaneSemanticStore } from '../useLaneSemanticStore';

describe('useLaneSemanticStore', () => {
  beforeEach(() => {
    act(() => {
      useChatStore.setState({
        actionMode: 'fast',
        sandboxMode: false,
        workspaceDir: null,
      });
      useLaneSemanticStore.setState({
        manualLaneOverride: null,
        pendingGraduation: null,
        isGraduationDialogOpen: false,
        graduationHistory: [],
      });
    });
  });

  it('initializes with default empty state', () => {
    const state = useLaneSemanticStore.getState();
    expect(state.manualLaneOverride).toBeNull();
    expect(state.pendingGraduation).toBeNull();
    expect(state.isGraduationDialogOpen).toBe(false);
    expect(state.graduationHistory).toEqual([]);
  });

  it('triggers graduation when evaluating boundary-crossing text in chat lane', () => {
    const match = useLaneSemanticStore.getState().evaluateInputIntent('请把这段代码保存到 src/main.ts');

    expect(match).not.toBeNull();
    expect(match?.triggerKind).toBe('file_write');

    const state = useLaneSemanticStore.getState();
    expect(state.pendingGraduation).toEqual(match);
    expect(state.isGraduationDialogOpen).toBe(true);
  });

  it('does not trigger graduation for pure conversational text', () => {
    const match = useLaneSemanticStore.getState().evaluateInputIntent('请帮我写一首关于秋天的诗');

    expect(match).toBeNull();
    const state = useLaneSemanticStore.getState();
    expect(state.pendingGraduation).toBeNull();
    expect(state.isGraduationDialogOpen).toBe(false);
  });

  it('graduates to local workspace and synchronizes with useChatStore', () => {
    act(() => {
      useLaneSemanticStore.getState().evaluateInputIntent('请在终端运行 npm test');
    });

    expect(useLaneSemanticStore.getState().isGraduationDialogOpen).toBe(true);

    act(() => {
      useLaneSemanticStore.getState().graduateToWorkspace('local_workspace', '/my/project');
    });

    const storeState = useLaneSemanticStore.getState();
    expect(storeState.isGraduationDialogOpen).toBe(false);
    expect(storeState.pendingGraduation).toBeNull();
    expect(storeState.graduationHistory.length).toBe(1);
    expect(storeState.graduationHistory[0].toLane).toBe('workspace');
    expect(storeState.graduationHistory[0].toEnvMode).toBe('local_workspace');

    const chatState = useChatStore.getState();
    expect(chatState.actionMode).toBe('agent');
    expect(chatState.sandboxMode).toBe(false);
    expect(chatState.workspaceDir).toBe('/my/project');
  });

  it('graduates to cloud sandbox and sets sandboxMode true', () => {
    act(() => {
      useLaneSemanticStore.getState().graduateToWorkspace('cloud_sandbox');
    });

    const storeState = useLaneSemanticStore.getState();
    expect(storeState.graduationHistory.length).toBe(1);
    expect(storeState.graduationHistory[0].toEnvMode).toBe('cloud_sandbox');

    const chatState = useChatStore.getState();
    expect(chatState.actionMode).toBe('agent');
    expect(chatState.sandboxMode).toBe(true);
  });

  it('dismisses graduation and clears dialog state', () => {
    act(() => {
      useLaneSemanticStore.getState().setPendingGraduation({
        triggerKind: 'file_write',
        matchedKeyword: '保存到',
        confidence: 0.9,
        reason: '需要写文件',
        suggestedTargetMode: 'local_workspace',
        detectedSnippet: '保存到 a.txt',
      });
    });

    expect(useLaneSemanticStore.getState().isGraduationDialogOpen).toBe(true);

    act(() => {
      useLaneSemanticStore.getState().dismissGraduation();
    });

    const state = useLaneSemanticStore.getState();
    expect(state.isGraduationDialogOpen).toBe(false);
    expect(state.pendingGraduation).toBeNull();
  });

  it('supports manual override and history clearing', () => {
    act(() => {
      useLaneSemanticStore.getState().setManualLaneOverride('workspace');
    });
    expect(useLaneSemanticStore.getState().manualLaneOverride).toBe('workspace');

    act(() => {
      useLaneSemanticStore.getState().clearHistory();
    });
    expect(useLaneSemanticStore.getState().graduationHistory).toEqual([]);
  });
});
