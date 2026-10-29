import { describe, expect, it } from 'vitest';

import { hasEditedChanges, initialEditedArgs, parseEditedArgs, type InputEntry } from '../editedArgs';

describe('initialEditedArgs', () => {
  it('shows strings as they are, objects as indented JSON, and missing values as empty text', () => {
    const entries: InputEntry[] = [
      ['command', 'ls -la'],
      ['options', { depth: 2 }],
      ['timeout', 30],
      ['cwd', null],
      ['env', undefined],
    ];

    expect(initialEditedArgs(entries)).toEqual({
      command: 'ls -la',
      options: '{\n  "depth": 2\n}',
      timeout: '30',
      cwd: '',
      env: '',
    });
  });
});

describe('parseEditedArgs', () => {
  it('restores JSON values to their type and keeps plain text as a string', () => {
    const { parsed, invalidFields } = parseEditedArgs({
      timeout: '30',
      enabled: 'true',
      options: '{"depth": 2}',
      command: 'ls -la',
    });

    expect(parsed).toEqual({ timeout: 30, enabled: true, options: { depth: 2 }, command: 'ls -la' });
    expect(invalidFields).toEqual([]);
  });

  it('flags a field that starts like an object or array but is not valid JSON', () => {
    const { invalidFields } = parseEditedArgs({ options: '{"depth": ', items: '[1, 2', note: 'a {braced} word' });

    expect(invalidFields).toEqual(['options', 'items']);
  });
});

describe('hasEditedChanges', () => {
  const entries: InputEntry[] = [
    ['command', 'ls'],
    ['options', { depth: 2 }],
    ['cwd', null],
  ];

  it('is false when nothing was touched, including a null parameter shown as empty text', () => {
    expect(hasEditedChanges(entries, initialEditedArgs(entries))).toBe(false);
  });

  it('is true as soon as one field differs from what the editor started with', () => {
    expect(hasEditedChanges(entries, { ...initialEditedArgs(entries), command: 'ls -la' })).toBe(true);
    expect(hasEditedChanges(entries, { ...initialEditedArgs(entries), cwd: '/tmp' })).toBe(true);
  });
});
