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

  it('maps auth_permanent / session_expired to model_failover_auth', () => {
    expect(resolveModelFailoverToastKey('auth_permanent')).toBe(
      'progressSteps.model_failover_auth',
    );
    expect(resolveModelFailoverToastKey('session_expired')).toBe(
      'progressSteps.model_failover_auth',
    );
    expect(resolveModelFailoverProgressStepKey('auth_permanent')).toBe(
      'model_failover_auth',
    );
  });

  it('maps safety_block to safety_fallback_active for both toast and step key', () => {
    expect(resolveModelFailoverToastKey('safety_block')).toBe(
      'progressSteps.safety_fallback_active',
    );
    expect(resolveModelFailoverProgressStepKey('safety_block')).toBe(
      'safety_fallback_active',
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
