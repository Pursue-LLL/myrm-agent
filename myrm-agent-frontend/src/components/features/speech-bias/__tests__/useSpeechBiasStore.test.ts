import { describe, it, expect, beforeEach } from 'vitest';
import { useSpeechBiasStore } from '../useSpeechBiasStore';

describe('useSpeechBiasStore', () => {
  beforeEach(() => {
    useSpeechBiasStore.getState().reset();
  });

  it('初始状态规范合规', () => {
    const state = useSpeechBiasStore.getState();
    expect(state.status).toBe('idle');
    expect(state.rawTranscript).toBe('');
    expect(state.correctedTranscript).toBe('');
    expect(state.activeCorrections).toEqual([]);
    expect(state.isAutoCorrectEnabled).toBe(true);
    expect(state.isDrawerOpen).toBe(false);
    expect(state.lexicon.length).toBeGreaterThan(0);
  });

  it('支持开始听写与分片追加语音输入', () => {
    const store = useSpeechBiasStore.getState();
    store.startListening();

    expect(useSpeechBiasStore.getState().status).toBe('listening');

    store.appendTranscriptChunk('使用 grape 查找');
    store.appendTranscriptChunk('所有包含 pen pm 的文件');

    expect(useSpeechBiasStore.getState().rawTranscript).toBe(
      '使用 grape 查找 所有包含 pen pm 的文件'
    );
  });

  it('支持结束听写并自动触发术语偏置纠偏', () => {
    const store = useSpeechBiasStore.getState();
    store.startListening();
    store.appendTranscriptChunk('部署到 库伯拉提斯 集群');
    store.finalizeTranscript();

    const state = useSpeechBiasStore.getState();
    expect(state.status).toBe('ready');
    expect(state.correctedTranscript).toContain('Kubernetes');
    expect(state.activeCorrections.length).toBe(1);
    expect(state.activeCorrections[0]?.corrected).toBe('Kubernetes');
  });

  it('支持撤销特定的术语纠偏替换', () => {
    const store = useSpeechBiasStore.getState();
    store.startListening();
    store.appendTranscriptChunk('用 grape 命令');
    store.finalizeTranscript();

    const stateBefore = useSpeechBiasStore.getState();
    expect(stateBefore.correctedTranscript).toBe('用 grep 命令');
    const corrId = stateBefore.activeCorrections[0]?.id;
    expect(corrId).toBeDefined();

    if (corrId) {
      store.revertCorrection(corrId);
    }

    const stateAfter = useSpeechBiasStore.getState();
    expect(stateAfter.correctedTranscript).toBe('用 grape 命令');
    expect(stateAfter.activeCorrections.length).toBe(0);
  });

  it('支持注入项目上下文术语和添加自定义术语', () => {
    const store = useSpeechBiasStore.getState();
    store.injectContextTerms({
      branch: 'fix/auth-bug',
      astSymbols: ['sanitizeUserInput'],
      skills: ['my-custom-skill'],
    });

    const state = useSpeechBiasStore.getState();
    expect(state.activeBranchName).toBe('fix/auth-bug');
    expect(state.recentAstSymbols).toContain('sanitizeUserInput');
    expect(state.installedSkills).toContain('my-custom-skill');

    store.addCustomTerm('MyrmidonCore', ['迈密顿核心', 'myrmidon core']);
    const customItem = useSpeechBiasStore
      .getState()
      .lexicon.find((item) => item.term === 'MyrmidonCore');
    expect(customItem).toBeDefined();
    expect(customItem?.aliases).toContain('迈密顿核心');

    if (customItem) {
      store.removeTerm(customItem.id);
      expect(
        useSpeechBiasStore.getState().lexicon.some((item) => item.id === customItem.id)
      ).toBe(false);
    }
  });

  it('支持切换自动纠偏开关与抽屉显隐', () => {
    const store = useSpeechBiasStore.getState();
    store.toggleAutoCorrect(false);
    expect(useSpeechBiasStore.getState().isAutoCorrectEnabled).toBe(false);

    store.setDrawerOpen(true);
    expect(useSpeechBiasStore.getState().isDrawerOpen).toBe(true);
  });
});
