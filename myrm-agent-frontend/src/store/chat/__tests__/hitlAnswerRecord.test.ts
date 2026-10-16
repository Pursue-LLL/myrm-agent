/**
 * What a settled clarification card shows is read back from the record the server persisted, so the
 * summarizers must trust nothing: a record that does not fit the card it sits on falls back to the plain answered label.
 */
import { describe, expect, it } from 'vitest';

import {
  clarificationAnswerAsText,
  isHitlAnswerRecord,
  summarizeClarificationRecord,
} from '@/store/chat/hitlAnswerRecord';
import type { ClarificationForm, HitlAnswerRecord } from '@/store/chat/types';

const form: ClarificationForm = {
  title: 'Deployment',
  questions: [
    {
      id: 'strategy',
      prompt: 'Choose a strategy',
      options: [
        { id: 'blue-green', label: 'Blue green' },
        { id: 'canary', label: 'Canary' },
      ],
    },
    { id: 'notes', prompt: 'Anything else?' },
  ],
};

const user = (value: unknown): HitlAnswerRecord => ({ by: 'user', value });

describe('isHitlAnswerRecord', () => {
  it.each([
    ['a user record', { by: 'user', value: {} }, true],
    ['a timeout record', { by: 'timeout', value: null }, true],
    ['a record without a value', { by: 'user' }, false],
    ['an unknown author', { by: 'agent', value: {} }, false],
    ['a string', 'answered', false],
    ['null', null, false],
  ])('%s', (_label, candidate, expected) => {
    expect(isHitlAnswerRecord(candidate)).toBe(expected);
  });
});

describe('summarizeClarificationRecord', () => {
  it('has nothing to say about a card that was settled before records existed', () => {
    expect(summarizeClarificationRecord(undefined, form)).toBeNull();
  });

  it('shows the option label and the free text the user gave to each question', () => {
    const record = user({ strategy: 'blue-green', notes: 'ship on Friday' });

    expect(summarizeClarificationRecord(record, form)).toEqual({
      kind: 'answered',
      lines: [
        { key: 'strategy', prompt: 'Choose a strategy', text: 'Blue green' },
        { key: 'notes', prompt: 'Anything else?', text: 'ship on Friday' },
      ],
    });
  });

  it('joins a multiple choice answer and keeps text the form has no option for', () => {
    const record = user({ strategy: ['blue-green', 'canary', 'my own idea'] });

    expect(summarizeClarificationRecord(record, form)).toEqual({
      kind: 'answered',
      lines: [{ key: 'strategy', prompt: 'Choose a strategy', text: 'Blue green, Canary, my own idea' }],
    });
  });

  it('shows a single-question answer as it was typed', () => {
    expect(summarizeClarificationRecord(user(['Paris', 'Tokyo']), undefined)).toEqual({
      kind: 'answered',
      lines: [{ key: 'answer', text: 'Paris, Tokyo' }],
    });
    expect(summarizeClarificationRecord(user('Paris'), undefined)).toEqual({
      kind: 'answered',
      lines: [{ key: 'answer', text: 'Paris' }],
    });
  });

  it.each([
    ['an empty form answer', {}],
    ['an empty text', ''],
    ['an empty list', []],
    ['a blank text', '   '],
  ])('reports a skip for %s', (_label, value) => {
    expect(summarizeClarificationRecord(user(value), form)).toEqual({ kind: 'skipped' });
  });

  it('reports the timeout whatever default value it resumed with', () => {
    expect(summarizeClarificationRecord({ by: 'timeout', value: {} }, form)).toEqual({ kind: 'timeout' });
    expect(summarizeClarificationRecord({ by: 'timeout', value: null }, form)).toEqual({ kind: 'timeout' });
  });

  it.each([
    ['answers to questions this form never asked', { unrelated: 'x' }],
    ['a value of the wrong shape', 42],
    ['an answer that is not text', { strategy: { nested: true } }],
    ['no value at all', null],
  ])('falls back to the plain label for %s', (_label, value) => {
    expect(summarizeClarificationRecord(user(value), form)).toBeNull();
  });

  it('cannot read a form answer without the form that gives it meaning', () => {
    expect(summarizeClarificationRecord(user({ strategy: 'blue-green' }), undefined)).toBeNull();
  });
});

describe('clarificationAnswerAsText', () => {
  it('writes each answered question as a line of the message the user would send', () => {
    expect(clarificationAnswerAsText({ strategy: ['canary'], notes: 'after the freeze' }, form)).toBe(
      'Choose a strategy: Canary\nAnything else?: after the freeze',
    );
  });

  it('sends a free-text answer as it was typed', () => {
    expect(clarificationAnswerAsText('  ship it on Friday ', undefined)).toBe('ship it on Friday');
  });

  it.each([
    ['a skip', {}],
    ['an empty answer', ''],
    ['an answer the form cannot explain', { unrelated: 'x' }],
  ])('has nothing to send for %s', (_label, value) => {
    expect(clarificationAnswerAsText(value, form)).toBe('');
  });
});
