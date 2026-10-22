import { beforeEach, describe, expect, it } from 'vitest';
import { useUserQuestionNavStore } from '../useUserQuestionNavStore';

describe('useUserQuestionNavStore', () => {
  beforeEach(() => {
    useUserQuestionNavStore.getState().reset();
  });

  it('initializes with default empty state', () => {
    const state = useUserQuestionNavStore.getState();
    expect(state.questions).toEqual([]);
    expect(state.currentIndex).toBe(0);
    expect(state.isOutlineOpen).toBe(false);
    expect(state.pendingCount).toBe(0);
    expect(state.pendingItems).toEqual([]);
  });

  it('correctly filters user questions and builds question anchors', () => {
    const rawMessages = [
      { messageId: 'm1', role: 'user', content: 'What is the speed of light?' },
      { messageId: 'm2', role: 'assistant', content: '299,792,458 m/s' },
      { messageId: 'm3', role: 'user', content: 'And what about sound?' },
      { messageId: 'm4', role: 'assistant', content: 'Around 343 m/s in air.' },
    ];

    useUserQuestionNavStore.getState().syncMessages(rawMessages);

    const state = useUserQuestionNavStore.getState();
    expect(state.questions).toHaveLength(2);

    expect(state.questions[0]).toMatchObject({
      messageId: 'm1',
      messageIndex: 0,
      questionNumber: 1,
      summary: 'What is the speed of light?',
    });

    expect(state.questions[1]).toMatchObject({
      messageId: 'm3',
      messageIndex: 2,
      questionNumber: 2,
      summary: 'And what about sound?',
    });
  });

  it('truncates summaries longer than 40 chars', () => {
    const longPrompt = 'This is a very long question that exceeds forty characters and should be truncated with an ellipsis';
    useUserQuestionNavStore.getState().syncMessages([
      { messageId: 'long1', role: 'user', content: longPrompt },
    ]);

    const state = useUserQuestionNavStore.getState();
    expect(state.questions[0].summary.endsWith('...')).toBe(true);
    expect(state.questions[0].summary.length).toBe(43); // 40 chars + '...'
  });

  it('calculates pending cues below last visible index', () => {
    const messages = [
      { messageId: 'm1', role: 'user', content: 'First prompt' },
      { messageId: 'm2', role: 'assistant', content: 'First reply\nSecond line' },
      { messageId: 'm3', role: 'user', content: 'Second prompt' },
      { messageId: 'm4', role: 'assistant', content: 'Second reply' },
      { messageId: 'm5', role: 'assistant', content: 'Third reply' },
    ];

    // User is viewing up to m2 (index 1)
    useUserQuestionNavStore.getState().syncMessages(messages, 1);

    const state = useUserQuestionNavStore.getState();
    expect(state.pendingCount).toBe(3); // m3, m4, m5
    expect(state.pendingItems).toHaveLength(3);
    expect(state.pendingItems[0].role).toBe('user');
    expect(state.pendingItems[0].snippet).toBe('Second prompt');
    expect(state.pendingItems[1].role).toBe('assistant');
    expect(state.pendingItems[1].snippet).toBe('Second reply');
  });

  it('navigates previous and next questions safely with clamping', () => {
    const rawMessages = [
      { messageId: 'm1', role: 'user', content: 'Prompt 1' },
      { messageId: 'm2', role: 'assistant', content: 'Ans 1' },
      { messageId: 'm3', role: 'user', content: 'Prompt 2' },
      { messageId: 'm4', role: 'assistant', content: 'Ans 2' },
      { messageId: 'm5', role: 'user', content: 'Prompt 3' },
    ];

    useUserQuestionNavStore.getState().syncMessages(rawMessages);

    // Initial index 0
    expect(useUserQuestionNavStore.getState().getPreviousQuestion()).toBeNull();
    const nextQ = useUserQuestionNavStore.getState().getNextQuestion();
    expect(nextQ?.messageId).toBe('m3');

    // Move to index 1
    useUserQuestionNavStore.getState().setCurrentIndex(1);
    expect(useUserQuestionNavStore.getState().getPreviousQuestion()?.messageId).toBe('m1');
    expect(useUserQuestionNavStore.getState().getNextQuestion()?.messageId).toBe('m5');

    // Move to index 2 (last)
    useUserQuestionNavStore.getState().setCurrentIndex(2);
    expect(useUserQuestionNavStore.getState().getNextQuestion()).toBeNull();

    // Out-of-bounds clamping
    useUserQuestionNavStore.getState().setCurrentIndex(99);
    expect(useUserQuestionNavStore.getState().currentIndex).toBe(2);
  });

  it('manages outline drawer open/close state', () => {
    expect(useUserQuestionNavStore.getState().isOutlineOpen).toBe(false);

    useUserQuestionNavStore.getState().setOutlineOpen(true);
    expect(useUserQuestionNavStore.getState().isOutlineOpen).toBe(true);

    useUserQuestionNavStore.getState().setOutlineOpen(false);
    expect(useUserQuestionNavStore.getState().isOutlineOpen).toBe(false);
  });
});
