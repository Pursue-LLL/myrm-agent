import { renderHook, act } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import {
  clearPromptHistory,
  getPromptHistory,
  recordPromptHistory,
  useMobilePromptHistory,
} from '../useMobilePromptHistory';

describe('useMobilePromptHistory', () => {
  const chatId = 'test-chat-history-1';
  const otherChatId = 'test-chat-history-2';

  beforeEach(() => {
    clearPromptHistory(chatId);
    clearPromptHistory(otherChatId);
  });

  describe('pure history functions', () => {
    it('records and returns history for a specific chatId', () => {
      expect(getPromptHistory(chatId)).toEqual([]);
      recordPromptHistory(chatId, 'First prompt');
      recordPromptHistory(chatId, 'Second prompt');
      expect(getPromptHistory(chatId)).toEqual(['First prompt', 'Second prompt']);
    });

    it('ignores empty or whitespace-only prompts', () => {
      recordPromptHistory(chatId, '   ');
      recordPromptHistory(chatId, '');
      expect(getPromptHistory(chatId)).toEqual([]);
    });

    it('deduplicates consecutive identical prompts', () => {
      recordPromptHistory(chatId, 'Repeat this');
      recordPromptHistory(chatId, 'Repeat this');
      expect(getPromptHistory(chatId)).toEqual(['Repeat this']);

      recordPromptHistory(chatId, 'Different');
      recordPromptHistory(chatId, 'Repeat this');
      expect(getPromptHistory(chatId)).toEqual(['Repeat this', 'Different', 'Repeat this']);
    });

    it('enforces maximum 20 items bound', () => {
      for (let i = 1; i <= 25; i++) {
        recordPromptHistory(chatId, `Prompt ${i}`);
      }
      const history = getPromptHistory(chatId);
      expect(history.length).toBe(20);
      expect(history[0]).toBe('Prompt 6');
      expect(history[19]).toBe('Prompt 25');
    });

    it('isolates history strictly by chatId', () => {
      recordPromptHistory(chatId, 'Chat 1 prompt');
      recordPromptHistory(otherChatId, 'Chat 2 prompt');

      expect(getPromptHistory(chatId)).toEqual(['Chat 1 prompt']);
      expect(getPromptHistory(otherChatId)).toEqual(['Chat 2 prompt']);
    });
  });

  describe('hook navigation', () => {
    it('walks backwards through history and stays on the oldest item', () => {
      const { result } = renderHook(() => useMobilePromptHistory(chatId));

      act(() => {
        result.current.pushHistory('Command A');
        result.current.pushHistory('Command B');
      });

      expect(result.current.historyCount).toBe(2);
      expect(result.current.currentIndex).toBe(-1);

      let navigated: string | null = null;
      act(() => {
        navigated = result.current.navigatePrevious();
      });
      expect(navigated).toBe('Command B');
      expect(result.current.currentIndex).toBe(1);

      act(() => {
        navigated = result.current.navigatePrevious();
      });
      expect(navigated).toBe('Command A');
      expect(result.current.currentIndex).toBe(0);

      act(() => {
        navigated = result.current.navigatePrevious();
      });
      expect(navigated).toBe('Command A');
      expect(result.current.currentIndex).toBe(0);
    });

    it('returns null when navigating empty history', () => {
      const { result } = renderHook(() => useMobilePromptHistory(chatId));
      let navigated: string | null = null;
      act(() => {
        navigated = result.current.navigatePrevious();
      });
      expect(navigated).toBeNull();
    });

    it('resets navigation index on resetNavigation', () => {
      const { result } = renderHook(() => useMobilePromptHistory(chatId));
      act(() => {
        result.current.pushHistory('Cmd 1');
      });
      act(() => {
        result.current.navigatePrevious();
      });
      expect(result.current.currentIndex).toBe(0);

      act(() => {
        result.current.resetNavigation();
      });
      expect(result.current.currentIndex).toBe(-1);
    });

    it('leaves browsing mode when a new prompt is pushed', () => {
      const { result } = renderHook(() => useMobilePromptHistory(chatId));
      act(() => {
        result.current.pushHistory('Cmd 1');
      });
      act(() => {
        result.current.navigatePrevious();
      });
      expect(result.current.currentIndex).toBe(0);

      act(() => {
        result.current.pushHistory('Cmd 2');
      });
      expect(result.current.currentIndex).toBe(-1);
    });

    it('allows pushing uncommitted draft as defensive snapshot and immediately retrieving it', () => {
      const { result } = renderHook(() => useMobilePromptHistory(chatId));
      // User typed an uncommitted draft and cleared it
      const uncommittedDraft = 'Complex multi-word prompt that was cleared';
      act(() => {
        result.current.pushHistory(uncommittedDraft);
        result.current.resetNavigation();
      });

      expect(result.current.historyCount).toBe(1);
      let recovered: string | null = null;
      act(() => {
        recovered = result.current.navigatePrevious();
      });
      expect(recovered).toBe(uncommittedDraft);
    });
  });
});
