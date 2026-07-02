import { describe, expect, it } from 'vitest';

import { mapTaskStepStatus } from '../streamHelpers';

describe('mapTaskStepStatus', () => {
  it('maps harness checklist and planner terminal statuses', () => {
    expect(mapTaskStepStatus('success')).toBe('success');
    expect(mapTaskStepStatus('completed')).toBe('success');
    expect(mapTaskStepStatus('error')).toBe('error');
    expect(mapTaskStepStatus('failed')).toBe('error');
    expect(mapTaskStepStatus('skipped')).toBe('cancelled');
    expect(mapTaskStepStatus('cancelled')).toBe('cancelled');
    expect(mapTaskStepStatus('partial_success')).toBe('warning');
  });

  it('returns undefined for in-flight harness statuses', () => {
    expect(mapTaskStepStatus('running')).toBeUndefined();
    expect(mapTaskStepStatus('pending')).toBeUndefined();
    expect(mapTaskStepStatus('in_progress')).toBeUndefined();
    expect(mapTaskStepStatus(undefined)).toBeUndefined();
  });
});
