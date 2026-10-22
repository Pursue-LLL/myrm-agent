/**
 * Silent Failure Barrier Engine Unit Tests
 */

import { describe, expect, it } from 'vitest';
import { TaskExecutionRun } from '../cronIncidentTypes';
import {
  classifyExecutionRun,
  computeIncidentMetrics,
  verifyArtifactAcceptance,
} from '../silentFailureBarrierEngine';

describe('silentFailureBarrierEngine', () => {
  const baseRun: TaskExecutionRun = {
    runId: 'run-test-01',
    jobId: 'job-report-gen',
    jobName: '财务分析每日简报',
    exitCode: 0,
    durationMs: 1200,
    stdout: 'Execution finished normally',
    stderr: '',
    generatedArtifacts: [{ name: 'daily_summary.csv', bytes: 2048 }],
    executedAt: new Date().toISOString(),
  };

  it('should pass verification when run produces required artifacts and content keywords', () => {
    const result = verifyArtifactAcceptance(baseRun, {
      requiredArtifacts: ['daily_summary.csv'],
      minOutputBytes: 1000,
      contentKeywords: ['finished normally'],
    });

    expect(result.passed).toBe(true);
    expect(result.isSilentFailure).toBe(false);
    expect(result.missingArtifacts).toHaveLength(0);
  });

  it('should detect silent failure when exit code is 0 but missing required artifact', () => {
    const runWithoutArtifact: TaskExecutionRun = {
      ...baseRun,
      generatedArtifacts: [],
    };

    const result = verifyArtifactAcceptance(runWithoutArtifact, {
      requiredArtifacts: ['daily_summary.csv'],
    });

    expect(result.passed).toBe(false);
    expect(result.isSilentFailure).toBe(true);
    expect(result.missingArtifacts).toContain('daily_summary.csv');

    // Classification should yield a critical silent_failure incident
    const classification = classifyExecutionRun(runWithoutArtifact, {
      requiredArtifacts: ['daily_summary.csv'],
    });
    expect(classification.passed).toBe(false);
    expect(classification.incident).toBeDefined();
    expect(classification.incident?.category).toBe('silent_failure');
    expect(classification.incident?.exitCode).toBe(0);
    expect(classification.incident?.severity).toBe('critical');
  });

  it('should detect silent failure when output bytes is 0 and stdout is empty', () => {
    const emptyRun: TaskExecutionRun = {
      ...baseRun,
      stdout: '   ',
      generatedArtifacts: [{ name: 'empty.log', bytes: 0 }],
    };

    const result = verifyArtifactAcceptance(emptyRun, {
      minOutputBytes: 1,
    });
    expect(result.passed).toBe(false);
    expect(result.isSilentFailure).toBe(true);
  });

  it('should classify quota exhaustion when stderr contains 429', () => {
    const quotaRun: TaskExecutionRun = {
      ...baseRun,
      exitCode: 1,
      stderr: 'HTTP 429: Rate limit exceeded, quota exhausted',
    };

    const classification = classifyExecutionRun(quotaRun);
    expect(classification.passed).toBe(false);
    expect(classification.incident?.category).toBe('quota_exhausted');
    expect(classification.incident?.severity).toBe('warning');
  });

  it('should classify auth expiration when stderr contains 401', () => {
    const authRun: TaskExecutionRun = {
      ...baseRun,
      exitCode: 2,
      stderr: 'Error 401: Token expired or unauthorized credentials',
    };

    const classification = classifyExecutionRun(authRun);
    expect(classification.passed).toBe(false);
    expect(classification.incident?.category).toBe('auth_expired');
    expect(classification.incident?.severity).toBe('critical');
  });

  it('should calculate incident metrics accurately', () => {
    const classification = classifyExecutionRun({
      ...baseRun,
      generatedArtifacts: [],
    }, { requiredArtifacts: ['report.pdf'] });

    expect(classification.incident).toBeDefined();
    if (!classification.incident) {
      throw new Error('classification.incident must be defined');
    }
    const incident = classification.incident;
    const metrics = computeIncidentMetrics([
      incident,
      { ...incident, id: 'inc-2', acknowledged: true },
    ]);

    expect(metrics.totalCount).toBe(2);
    expect(metrics.unacknowledgedCount).toBe(1);
    expect(metrics.silentFailureCount).toBe(1);
    expect(metrics.hasBlockingIncidents).toBe(true);
  });
});
