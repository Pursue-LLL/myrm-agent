import { describe, expect, it } from 'vitest';
import {
  buildBatchTaskStats,
  matchesBatchStatusFilter,
  normalizeBatchStatus,
  parseSkillIds,
} from '../batch-optimization';

describe('batch-optimization utils', () => {
  it('parses mixed separators and deduplicates skill ids', () => {
    const result = parseSkillIds('skill-a, skill-b\nskill-c；skill-a；skill-d;skill-e，skill-f');

    expect(result).toEqual(['skill-a', 'skill-b', 'skill-c', 'skill-d', 'skill-e', 'skill-f']);
  });

  it('normalizes batch status aliases', () => {
    expect(normalizeBatchStatus('success')).toBe('completed');
    expect(normalizeBatchStatus('failed')).toBe('failure');
    expect(normalizeBatchStatus('RUNNING')).toBe('running');
    expect(normalizeBatchStatus('unknown-status')).toBe('pending');
  });

  it('matches batch status filters', () => {
    expect(matchesBatchStatusFilter('pending', 'active')).toBe(true);
    expect(matchesBatchStatusFilter('running', 'active')).toBe(true);
    expect(matchesBatchStatusFilter('completed', 'active')).toBe(false);
    expect(matchesBatchStatusFilter('success', 'completed')).toBe(true);
  });

  it('builds summary stats from batch tasks', () => {
    const stats = buildBatchTaskStats([
      {
        batch_id: 'batch-1',
        skill_ids: { ids: ['skill-a', 'skill-b'] },
        status: 'running',
        priority: 2,
        max_concurrent: 3,
        total_tasks: 10,
        completed_tasks: 4,
        failed_tasks: 1,
        cancelled_tasks: 0,
        total_execution_time: 12,
        total_token_consumption: 1200,
        estimated_completion_time: null,
        created_at: '2026-04-13T00:00:00Z',
        started_at: '2026-04-13T00:01:00Z',
        completed_at: null,
      },
      {
        batch_id: 'batch-2',
        skill_ids: { ids: ['skill-c'] },
        status: 'success',
        priority: 1,
        max_concurrent: 2,
        total_tasks: 5,
        completed_tasks: 5,
        failed_tasks: 0,
        cancelled_tasks: 0,
        total_execution_time: 3,
        total_token_consumption: 300,
        estimated_completion_time: null,
        created_at: '2026-04-13T01:00:00Z',
        started_at: '2026-04-13T01:01:00Z',
        completed_at: '2026-04-13T01:04:00Z',
      },
    ]);

    expect(stats.totalBatches).toBe(2);
    expect(stats.activeBatches).toBe(1);
    expect(stats.runningBatches).toBe(1);
    expect(stats.completedBatches).toBe(1);
    expect(stats.totalSkills).toBe(3);
    expect(stats.totalTasks).toBe(15);
    expect(stats.completedTasks).toBe(9);
    expect(stats.failedTasks).toBe(1);
    expect(stats.totalTokens).toBe(1500);
    expect(stats.totalExecutionSeconds).toBe(15);
    expect(stats.overallProgress).toBe(60);
    expect(stats.averageExecutionSeconds).toBe(7.5);
  });
});
