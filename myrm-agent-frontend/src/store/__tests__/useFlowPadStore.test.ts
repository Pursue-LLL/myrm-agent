import { beforeEach, describe, expect, it } from 'vitest';
import { useFlowPadStore, type FlowPadCapture } from '@/store/useFlowPadStore';

function makeCapture(overrides: Partial<FlowPadCapture> = {}): FlowPadCapture {
  return {
    screenshot: 'base64data',
    windowTitle: 'Test Window',
    extractedText: 'Some extracted text',
    timestamp: Date.now(),
    ...overrides,
  };
}

describe('useFlowPadStore', () => {
  beforeEach(() => {
    useFlowPadStore.getState().close();
  });

  describe('open', () => {
    it('opens the modal with default empty text', () => {
      useFlowPadStore.getState().open();
      const state = useFlowPadStore.getState();
      expect(state.isOpen).toBe(true);
      expect(state.initialText).toBe('');
    });

    it('opens the modal with provided text', () => {
      useFlowPadStore.getState().open('Hello world');
      const state = useFlowPadStore.getState();
      expect(state.isOpen).toBe(true);
      expect(state.initialText).toBe('Hello world');
    });

    it('does not affect existing captures', () => {
      useFlowPadStore.getState().addCapture(makeCapture());
      expect(useFlowPadStore.getState().captures).toHaveLength(1);

      useFlowPadStore.getState().open('text');
      expect(useFlowPadStore.getState().captures).toHaveLength(1);
    });
  });

  describe('addCapture', () => {
    it('adds a capture and opens the modal', () => {
      const capture = makeCapture({ windowTitle: 'VS Code' });
      useFlowPadStore.getState().addCapture(capture);

      const state = useFlowPadStore.getState();
      expect(state.isOpen).toBe(true);
      expect(state.captures).toHaveLength(1);
      expect(state.captures[0].windowTitle).toBe('VS Code');
    });

    it('appends captures when already open', () => {
      useFlowPadStore.getState().addCapture(makeCapture({ windowTitle: 'Window 1' }));
      useFlowPadStore.getState().addCapture(makeCapture({ windowTitle: 'Window 2' }));

      const state = useFlowPadStore.getState();
      expect(state.captures).toHaveLength(2);
      expect(state.captures[0].windowTitle).toBe('Window 1');
      expect(state.captures[1].windowTitle).toBe('Window 2');
    });

    it('rejects capture when MAX_CAPTURES (10) is reached', () => {
      for (let i = 0; i < 10; i++) {
        useFlowPadStore.getState().addCapture(makeCapture({ windowTitle: `Win ${i}` }));
      }
      expect(useFlowPadStore.getState().captures).toHaveLength(10);

      useFlowPadStore.getState().addCapture(makeCapture({ windowTitle: 'Win 11' }));
      const state = useFlowPadStore.getState();
      expect(state.captures).toHaveLength(10);
      expect(state.captures.every((c) => c.windowTitle !== 'Win 11')).toBe(true);
    });

    it('returns unchanged state reference when at max capacity', () => {
      for (let i = 0; i < 10; i++) {
        useFlowPadStore.getState().addCapture(makeCapture());
      }
      const capturesBefore = useFlowPadStore.getState().captures;

      useFlowPadStore.getState().addCapture(makeCapture());
      const capturesAfter = useFlowPadStore.getState().captures;

      expect(capturesBefore).toBe(capturesAfter);
    });
  });

  describe('removeCapture', () => {
    it('removes capture at the specified index', () => {
      useFlowPadStore.getState().addCapture(makeCapture({ windowTitle: 'A' }));
      useFlowPadStore.getState().addCapture(makeCapture({ windowTitle: 'B' }));
      useFlowPadStore.getState().addCapture(makeCapture({ windowTitle: 'C' }));

      useFlowPadStore.getState().removeCapture(1);

      const state = useFlowPadStore.getState();
      expect(state.captures).toHaveLength(2);
      expect(state.captures[0].windowTitle).toBe('A');
      expect(state.captures[1].windowTitle).toBe('C');
    });

    it('handles removing the first capture', () => {
      useFlowPadStore.getState().addCapture(makeCapture({ windowTitle: 'First' }));
      useFlowPadStore.getState().addCapture(makeCapture({ windowTitle: 'Second' }));

      useFlowPadStore.getState().removeCapture(0);

      const state = useFlowPadStore.getState();
      expect(state.captures).toHaveLength(1);
      expect(state.captures[0].windowTitle).toBe('Second');
    });

    it('handles removing the last capture', () => {
      useFlowPadStore.getState().addCapture(makeCapture({ windowTitle: 'First' }));
      useFlowPadStore.getState().addCapture(makeCapture({ windowTitle: 'Last' }));

      useFlowPadStore.getState().removeCapture(1);

      const state = useFlowPadStore.getState();
      expect(state.captures).toHaveLength(1);
      expect(state.captures[0].windowTitle).toBe('First');
    });

    it('does not close the modal even if all captures are removed', () => {
      useFlowPadStore.getState().addCapture(makeCapture());
      useFlowPadStore.getState().removeCapture(0);

      const state = useFlowPadStore.getState();
      expect(state.captures).toHaveLength(0);
      expect(state.isOpen).toBe(true);
    });
  });

  describe('close', () => {
    it('resets all state', () => {
      useFlowPadStore.getState().open('some text');
      useFlowPadStore.getState().addCapture(makeCapture());

      useFlowPadStore.getState().close();

      const state = useFlowPadStore.getState();
      expect(state.isOpen).toBe(false);
      expect(state.captures).toHaveLength(0);
      expect(state.initialText).toBe('');
    });

    it('releases base64 capture data on close', () => {
      const largeScreenshot = 'x'.repeat(100000);
      useFlowPadStore.getState().addCapture(makeCapture({ screenshot: largeScreenshot }));
      expect(useFlowPadStore.getState().captures[0].screenshot).toHaveLength(100000);

      useFlowPadStore.getState().close();
      expect(useFlowPadStore.getState().captures).toHaveLength(0);
    });
  });

  describe('state isolation', () => {
    it('open does not overwrite captures', () => {
      useFlowPadStore.getState().addCapture(makeCapture({ windowTitle: 'Preserved' }));
      useFlowPadStore.getState().open('new text');

      const state = useFlowPadStore.getState();
      expect(state.captures).toHaveLength(1);
      expect(state.captures[0].windowTitle).toBe('Preserved');
      expect(state.initialText).toBe('new text');
    });

    it('addCapture does not modify initialText', () => {
      useFlowPadStore.getState().open('initial');
      useFlowPadStore.getState().addCapture(makeCapture());

      expect(useFlowPadStore.getState().initialText).toBe('initial');
    });
  });

  describe('edge cases', () => {
    it('removeCapture with out-of-bounds index leaves array unchanged', () => {
      useFlowPadStore.getState().addCapture(makeCapture({ windowTitle: 'Only' }));

      useFlowPadStore.getState().removeCapture(99);
      expect(useFlowPadStore.getState().captures).toHaveLength(1);
      expect(useFlowPadStore.getState().captures[0].windowTitle).toBe('Only');
    });

    it('removeCapture with negative index leaves array unchanged', () => {
      useFlowPadStore.getState().addCapture(makeCapture({ windowTitle: 'Only' }));

      useFlowPadStore.getState().removeCapture(-1);
      expect(useFlowPadStore.getState().captures).toHaveLength(1);
    });

    it('close then reopen starts with clean state', () => {
      useFlowPadStore.getState().open('first session');
      useFlowPadStore.getState().addCapture(makeCapture({ windowTitle: 'Old' }));
      useFlowPadStore.getState().close();

      useFlowPadStore.getState().open('second session');
      const state = useFlowPadStore.getState();
      expect(state.isOpen).toBe(true);
      expect(state.initialText).toBe('second session');
      expect(state.captures).toHaveLength(0);
    });

    it('addCapture with empty screenshot and text still adds', () => {
      useFlowPadStore.getState().addCapture(
        makeCapture({ screenshot: '', extractedText: '', windowTitle: '' }),
      );
      expect(useFlowPadStore.getState().captures).toHaveLength(1);
    });

    it('addCapture at exactly MAX_CAPTURES boundary (9 -> 10 succeeds, 10 -> 11 fails)', () => {
      for (let i = 0; i < 9; i++) {
        useFlowPadStore.getState().addCapture(makeCapture());
      }
      expect(useFlowPadStore.getState().captures).toHaveLength(9);

      useFlowPadStore.getState().addCapture(makeCapture({ windowTitle: 'Tenth' }));
      expect(useFlowPadStore.getState().captures).toHaveLength(10);
      expect(useFlowPadStore.getState().captures[9].windowTitle).toBe('Tenth');

      useFlowPadStore.getState().addCapture(makeCapture({ windowTitle: 'Eleventh' }));
      expect(useFlowPadStore.getState().captures).toHaveLength(10);
    });

    it('removeCapture then addCapture works after clearing capacity', () => {
      for (let i = 0; i < 10; i++) {
        useFlowPadStore.getState().addCapture(makeCapture({ windowTitle: `Win ${i}` }));
      }
      expect(useFlowPadStore.getState().captures).toHaveLength(10);

      useFlowPadStore.getState().removeCapture(0);
      expect(useFlowPadStore.getState().captures).toHaveLength(9);

      useFlowPadStore.getState().addCapture(makeCapture({ windowTitle: 'New After Remove' }));
      expect(useFlowPadStore.getState().captures).toHaveLength(10);
      expect(useFlowPadStore.getState().captures[9].windowTitle).toBe('New After Remove');
    });

    it('multiple close calls are idempotent', () => {
      useFlowPadStore.getState().open('test');
      useFlowPadStore.getState().close();
      useFlowPadStore.getState().close();
      useFlowPadStore.getState().close();

      const state = useFlowPadStore.getState();
      expect(state.isOpen).toBe(false);
      expect(state.captures).toHaveLength(0);
      expect(state.initialText).toBe('');
    });
  });
});
