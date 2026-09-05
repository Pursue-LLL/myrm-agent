import { describe, it, expect } from 'vitest';
import { buildBuiltinActions } from '@/store/builtinActions';

describe('buildBuiltinActions', () => {
  const actions = buildBuiltinActions();

  it('returns 15 builtin actions', () => {
    expect(actions).toHaveLength(15);
  });

  it('all actions have required fields', () => {
    for (const action of actions) {
      expect(action.id).toMatch(/^builtin:/);
      expect(action.name).toBeTruthy();
      expect(action.description).toBeTruthy();
      expect(action.type).toBe('action');
      expect(typeof action.execute).toBe('function');
    }
  });

  it('actions that support arguments have argsHint', () => {
    const compact = actions.find((a) => a.name === 'compact')!;
    expect(compact.argsHint).toBe('[topic]');

    const yolo = actions.find((a) => a.name === 'yolo')!;
    expect(yolo.argsHint).toBe('[on|off|<seconds>]');

    const freeze = actions.find((a) => a.name === 'freeze')!;
    expect(freeze.argsHint).toBe('[off|resume]');
  });

  it('actions with aliases have correct aliases', () => {
    const compact = actions.find((a) => a.name === 'compact')!;
    expect(compact.aliases).toEqual(['compress']);

    const freeze = actions.find((a) => a.name === 'freeze')!;
    expect(freeze.aliases).toEqual(['estop']);

    const newCmd = actions.find((a) => a.name === 'new')!;
    expect(newCmd.aliases).toEqual(['reset']);

    const stop = actions.find((a) => a.name === 'stop')!;
    expect(stop.aliases).toEqual(['cancel', 'abort']);

    const model = actions.find((a) => a.name === 'model')!;
    expect(model.aliases).toEqual(['switch-model']);

    const fork = actions.find((a) => a.name === 'fork')!;
    expect(fork.aliases).toEqual(['branch']);

    const loop = actions.find((a) => a.name === 'loop')!;
    expect(loop.argsHint).toBe('[interval] <prompt>');
    expect(loop.aliases).toEqual(['repeat', 'cron']);

    const pet = actions.find((a) => a.name === 'pet')!;
    expect(pet.argsHint).toBe('[toggle | list | <slug>]');
    expect(pet.aliases).toEqual(['pets']);

    const memo = actions.find((a) => a.name === 'memo')!;
    expect(memo.argsHint).toBe('[transcript | topic]');
    expect(memo.aliases).toEqual(['meeting', 'minutes']);

    const reviewWeek = actions.find((a) => a.name === 'review-week')!;
    expect(reviewWeek.argsHint).toBe('[timeframe | focus-area]');
    expect(reviewWeek.aliases).toEqual(['week-review', 'weekly-digest', 'extract-blockers']);
  });

  it('focus action has no argsHint (no arguments)', () => {
    const focus = actions.find((a) => a.name === 'focus')!;
    expect(focus.argsHint).toBeUndefined();
  });

  it('all action ids are unique', () => {
    const ids = actions.map((a) => a.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('all action names are unique', () => {
    const names = actions.map((a) => a.name);
    expect(new Set(names).size).toBe(names.length);
  });

  it('expected action names exist', () => {
    const names = actions.map((a) => a.name);
    expect(names).toEqual(
      expect.arrayContaining([
        'compact',
        'focus',
        'yolo',
        'freeze',
        'new',
        'stop',
        'model',
        'learn',
        'fork',
        'goal',
        'loop',
        'pet',
        'memo',
        'review-week',
      ]),
    );
  });
});
