/**
 * Cron Incident Store Unit Tests
 */

import { beforeEach, describe, expect, it } from 'vitest';
import { TaskExecutionRun } from '../cronIncidentTypes';
import { useCronIncidentStore } from '../useCronIncidentStore';

describe('useCronIncidentStore', () => {
  beforeEach(() => {
    useCronIncidentStore.getState().resetToDefault();
  });

  it('should compute initial metrics including silent failures', () => {
    const store = useCronIncidentStore.getState();
    const metrics = store.getMetrics();

    expect(metrics.totalCount).toBeGreaterThanOrEqual(3);
    expect(metrics.unacknowledgedCount).toBeGreaterThanOrEqual(2);
    expect(metrics.silentFailureCount).toBeGreaterThanOrEqual(1);
    expect(metrics.hasBlockingIncidents).toBe(true);
  });

  it('should acknowledge an incident individually', () => {
    const store = useCronIncidentStore.getState();
    const unacknowledged = store.incidents.find((i) => !i.acknowledged);
    expect(unacknowledged).toBeDefined();
    if (!unacknowledged) {
      throw new Error('unacknowledged incident must be defined');
    }
    const targetId = unacknowledged.id;
    store.acknowledgeIncident(targetId);

    const updated = useCronIncidentStore.getState().incidents.find((i) => i.id === targetId);
    expect(updated?.acknowledged).toBe(true);
    expect(updated?.acknowledgedAt).toBeTruthy();
  });

  it('should acknowledge all incidents in batch', () => {
    const store = useCronIncidentStore.getState();
    store.acknowledgeAll();

    const metrics = useCronIncidentStore.getState().getMetrics();
    expect(metrics.unacknowledgedCount).toBe(0);
    expect(metrics.hasBlockingIncidents).toBe(false);
  });

  it('should increment retryCount when retrying an incident', () => {
    const store = useCronIncidentStore.getState();
    const target = store.incidents[0];
    const initialRetries = target.retryCount;

    store.retryIncidentRun(target.id);

    const updated = useCronIncidentStore.getState().incidents.find((i) => i.id === target.id);
    expect(updated?.retryCount).toBe(initialRetries + 1);
  });

  it('should record execution run and intercept silent failure', () => {
    const store = useCronIncidentStore.getState();
    const fakeRun: TaskExecutionRun = {
      runId: 'run-intercept-01',
      jobId: 'job-daily-backup',
      jobName: '每日数据库备份',
      exitCode: 0,
      durationMs: 800,
      stdout: '',
      stderr: '',
      generatedArtifacts: [],
      executedAt: new Date().toISOString(),
    };

    const result = store.recordExecutionRun(fakeRun, {
      requiredArtifacts: ['db_backup.tar.gz'],
    });

    expect(result.passed).toBe(false);
    expect(result.incident?.category).toBe('silent_failure');

    // Store should prepend the new incident
    const firstIncident = useCronIncidentStore.getState().incidents[0];
    expect(firstIncident.id).toBe(result.incident?.id);
    expect(firstIncident.jobName).toBe('每日数据库备份');
  });

  it('should filter incidents by category and search keyword', () => {
    const store = useCronIncidentStore.getState();
    store.setOnlyUnacknowledged(false);
    store.setFilterCategory('quota_exhausted');

    const filtered = store.getFilteredIncidents();
    for (const item of filtered) {
      expect(item.category).toBe('quota_exhausted');
    }

    store.setFilterCategory('all');
    store.setSearchQuery('财务');
    const searchResult = store.getFilteredIncidents();
    expect(searchResult.length).toBeGreaterThan(0);
    expect(searchResult[0].jobName).toContain('财务');
  });
});
