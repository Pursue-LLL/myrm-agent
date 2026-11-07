import { describe, expect, it } from 'vitest';

import type { BatchProjectStatus } from '@/services/batch-directory';
import { batchProgressPercent, deriveProjectFlags, formatDateTime, isTaskRetryable } from '../batchProjectModel';
import { mkDetail, mkTask } from './batchTestKit';

describe('formatDateTime', () => {
  it.each([null, undefined, '', 'not-a-date'])('returns a dash for %j', (value) => {
    expect(formatDateTime(value)).toBe('—');
  });

  it('formats valid ISO timestamps with the local locale', () => {
    expect(formatDateTime('2026-01-02T03:04:05Z')).toBe(new Date('2026-01-02T03:04:05Z').toLocaleString());
  });
});

describe('batchProgressPercent', () => {
  const progress = (total_tasks: number, completed_tasks: number, failed_tasks: number) => ({
    total_tasks,
    completed_tasks,
    failed_tasks,
  });

  it.each([
    [0, 0, 0, 0],
    [4, 0, 0, 0],
    [4, 1, 1, 50],
    [3, 1, 0, 33],
    [3, 1, 1, 67],
    [3, 2, 1, 100],
  ])('%i total, %i completed, %i failed gives %i percent', (total, completed, failed, expected) => {
    expect(batchProgressPercent(progress(total, completed, failed))).toBe(expected);
  });
});

describe('deriveProjectFlags', () => {
  const FLAGS: [BatchProjectStatus, { running: boolean; paused: boolean; terminal: boolean; active: boolean }][] = [
    ['draft', { running: false, paused: false, terminal: false, active: false }],
    ['running', { running: true, paused: false, terminal: false, active: true }],
    ['paused', { running: false, paused: true, terminal: false, active: true }],
    ['completed', { running: false, paused: false, terminal: true, active: false }],
    ['failed', { running: false, paused: false, terminal: true, active: false }],
    ['cancelled', { running: false, paused: false, terminal: true, active: false }],
  ];

  it.each(FLAGS)('derives the status flags of a %s project', (status, expected) => {
    expect(deriveProjectFlags(mkDetail({ status }))).toMatchObject(expected);
  });

  it('counts in-review tasks', () => {
    const tasks = [
      mkTask({ task_id: 'a', status: 'in_review' }),
      mkTask({ task_id: 'b', status: 'completed' }),
      mkTask({ task_id: 'c', status: 'in_review' }),
    ];
    expect(deriveProjectFlags(mkDetail({ tasks })).inReviewCount).toBe(2);
    expect(deriveProjectFlags(mkDetail({ tasks: [] })).inReviewCount).toBe(0);
  });

  it.each([
    [['/a'], [], true],
    [[], ['/a'], true],
    [['/a'], ['/b'], true],
    [[], [], false],
    [undefined, undefined, false],
  ])('hasRetryable for failed %j and missing %j is %s', (failed, missing, expected) => {
    const project = mkDetail({ failed_directories: failed, missing_artifact_directories: missing });
    expect(deriveProjectFlags(project).hasRetryable).toBe(expected);
  });
});

describe('isTaskRetryable', () => {
  it.each([
    [{ status: 'failed' }, true],
    [{ status: 'archived' }, true],
    [{ status: 'completed', artifact_status: 'missing' }, true],
    [{ status: 'completed', artifact_status: 'verified' }, false],
    [{ status: 'completed', artifact_status: 'not_specified' }, false],
    [{ status: 'completed' }, false],
    [{ status: 'running' }, false],
    [{ status: 'pending' }, false],
    [{ status: 'in_review' }, false],
    [{ status: 'blocked' }, false],
    [{ status: 'running', artifact_status: 'missing' }, false],
  ] as const)('%j -> %s', (over, expected) => {
    expect(isTaskRetryable(mkTask(over))).toBe(expected);
  });
});
