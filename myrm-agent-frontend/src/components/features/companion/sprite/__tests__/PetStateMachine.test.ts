import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AnimRow, PetStateMachine, stepKeyToPetEvent } from '../PetStateMachine';

describe('PetStateMachine', () => {
  let sm: PetStateMachine;
  let currentRow: AnimRow;

  beforeEach(() => {
    vi.useFakeTimers();
    sm = new PetStateMachine({
      onChange: (row) => { currentRow = row; },
      heartbeatTimeoutMs: 5000,
      tickIntervalMs: 100,
    });
    currentRow = AnimRow.IDLE;
  });

  afterEach(() => {
    sm.destroy();
    vi.useRealTimers();
  });

  it('starts in IDLE state', () => {
    expect(sm.getCurrentRow()).toBe(AnimRow.IDLE);
  });

  it('transitions to sticky state', () => {
    sm.ingest({ row: AnimRow.THINKING, mode: 'sticky' });
    expect(currentRow).toBe(AnimRow.THINKING);
    expect(sm.getCurrentRow()).toBe(AnimRow.THINKING);
  });

  it('sticky state persists across ticks', () => {
    sm.ingest({ row: AnimRow.RUNNING, mode: 'sticky' });
    sm.heartbeat();
    vi.advanceTimersByTime(500);
    expect(currentRow).toBe(AnimRow.RUNNING);
  });

  it('transient state reverts to idle after TTL', () => {
    sm.ingest({ row: AnimRow.CELEBRATING, mode: 'transient', ttlMs: 200 });
    expect(currentRow).toBe(AnimRow.CELEBRATING);

    vi.advanceTimersByTime(300);
    expect(currentRow).toBe(AnimRow.IDLE);
  });

  it('transient state reverts to sticky if one is set', () => {
    sm.ingest({ row: AnimRow.RUNNING, mode: 'sticky' });
    sm.heartbeat();
    sm.ingest({ row: AnimRow.CELEBRATING, mode: 'transient', ttlMs: 200 });
    expect(currentRow).toBe(AnimRow.CELEBRATING);

    vi.advanceTimersByTime(300);
    expect(currentRow).toBe(AnimRow.RUNNING);
  });

  it('release clears sticky state', () => {
    sm.ingest({ row: AnimRow.THINKING, mode: 'sticky' });
    sm.heartbeat();
    sm.ingest({ row: AnimRow.IDLE, mode: 'release' });
    vi.advanceTimersByTime(200);
    expect(currentRow).toBe(AnimRow.IDLE);
  });

  it('heartbeat timeout forces idle', () => {
    sm.ingest({ row: AnimRow.RUNNING, mode: 'sticky' });
    sm.heartbeat();
    expect(currentRow).toBe(AnimRow.RUNNING);

    vi.advanceTimersByTime(6000);
    expect(currentRow).toBe(AnimRow.IDLE);
  });

  it('heartbeat resets timeout', () => {
    sm.ingest({ row: AnimRow.RUNNING, mode: 'sticky' });
    sm.heartbeat();

    vi.advanceTimersByTime(3000);
    sm.heartbeat();
    vi.advanceTimersByTime(3000);
    expect(currentRow).toBe(AnimRow.RUNNING);
  });

  it('setLoading triggers THINKING sticky', () => {
    sm.setLoading(true);
    expect(currentRow).toBe(AnimRow.THINKING);
  });

  it('setLoading(false) triggers CELEBRATING transient then idle', () => {
    sm.setLoading(true);
    sm.setLoading(false);
    expect(currentRow).toBe(AnimRow.CELEBRATING);

    vi.advanceTimersByTime(2000);
    expect(currentRow).toBe(AnimRow.IDLE);
  });

  it('reset forces idle and clears sticky', () => {
    sm.ingest({ row: AnimRow.RUNNING, mode: 'sticky' });
    sm.reset();
    expect(currentRow).toBe(AnimRow.IDLE);
    vi.advanceTimersByTime(200);
    expect(currentRow).toBe(AnimRow.IDLE);
  });

  it('ignores events after destroy', () => {
    sm.destroy();
    sm.ingest({ row: AnimRow.RUNNING, mode: 'sticky' });
    expect(currentRow).toBe(AnimRow.IDLE);
  });

  it('approval waiting overrides celebrating from setLoading(false)', () => {
    sm.setLoading(true);
    expect(currentRow).toBe(AnimRow.THINKING);

    sm.setLoading(false);
    expect(currentRow).toBe(AnimRow.CELEBRATING);

    sm.ingest({ row: AnimRow.WAVING, mode: 'sticky' });
    expect(currentRow).toBe(AnimRow.WAVING);

    sm.heartbeat();
    vi.advanceTimersByTime(2000);
    expect(currentRow).toBe(AnimRow.WAVING);
  });

  it('approval release returns to idle after waiting', () => {
    sm.ingest({ row: AnimRow.WAVING, mode: 'sticky' });
    sm.heartbeat();
    expect(currentRow).toBe(AnimRow.WAVING);

    sm.ingest({ row: AnimRow.IDLE, mode: 'release' });
    vi.advanceTimersByTime(200);
    expect(currentRow).toBe(AnimRow.IDLE);
  });
});

describe('stepKeyToPetEvent', () => {
  it('maps workflow_planning to THINKING sticky', () => {
    const event = stepKeyToPetEvent('workflow_planning');
    expect(event).toEqual({ row: AnimRow.THINKING, mode: 'sticky' });
  });

  it('maps workflow_execution to RUNNING sticky', () => {
    const event = stepKeyToPetEvent('workflow_execution');
    expect(event).toEqual({ row: AnimRow.RUNNING, mode: 'sticky' });
  });

  it('maps model_failover to FAILED transient', () => {
    const event = stepKeyToPetEvent('model_failover');
    expect(event).toEqual({ row: AnimRow.FAILED, mode: 'transient', ttlMs: 2500 });
  });

  it('maps context_compaction to REVIEWING transient', () => {
    const event = stepKeyToPetEvent('context_compaction');
    expect(event).toEqual({ row: AnimRow.REVIEWING, mode: 'transient', ttlMs: 2000 });
  });

  it('maps consensus_reference_done to CELEBRATING transient', () => {
    const event = stepKeyToPetEvent('consensus_reference_done');
    expect(event).toEqual({ row: AnimRow.CELEBRATING, mode: 'transient', ttlMs: 1500 });
  });

  it('maps loop_guard_break to FAILED transient', () => {
    const event = stepKeyToPetEvent('loop_guard_break');
    expect(event).toEqual({ row: AnimRow.FAILED, mode: 'transient', ttlMs: 3000 });
  });

  it('maps approval_waiting to WAVING sticky', () => {
    const event = stepKeyToPetEvent('approval_waiting');
    expect(event).toEqual({ row: AnimRow.WAVING, mode: 'sticky' });
  });

  it('maps approval_released to IDLE release', () => {
    const event = stepKeyToPetEvent('approval_released');
    expect(event).toEqual({ row: AnimRow.IDLE, mode: 'release' });
  });

  it('returns null for unknown step_key', () => {
    expect(stepKeyToPetEvent('unknown_event')).toBeNull();
    expect(stepKeyToPetEvent('')).toBeNull();
  });

  it('maps all 23 known step_keys', () => {
    const knownKeys = [
      'workflow_init', 'workflow_planning', 'workflow_execution', 'workflow_stage',
      'context_compaction', 'context_truncation', 'context_pruned', 'memory_archived',
      'model_failover', 'safety_fallback_active', 'transient_retry',
      'thinking_budget_exhausted', 'text_continuation_exhausted',
      'analyzing_image', 'analyzing_video',
      'consensus_active', 'consensus_reference_done',
      'loop_guard_warn', 'loop_guard_break',
      'approval_waiting', 'approval_released',
    ];
    for (const key of knownKeys) {
      const event = stepKeyToPetEvent(key);
      expect(event, `${key} should map to a PetEvent`).not.toBeNull();
      expect(event!.row).toBeGreaterThanOrEqual(0);
      expect(event!.row).toBeLessThanOrEqual(8);
      expect(['transient', 'sticky', 'release']).toContain(event!.mode);
    }
  });
});
