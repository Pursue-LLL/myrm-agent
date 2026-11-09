import { beforeEach, describe, expect, it } from 'vitest';

import useChatStore from '@/store/useChatStore';

import { prefillComposerWithUseCase } from '../prefillComposerWithUseCase';

const composerText = () => useChatStore.getState().inputMessage;

describe('prefillComposerWithUseCase', () => {
  beforeEach(() => {
    useChatStore.setState({ inputMessage: '' });
  });

  it('fills an empty composer with the use case', () => {
    prefillComposerWithUseCase('Review system refactoring plan');

    expect(composerText()).toBe('Review system refactoring plan');
  });

  it.each(['  ', '\n\t '])('treats a draft of only whitespace (%j) as empty', (blankDraft) => {
    useChatStore.setState({ inputMessage: blankDraft });

    prefillComposerWithUseCase('Review system refactoring plan');

    expect(composerText()).toBe('Review system refactoring plan');
  });

  it('never replaces a draft the viewer already typed', () => {
    useChatStore.setState({ inputMessage: 'my own draft' });

    prefillComposerWithUseCase('Review system refactoring plan');

    expect(composerText()).toBe('my own draft');
  });

  it.each([undefined, ''])('leaves the composer alone when the template has no use case (%j)', (useCase) => {
    prefillComposerWithUseCase(useCase);

    expect(composerText()).toBe('');
  });
});
