import { describe, expect, it } from 'vitest';

import { getStepVisualState, progressTextTone, stepTitleTone, type StepVisualState } from '../stepTone';
import { makeStep } from './progressStepsKit';

const NONE: StepVisualState = {
  isWarning: false,
  isBlocked: false,
  isError: false,
  isCurrent: false,
  isCompleted: false,
};

describe('getStepVisualState', () => {
  it('calls a finished step without an error completed', () => {
    expect(getStepVisualState(makeStep(), false)).toEqual({ ...NONE, isCompleted: true });
  });

  it('calls the step in flight current, and not completed', () => {
    expect(getStepVisualState(makeStep({ status: undefined }), true)).toEqual({ ...NONE, isCurrent: true });
  });

  it.each([
    ['a text', 'it failed'],
    ['a bare flag', true],
  ])('calls a step with %s as its error an error', (_kind, error) => {
    expect(getStepVisualState(makeStep({ status: 'error', error }), false)).toEqual({ ...NONE, isError: true });
  });

  it('keeps a step that has an error out of completed, even when it is not in flight', () => {
    expect(getStepVisualState(makeStep({ status: 'success', error: 'late failure' }), false).isCompleted).toBe(false);
  });

  it('reads a warning status as a warning, not as an error', () => {
    expect(getStepVisualState(makeStep({ status: 'warning', error: 'cancelled' }), false)).toEqual({
      ...NONE,
      isWarning: true,
    });
  });

  it.each(['user_declined', 'approval_timeout'])('reads a %s refusal as a warning, not as an error', (category) => {
    const state = getStepVisualState(makeStep({ status: 'error', error: 'no', error_category: category }), false);

    expect(state.isWarning).toBe(true);
    expect(state.isError).toBe(false);
  });

  it('reads any other refusal category as an error', () => {
    const state = getStepVisualState(
      makeStep({ status: 'error', error: 'no', error_category: 'policy_denied' }),
      false,
    );

    expect(state).toEqual({ ...NONE, isError: true });
  });

  it('reads a blocked step as blocked, not as an error', () => {
    expect(getStepVisualState(makeStep({ status: 'blocked', error: 'waiting' }), false)).toEqual({
      ...NONE,
      isBlocked: true,
    });
  });

  it('can be in flight and in error at once', () => {
    const state = getStepVisualState(makeStep({ status: 'error', error: 'it failed' }), true);

    expect(state.isCurrent).toBe(true);
    expect(state.isError).toBe(true);
    expect(state.isCompleted).toBe(false);
  });
});

describe('stepTitleTone', () => {
  const AMBER = 'text-amber-600 dark:text-amber-400';

  it.each([
    ['warning', { ...NONE, isWarning: true }],
    ['blocked', { ...NONE, isBlocked: true }],
  ])('draws a %s step in amber', (_name, state) => {
    expect(stepTitleTone(state, 'idle-tone')).toBe(AMBER);
  });

  it('draws an error in the destructive text token, never the fill token', () => {
    expect(stepTitleTone({ ...NONE, isError: true }, 'idle-tone')).toBe('text-destructive-text');
  });

  it.each([
    ['completed', { ...NONE, isCompleted: true }],
    ['in flight', { ...NONE, isCurrent: true }],
    ['pending', NONE],
  ])('hands a %s step the idle tone the caller asked for', (_name, state) => {
    expect(stepTitleTone(state, 'idle-tone')).toBe('idle-tone');
  });
});

describe('progressTextTone', () => {
  it.each([
    ['alert', 'text-destructive-text'],
    ['warn', 'text-amber-600 dark:text-amber-400'],
    ['info', 'text-muted-foreground/60'],
    [undefined, 'text-muted-foreground/60'],
  ] as const)('draws the %s level of progress in %s', (level, tone) => {
    expect(progressTextTone(level)).toBe(tone);
  });
});
