import { describe, it, expect, beforeEach } from 'vitest';
import { useFlowPadStore } from '@/store/useFlowPadStore';

describe('useFlowPadStore', () => {
  beforeEach(() => {
    useFlowPadStore.setState({
      isOpen: false,
      mode: 'chat',
      captures: [],
      initialText: '',
      inlineResult: '',
      inlineGenerating: false,
      sourcePid: null,
    });
  });

  describe('openInline', () => {
    it('opens FlowPad in inline mode with capture and PID', () => {
      const capture = {
        screenshot: 'base64data',
        windowTitle: 'Gmail',
        extractedText: 'Hello world',
        timestamp: 1000,
      };

      useFlowPadStore.getState().openInline(capture, 12345);

      const state = useFlowPadStore.getState();
      expect(state.isOpen).toBe(true);
      expect(state.mode).toBe('inline');
      expect(state.captures).toHaveLength(1);
      expect(state.captures[0]).toEqual(capture);
      expect(state.sourcePid).toBe(12345);
      expect(state.inlineResult).toBe('');
      expect(state.inlineGenerating).toBe(false);
    });
  });

  describe('inlineResult management', () => {
    it('setState sets inlineResult and inlineGenerating directly', () => {
      useFlowPadStore.getState().openInline(
        { screenshot: '', windowTitle: '', extractedText: '', timestamp: 0 },
        1,
      );

      useFlowPadStore.setState({ inlineResult: 'Hello', inlineGenerating: true });

      expect(useFlowPadStore.getState().inlineResult).toBe('Hello');
      expect(useFlowPadStore.getState().inlineGenerating).toBe(true);
    });

    it('setState replaces inlineResult on each call (full replacement pattern)', () => {
      useFlowPadStore.setState({ inlineResult: 'H', inlineGenerating: true });
      useFlowPadStore.setState({ inlineResult: 'He', inlineGenerating: true });
      useFlowPadStore.setState({ inlineResult: 'Hello world', inlineGenerating: true });

      expect(useFlowPadStore.getState().inlineResult).toBe('Hello world');
    });

    it('finishInlineResult sets inlineGenerating to false', () => {
      useFlowPadStore.setState({ inlineResult: 'Done', inlineGenerating: true });
      useFlowPadStore.setState({ inlineGenerating: false });

      expect(useFlowPadStore.getState().inlineResult).toBe('Done');
      expect(useFlowPadStore.getState().inlineGenerating).toBe(false);
    });
  });

  describe('close', () => {
    it('resets all inline state on close', () => {
      useFlowPadStore.getState().openInline(
        { screenshot: 'data', windowTitle: 'App', extractedText: 'text', timestamp: 1 },
        999,
      );
      useFlowPadStore.setState({ inlineResult: 'Result text', inlineGenerating: true });

      useFlowPadStore.getState().close();

      const state = useFlowPadStore.getState();
      expect(state.isOpen).toBe(false);
      expect(state.mode).toBe('chat');
      expect(state.inlineResult).toBe('');
      expect(state.inlineGenerating).toBe(false);
      expect(state.sourcePid).toBe(null);
      expect(state.captures).toHaveLength(0);
    });
  });

  describe('subscribe bridge pattern', () => {
    it('subscribe notifies when state changes', () => {
      const changes: string[] = [];

      const unsub = useFlowPadStore.subscribe((state) => {
        if (state.inlineResult) {
          changes.push(state.inlineResult);
        }
      });

      useFlowPadStore.setState({ inlineResult: 'chunk1', inlineGenerating: true });
      useFlowPadStore.setState({ inlineResult: 'chunk1 chunk2', inlineGenerating: true });
      useFlowPadStore.setState({ inlineResult: 'chunk1 chunk2 chunk3', inlineGenerating: false });

      unsub();

      expect(changes).toEqual(['chunk1', 'chunk1 chunk2', 'chunk1 chunk2 chunk3']);
    });
  });
});
