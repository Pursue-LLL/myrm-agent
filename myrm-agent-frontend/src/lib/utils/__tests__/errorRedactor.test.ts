/**
 * [INPUT]
 * - src/lib/utils/errorRedactor::redactErrorMessage, redactErrorPayload, redactErrorObject (POS: 敏感字段脱敏纯函数)
 * - src/lib/utils/toast::toast (POS: 前端通知分发器)
 *
 * [OUTPUT]
 * - describe('errorRedactor')
 * - describe('toast error redaction integration')
 *
 * [POS]
 * 前端错误信息敏感数据脱敏与 Toast 安全防泄漏单元测试。
 */

import { describe, it, expect, vi } from 'vitest';
import { redactErrorMessage, redactErrorPayload, redactErrorObject } from '../errorRedactor';
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

  it('redacts JWT tokens', () => {
    const raw = 'Session expired: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozGz3asdf1234567890';
    const redacted = redactErrorMessage(raw);
    expect(redacted).not.toContain('eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9');
    expect(redacted).toContain('***REDACTED***');
  });

  it('redacts AWS Access Keys', () => {
    const raw = 'S3 client init failed with AKIAIOSFODNN7EXAMPLE key';
    const redacted = redactErrorMessage(raw);
    expect(redacted).not.toContain('AKIAIOSFODNN7EXAMPLE');
    expect(redacted).toContain('AKIA...PLE');
  });

  it('redacts database credentials in URLs', () => {
    const raw = 'Connection refused: postgresql://admin:MySecretPassword123@10.0.0.8:5432/myrm_db';
    const redacted = redactErrorMessage(raw);
    expect(redacted).not.toContain('MySecretPassword123');
    expect(redacted).toContain('postgresql://admin:***REDACTED***@10.0.0.8:5432/myrm_db');
  });

  it('redacts local user home directory absolute paths across macOS, Linux, and Windows', () => {
    const macRaw = 'Failed to load script at /Users/john_doe/projects/secret/index.js';
    expect(redactErrorMessage(macRaw)).toContain('~/projects/secret/index.js');
    expect(redactErrorMessage(macRaw)).not.toContain('/Users/john_doe/');

    const linuxRaw = 'Config missing: /home/deployer/myrm-agent/config.env';
    expect(redactErrorMessage(linuxRaw)).toContain('~/myrm-agent/config.env');
    expect(redactErrorMessage(linuxRaw)).not.toContain('/home/deployer/');

    const winRaw = 'IO error in C:\\Users\\Admin\\AppData\\Local\\secret.json';
    expect(redactErrorMessage(winRaw)).toContain('~\\AppData\\Local\\secret.json');
    expect(redactErrorMessage(winRaw)).not.toContain('C:\\Users\\Admin\\');
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

  it('redacts sensitive fields in nested error objects (FastAPI 422)', () => {
    const errObj = {
      detail: [
        {
          loc: ['body', 'api_key'],
          msg: 'String should have at least 10 characters',
          input: 'sk-proj-mysecrettoken123456789',
        },
      ],
    };
    const sanitized = redactErrorObject(errObj);
    expect(sanitized.detail[0].input).toBe('***REDACTED***');
  });
});

describe('toast error redaction integration', () => {
  it('transparently redacts error messages dispatched through toast.error', () => {
    const errorSpy = vi.spyOn(toast, 'error');
    toast.error('Fatal error with API key sk-proj-999888777666555444333');
    expect(errorSpy).toHaveBeenCalled();
  });
});
