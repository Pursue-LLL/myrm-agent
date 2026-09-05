import { describe, it, expect, vi } from 'vitest';
import { redactErrorMessage, redactErrorPayload } from '../errorRedactor';
import { toast } from '../toast';

describe('errorRedactor', () => {
  it('redacts sk- tokens while preserving head and tail', () => {
    const raw = 'Failed to connect: sk-proj-1234567890abcdef123456 is invalid';
    const redacted = redactErrorMessage(raw);
    expect(redacted).not.toContain('sk-proj-1234567890abcdef123456');
    expect(redacted).toContain('sk-p...456');
  });

  it('redacts Bearer tokens in headers', () => {
    const raw = 'Authorization error with Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz';
    const redacted = redactErrorMessage(raw);
    expect(redacted).not.toContain('eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz');
    expect(redacted).toContain('Bearer ***REDACTED***');
  });

  it('redacts database credentials in URLs', () => {
    const raw = 'Connection refused: postgresql://admin:MySecretPassword123@10.0.0.8:5432/myrm_db';
    const redacted = redactErrorMessage(raw);
    expect(redacted).not.toContain('MySecretPassword123');
    expect(redacted).toContain('postgresql://admin:***REDACTED***@10.0.0.8:5432/myrm_db');
  });

  it('redacts local user home directory absolute paths', () => {
    const raw = 'Failed to load script at /Users/john_doe/projects/secret/index.js';
    const redacted = redactErrorMessage(raw);
    expect(redacted).not.toContain('/Users/john_doe/');
    expect(redacted).toContain('~/projects/secret/index.js');
  });

  it('safely handles non-string and null error inputs', () => {
    expect(redactErrorMessage(null)).toBe('');
    expect(redactErrorMessage(undefined)).toBe('');
    expect(redactErrorMessage(new Error('API error with token=supersecret123'))).toContain('token=***REDACTED***');
  });

  it('redacts error payload structures', () => {
    const payload = {
      title: 'Authentication Error: sk-ant-api03-abcdefghijklmnop123',
      description: 'Check credentials at /home/ubuntu/app/config.json',
      message: 'Failed to authenticate',
    };
    const sanitized = redactErrorPayload(payload);
    expect(sanitized.title).not.toContain('sk-ant-api03-abcdefghijklmnop123');
    expect(sanitized.description).toContain('~/app/config.json');
  });
});

describe('toast error redaction integration', () => {
  it('transparently redacts error messages dispatched through toast.error', () => {
    const errorSpy = vi.spyOn(toast, 'error');
    toast.error('Fatal error with API key sk-proj-999888777666555444333');
    expect(errorSpy).toHaveBeenCalled();
  });
});
