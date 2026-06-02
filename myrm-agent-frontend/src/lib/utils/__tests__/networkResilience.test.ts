import { describe, expect, it } from 'vitest';
import {
  ARCHIVE_RESTORE_ACTION_INVALID,
  FatalNetworkError,
  isArchiveRestoreActionInvalidError,
  isRetryableHttpStatus,
  isRetryableWebSocketClose,
} from '../networkResilience';

describe('networkResilience', () => {
  it('classifies retryable HTTP status codes correctly', () => {
    for (const status of [408, 429, 502, 503, 504]) {
      expect(isRetryableHttpStatus(status)).toBe(true);
    }

    for (const status of [400, 401, 403, 404, 500, 501, 505]) {
      expect(isRetryableHttpStatus(status)).toBe(false);
    }
  });

  it('classifies retryable websocket close codes correctly', () => {
    for (const code of [1001, 1006, 1012, 1013, 1014]) {
      expect(isRetryableWebSocketClose(code)).toBe(true);
    }

    for (const code of [1000, 1003, 1007, 1008, 1009, 1010, 1011]) {
      expect(isRetryableWebSocketClose(code)).toBe(false);
    }
  });

  it('preserves fatal network error metadata', () => {
    const error = new FatalNetworkError('Attach failed', 403);

    expect(error).toBeInstanceOf(Error);
    expect(error.name).toBe('FatalNetworkError');
    expect(error.message).toBe('Attach failed');
    expect(error.status).toBe(403);
  });

  it('identifies structured archive restore validation failures', () => {
    const error = new FatalNetworkError('Invalid archive range', {
      status: 422,
      errorCode: ARCHIVE_RESTORE_ACTION_INVALID,
      detail: 'Archive restore range is outside the archive.',
      responseBody: '{"error_code":"archive_restore_action_invalid"}',
    });

    expect(isArchiveRestoreActionInvalidError(error)).toBe(true);
    expect(error.status).toBe(422);
    expect(error.detail).toBe('Archive restore range is outside the archive.');
    expect(error.responseBody).toContain('archive_restore_action_invalid');
  });
});
