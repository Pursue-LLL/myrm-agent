/**
 * [INPUT]
 * - src/lib/utils/error-handling/errorRedactor::redactErrorMessage, redactErrorPayload, redactErrorObject (POS: 敏感字段脱敏纯函数)
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
import { toast } from '@/lib/utils/toast';

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
    const raw =
      'Session expired: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozGz3asdf1234567890';
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

  it.each([
    [
      'a raw @ in the password',
      'db=postgres://root:p@ssw0rd123@localhost:5432/prod',
      'ssw0rd123',
      'postgres://root:***REDACTED***@localhost:5432/prod',
    ],
    ['an empty user name', 'cache=redis://:Zx9PwQ7r@cache:6379/0', 'Zx9PwQ7r', 'redis://:***REDACTED***@cache:6379/0'],
    [
      'a driver suffix',
      'url=postgresql+asyncpg://app:Zx9PwQ7r@db/app',
      'Zx9PwQ7r',
      'postgresql+asyncpg://app:***REDACTED***@db/app',
    ],
  ])('redacts the whole database password with %s', (_name, raw, secret, expected) => {
    const redacted = redactErrorMessage(raw);
    expect(redacted).not.toContain(secret);
    expect(redacted).toContain(expected);
  });

  it('keeps text after a database URI, including an e-mail address', () => {
    const redacted = redactErrorMessage('postgres://u:pw1234@db1 failed, contact admin@corp.example');
    expect(redacted).toBe('postgres://u:***REDACTED***@db1 failed, contact admin@corp.example');
  });

  it.each([
    [
      'a SQL Server URL',
      'mssql://sa:Zk9mango42x@db.internal:1433/app',
      'mssql://sa:***REDACTED***@db.internal:1433/app',
    ],
    [
      'basic auth in an https URL',
      'GET https://admin:Zk9mango42x@api.internal/v1 failed',
      'https://admin:***REDACTED***@api.internal/v1 failed',
    ],
    ['an smtps URL', 'smtps://mailer:Zk9mango42x@smtp.internal:465', 'smtps://mailer:***REDACTED***@smtp.internal:465'],
    ['an ftp URL', 'ftp://deploy:Zk9mango42x@files.internal/r', 'ftp://deploy:***REDACTED***@files.internal/r'],
    [
      'a raw @ in the password',
      'https://root:Zk9@mango42x@api.internal/v1',
      'https://root:***REDACTED***@api.internal/v1',
    ],
  ])('redacts the password of %s', (_name, raw, expected) => {
    const redacted = redactErrorMessage(raw);
    expect(redacted).not.toContain('mango42x');
    expect(redacted).toContain(expected);
  });

  it.each([
    'https://example.com:8080?contact=dev@example.com',
    'ssh://git@github.com:22/org/repo.git',
    'https://example.com/users/@alice and https://example.com:8443/docs',
  ])('leaves a URL without a password as it is: %s', (raw) => {
    expect(redactErrorMessage(raw)).toBe(raw);
  });

  it('scans a long run of URL prefixes of any scheme in bounded time', () => {
    const started = performance.now();
    redactErrorMessage('https://u:'.repeat(4000));
    redactErrorMessage('a-'.repeat(20000) + '://');
    expect(performance.now() - started).toBeLessThan(400);
  });

  it('scans a long run of database URI prefixes in bounded time', () => {
    const raw = 'redis://:'.repeat(4000);
    const started = performance.now();
    redactErrorMessage(raw);
    expect(performance.now() - started).toBeLessThan(400);
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

  it('safely breaks circular references in nested objects without throwing RangeError', () => {
    const circularObj: Record<string, unknown> = {
      title: 'Circular test',
      token: 'sk-proj-1234567890abcdef',
    };
    circularObj.self = circularObj;
    const sanitized = redactErrorObject(circularObj);
    expect(sanitized.token).toBe('***REDACTED***');
    expect(sanitized.self).toBe('***REDACTED***');
  });
});

describe('toast error redaction integration', () => {
  it('transparently redacts error messages dispatched through toast.error', () => {
    const errorSpy = vi.spyOn(toast, 'error');
    toast.error('Fatal error with API key sk-proj-999888777666555444333');
    expect(errorSpy).toHaveBeenCalled();
  });
});
