import { describe, expect, it } from 'vitest';
import type { CommandBindingConfig } from '@/services/agent';
import {
  areBindingsEqual,
  findBindingIssues,
  normalizeBinding,
  parseAliasList,
  sanitizeCommandToken,
  toBindingsPayload,
} from '../commandBindings';

const binding = (overrides: Partial<CommandBindingConfig> = {}): CommandBindingConfig => ({
  command_name: 'report',
  skill_ids: ['skill-a'],
  ...overrides,
});

describe('sanitizeCommandToken', () => {
  it('keeps letters, digits, underscores and hyphens only', () => {
    expect(sanitizeCommandToken('Daily_Report-2!? /来')).toBe('Daily_Report-2');
  });

  it('caps the length at the server limit', () => {
    expect(sanitizeCommandToken('a'.repeat(80))).toHaveLength(50);
  });
});

describe('parseAliasList', () => {
  it('splits on commas, cleans each alias and drops empty ones', () => {
    expect(parseAliasList('dr, report ,, a b ,')).toEqual(['dr', 'report', 'ab']);
  });

  it('returns an empty list for blank input', () => {
    expect(parseAliasList('  ,  ')).toEqual([]);
  });
});

describe('normalizeBinding', () => {
  it('fills the optional fields the server would default', () => {
    expect(normalizeBinding({ command_name: 'x', skill_ids: ['s'] })).toEqual({
      command_name: 'x',
      skill_ids: ['s'],
      description: '',
      aliases: [],
      instruction: '',
    });
  });
});

describe('findBindingIssues', () => {
  it('accepts complete bindings with distinct names and aliases', () => {
    expect(
      findBindingIssues([binding(), binding({ command_name: 'summary', aliases: ['sum'], skill_ids: ['a', 'b'] })]),
    ).toEqual([null, null]);
  });

  it('flags a missing name or an empty skill list as incomplete', () => {
    expect(findBindingIssues([binding({ command_name: '' }), binding({ command_name: 'x', skill_ids: [] })])).toEqual([
      'incomplete',
      'incomplete',
    ]);
  });

  it('treats a blank row as incomplete rather than a duplicate of another blank row', () => {
    expect(
      findBindingIssues([binding({ command_name: '', skill_ids: [] }), binding({ command_name: '', skill_ids: [] })]),
    ).toEqual(['incomplete', 'incomplete']);
  });

  it('flags both bindings that share a command name, ignoring case', () => {
    expect(findBindingIssues([binding({ command_name: 'Report' }), binding({ command_name: 'report' })])).toEqual([
      'duplicate',
      'duplicate',
    ]);
  });

  it('flags an alias that collides with another binding’s name or alias', () => {
    expect(
      findBindingIssues([
        binding({ command_name: 'report', aliases: ['dr'] }),
        binding({ command_name: 'daily', aliases: ['DR'] }),
        binding({ command_name: 'dr' }),
        binding({ command_name: 'other' }),
      ]),
    ).toEqual(['duplicate', 'duplicate', 'duplicate', null]);
  });

  it('does not treat a binding repeating its own name as an alias as a duplicate', () => {
    expect(findBindingIssues([binding({ aliases: ['report'] })])).toEqual([null]);
  });
});

describe('toBindingsPayload', () => {
  it('sends null for an empty draft so the server clears the bindings', () => {
    expect(toBindingsPayload([])).toBeNull();
  });

  it('sends normalized bindings otherwise', () => {
    expect(toBindingsPayload([binding()])).toEqual([
      { command_name: 'report', skill_ids: ['skill-a'], description: '', aliases: [], instruction: '' },
    ]);
  });
});

describe('areBindingsEqual', () => {
  it('ignores defaults the server fills in', () => {
    expect(areBindingsEqual([binding()], [binding({ description: '', aliases: [], instruction: '' })])).toBe(true);
  });

  it('detects edits to any field, including skill order', () => {
    const base = binding({ skill_ids: ['a', 'b'] });
    expect(areBindingsEqual([base], [binding({ skill_ids: ['b', 'a'] })])).toBe(false);
    expect(areBindingsEqual([base], [{ ...base, description: 'x' }])).toBe(false);
    expect(areBindingsEqual([base], [{ ...base, aliases: ['r'] }])).toBe(false);
    expect(areBindingsEqual([base], [])).toBe(false);
  });
});
