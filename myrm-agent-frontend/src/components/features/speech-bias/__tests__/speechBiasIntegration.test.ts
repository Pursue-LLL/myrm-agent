import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useSpeechBiasStore } from '../useSpeechBiasStore';

describe('speechBiasIntegration', () => {
  beforeEach(() => {
    useSpeechBiasStore.getState().reset();
  });

  it('全链路：上下文注入 -> 分片听写 -> 智能纠偏 -> 单项撤销 -> 发送完成闭环', () => {
    const store = useSpeechBiasStore.getState();

    // 1. 注入项目上下文
    store.injectContextTerms({
      branch: 'refactor/speech-bias-pipeline',
      astSymbols: ['handleSpeechCorrection'],
      skills: ['workers-best-practices'],
    });

    const activeTerms = useSpeechBiasStore
      .getState()
      .lexicon.map((i) => i.term);
    expect(activeTerms).toContain('refactor/speech-bias-pipeline');
    expect(activeTerms).toContain('handleSpeechCorrection');

    // 2. 模拟用户语音输入
    store.startListening();
    expect(useSpeechBiasStore.getState().status).toBe('listening');

    store.appendTranscriptChunk('请使用 grape');
    store.appendTranscriptChunk('搜索所有的 handle speech correction 函数');
    store.appendTranscriptChunk('并用 pen pm test 校验');

    // 3. 听写结束触发纠偏
    store.finalizeTranscript();
    const finalState = useSpeechBiasStore.getState();

    expect(finalState.status).toBe('ready');
    expect(finalState.correctedTranscript).toContain('grep');
    expect(finalState.correctedTranscript).toContain('pnpm');
    expect(finalState.activeCorrections.length).toBeGreaterThanOrEqual(2);

    // 4. 模拟撤销其中某项纠偏
    const pnpmCorr = finalState.activeCorrections.find((c) => c.corrected === 'pnpm');
    expect(pnpmCorr).toBeDefined();
    if (pnpmCorr) {
      store.revertCorrection(pnpmCorr.id);
      expect(useSpeechBiasStore.getState().correctedTranscript).toContain('pen pm');
    }

    // 5. 模拟最终发送
    const onSendMock = vi.fn();
    onSendMock(useSpeechBiasStore.getState().correctedTranscript);
    store.reset();

    expect(onSendMock).toHaveBeenCalled();
    expect(useSpeechBiasStore.getState().status).toBe('idle');
  });

  it('关闭自动纠偏功能时，原始听写文本原样返回', () => {
    const store = useSpeechBiasStore.getState();
    store.toggleAutoCorrect(false);

    store.startListening();
    store.appendTranscriptChunk('使用 grape 和 pen pm');
    store.finalizeTranscript();

    const state = useSpeechBiasStore.getState();
    expect(state.status).toBe('ready');
    expect(state.correctedTranscript).toBe('使用 grape 和 pen pm');
    expect(state.activeCorrections.length).toBe(0);
  });
});
