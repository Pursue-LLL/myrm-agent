import { describe, expect, it } from 'vitest';
import {
  MODEL_ESCALATED_REASON_KEY,
  MODEL_ESCALATED_TOAST_KEY,
  MODEL_RECOVERY_DOWNTIME_KEY,
  MODEL_RECOVERY_TOAST_KEY,
  resolveModelFailoverProgressStepKey,
  resolveModelFailoverToastKey,
} from '../modelNotifyToastKey';

describe('modelNotifyToastKey', () => {
  it('maps model_not_found to progressSteps SSOT keys', () => {
    expect(resolveModelFailoverToastKey('model_not_found')).toBe(
      'progressSteps.model_failover_model_not_found',
    );
    expect(resolveModelFailoverProgressStepKey('model_not_found')).toBe(
      'model_failover_model_not_found',
    );
  });

  it('maps format to response_format_error progress key', () => {
    expect(resolveModelFailoverToastKey('format')).toBe(
      'progressSteps.model_failover_response_format_error',
    );
    expect(resolveModelFailoverProgressStepKey('format')).toBe(
      'model_failover_response_format_error',
    );
  });

  it('falls back to generic model_failover', () => {
    expect(resolveModelFailoverToastKey(undefined)).toBe('progressSteps.model_failover');
    expect(resolveModelFailoverToastKey('unknown_reason')).toBe('progressSteps.model_failover');
  });

  it('exports escalation and recovery toast SSOT keys', () => {
    expect(MODEL_ESCALATED_TOAST_KEY).toBe('progressSteps.model_escalated');
    expect(MODEL_ESCALATED_REASON_KEY).toBe('progressSteps.model_escalated_reason');
    expect(MODEL_RECOVERY_TOAST_KEY).toBe('progressSteps.model_recovery');
    expect(MODEL_RECOVERY_DOWNTIME_KEY).toBe('progressSteps.model_recovery_downtime');
  });
});
