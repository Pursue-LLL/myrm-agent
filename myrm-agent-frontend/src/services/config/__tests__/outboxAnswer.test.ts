import { describe, expect, it } from 'vitest';
import { mergeAnswers, partitionByAnswer } from '@/services/config/outboxAnswer';
import type { ConfigChange, ConfigKey, SyncResult } from '@/services/config/types';

const change = (key: ConfigKey): ConfigChange => ({ key, value: {} as never, expectedVersion: '1000_0', timestamp: 1 });
const answer = (parts: Partial<SyncResult>): SyncResult => ({
  success: false,
  conflicts: [],
  newVersions: new Map(),
  ...parts,
});
const keys = (changes: ConfigChange[]) => changes.map((c) => c.key);

describe('partitionByAnswer', () => {
  const batch = [change('chatSettings'), change('commands'), change('channels')];

  it('accepts every key of a successful answer, named or not', () => {
    const { accepted, rejected, unnamed } = partitionByAnswer(batch, answer({ success: true }));

    expect(keys(accepted)).toEqual(['chatSettings', 'commands', 'channels']);
    expect([rejected, unnamed]).toEqual([[], []]);
  });

  it('sorts the keys of a failed answer by what it names: a version, a clash, or nothing', () => {
    const { accepted, rejected, unnamed } = partitionByAnswer(
      batch,
      answer({ conflicts: ['commands'], newVersions: new Map([['chatSettings', '2000_0']]) }),
    );

    expect(keys(accepted)).toEqual(['chatSettings']);
    expect(keys(rejected)).toEqual(['commands']);
    expect(keys(unnamed)).toEqual(['channels']);
  });

  it('rejects a clashing key even when the answer also carries a version for it', () => {
    const { accepted, rejected } = partitionByAnswer(
      [change('commands')],
      answer({ conflicts: ['commands'], newVersions: new Map([['commands', '2000_0']]) }),
    );

    expect(accepted).toEqual([]);
    expect(keys(rejected)).toEqual(['commands']);
  });
});

describe('mergeAnswers', () => {
  it('is the answer to nothing sent when there are no answers', () => {
    expect(mergeAnswers([])).toEqual({ success: true, conflicts: [], newVersions: new Map() });
  });

  it('succeeds only if every answer did, and carries every clash, version and the first error', () => {
    const merged = mergeAnswers([
      answer({ success: true, newVersions: new Map([['chatSettings', '2000_0']]) }),
      answer({ conflicts: ['commands'], error: 'first' }),
      answer({ success: true, newVersions: new Map([['channels', '2000_1']]), error: 'second' }),
    ]);

    expect(merged).toEqual({
      success: false,
      conflicts: ['commands'],
      newVersions: new Map([
        ['chatSettings', '2000_0'],
        ['channels', '2000_1'],
      ]),
      error: 'first',
    });
  });
});
