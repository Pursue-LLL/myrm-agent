import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { PetState, PetStateMachine, stepKeyToPetEvent } from '../PetStateMachine';

describe('PetStateMachine', () => {
  let sm: PetStateMachine;
  let currentState: PetState;

  beforeEach(() => {
    vi.useFakeTimers();
    sm = new PetStateMachine({
      onChange: (state) => { currentState = state; },
      heartbeatTimeoutMs: 5000,
      tickIntervalMs: 100,
    });
    currentState = PetState.IDLE;
  });

  afterEach(() => {
    sm.destroy();
    vi.useRealTimers();
  });

  it('starts in IDLE state', () => {
    expect(sm.getCurrentState()).toBe(PetState.IDLE);
  });

  it('transitions to sticky state', () => {
    sm.ingest({ state: PetState.REVIEWING, mode: 'sticky' });
    expect(currentState).toBe(PetState.REVIEWING);
    expect(sm.getCurrentState()).toBe(PetState.REVIEWING);
  });

  it('sticky state persists across ticks', () => {
    sm.ingest({ state: PetState.RUNNING, mode: 'sticky' });
    sm.heartbeat();
    vi.advanceTimersByTime(500);
    expect(currentState).toBe(PetState.RUNNING);
  });

  it('transient state reverts to idle after TTL', () => {
    sm.ingest({ state: PetState.WAVE, mode: 'transient', ttlMs: 200 });
    expect(currentState).toBe(PetState.WAVE);

    vi.advanceTimersByTime(300);
    expect(currentState).toBe(PetState.IDLE);
  });

  it('transient state reverts to sticky if one is set', () => {
    sm.ingest({ state: PetState.RUNNING, mode: 'sticky' });
    sm.heartbeat();
    sm.ingest({ state: PetState.WAVE, mode: 'transient', ttlMs: 200 });
    expect(currentState).toBe(PetState.WAVE);

    vi.advanceTimersByTime(300);
    expect(currentState).toBe(PetState.RUNNING);
  });

  it('release clears sticky state', () => {
    sm.ingest({ state: PetState.REVIEWING, mode: 'sticky' });
    sm.heartbeat();
    sm.ingest({ state: PetState.IDLE, mode: 'release' });
    vi.advanceTimersByTime(200);
    expect(currentState).toBe(PetState.IDLE);
  });

  it('heartbeat timeout forces idle', () => {
    sm.ingest({ state: PetState.RUNNING, mode: 'sticky' });
    sm.heartbeat();
    expect(currentState).toBe(PetState.RUNNING);

    vi.advanceTimersByTime(6000);
    expect(currentState).toBe(PetState.IDLE);
  });

  it('setLoading triggers REVIEWING sticky', () => {
    sm.setLoading(true);
    expect(currentState).toBe(PetState.REVIEWING);
  });

  it('setLoading(false) triggers WAVE transient then idle', () => {
    sm.setLoading(true);
    sm.setLoading(false);
    expect(currentState).toBe(PetState.WAVE);

    vi.advanceTimersByTime(2000);
    expect(currentState).toBe(PetState.IDLE);
  });

  it('setBlockedOnUser shows WAITING and suppresses wave on load end', () => {
    sm.setLoading(true);
    sm.setBlockedOnUser(true);
    expect(currentState).toBe(PetState.WAITING);

    sm.setLoading(false);
    expect(currentState).toBe(PetState.WAITING);

    vi.advanceTimersByTime(2000);
    expect(currentState).toBe(PetState.WAITING);
  });

  it('clearing blockedOnUser returns to idle when no sticky', () => {
    sm.setBlockedOnUser(true);
    expect(currentState).toBe(PetState.WAITING);

    sm.setBlockedOnUser(false);
    vi.advanceTimersByTime(200);
    expect(currentState).toBe(PetState.IDLE);
  });

  it('blockedOnUser overrides running sticky', () => {
    sm.ingest({ state: PetState.RUNNING, mode: 'sticky' });
    sm.heartbeat();
    sm.setBlockedOnUser(true);
    expect(currentState).toBe(PetState.WAITING);
  });

  it('reset forces idle and clears sticky', () => {
    sm.ingest({ state: PetState.RUNNING, mode: 'sticky' });
    sm.reset();
    expect(currentState).toBe(PetState.IDLE);
  });

  it('ignores events after destroy', () => {
    sm.destroy();
    sm.ingest({ state: PetState.RUNNING, mode: 'sticky' });
    expect(currentState).toBe(PetState.IDLE);
  });
});

describe('stepKeyToPetEvent', () => {
  it('maps workflow_planning to REVIEWING sticky', () => {
    const event = stepKeyToPetEvent('workflow_planning');
    expect(event).toEqual({ state: PetState.REVIEWING, mode: 'sticky' });
  });

  it('maps workflow_execution to RUNNING sticky', () => {
    const event = stepKeyToPetEvent('workflow_execution');
    expect(event).toEqual({ state: PetState.RUNNING, mode: 'sticky' });
  });

  it('maps model_failover to FAILED transient', () => {
    const event = stepKeyToPetEvent('model_failover');
    expect(event).toEqual({ state: PetState.FAILED, mode: 'transient', ttlMs: 2500 });
  });

  it('maps consensus_reference_done to JUMP transient', () => {
    const event = stepKeyToPetEvent('consensus_reference_done');
    expect(event).toEqual({ state: PetState.JUMP, mode: 'transient', ttlMs: 1500 });
  });

  it('maps correction_learned to REVIEWING transient', () => {
    const event = stepKeyToPetEvent('correction_learned');
    expect(event).toEqual({ state: PetState.REVIEWING, mode: 'transient', ttlMs: 2000 });
  });

  it('does not map approval_waiting (store-driven waiting)', () => {
    expect(stepKeyToPetEvent('approval_waiting')).toBeNull();
    expect(stepKeyToPetEvent('approval_released')).toBeNull();
  });

  it('returns null for unknown step_key', () => {
    expect(stepKeyToPetEvent('unknown_event')).toBeNull();
    expect(stepKeyToPetEvent('')).toBeNull();
  });
});
