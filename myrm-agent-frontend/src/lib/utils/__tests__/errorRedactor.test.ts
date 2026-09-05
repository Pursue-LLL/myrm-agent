import { describe, expect, it } from 'vitest';
import {
  formatUiError,
  maskToken,
  redactErrorMessage,
  redactErrorObject,
  redactSensitiveText,
} from '../errorRedactor';

describe('errorRedactor', () => {
  describe('maskToken', () => {
    it('should completely mask short tokens (<= 10 chars) to prevent slice overlap', () => {
      expect(maskToken('short')).toBe('[redacted]');
      expect(maskToken('1234567890')).toBe('[redacted]');
    });

    it('should apply 6/4 mask to long tokens (> 10 chars)', () => {
      expect(maskToken('sk-1234567890abcdef')).toBe('sk-123...cdef');
      expect(maskToken('ghp_abcdef1234567890XYZ')).toBe('ghp_ab...0XYZ');
    });
  });

  describe('redactSensitiveText', () => {
    it('should redact well-known API keys (OpenAI / GitHub / Slack)', () => {
      const text = 'Failed with OpenAI key sk-proj-1234567890abcdef and GitHub token ghp_11223344556677889900';
      const result = redactSensitiveText(text);
      expect(result).not.toContain('sk-proj-1234567890abcdef');
      expect(result).not.toContain('ghp_11223344556677889900');
      expect(result).toContain('sk-pro...cdef');
      expect(result).toContain('ghp_11...9900');
    });

    it('should redact Bearer tokens', () => {
      const text = 'HTTP error 401: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.header.signature';
      const result = redactSensitiveText(text);
      expect(result).not.toContain('eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.header.signature');
      expect(result).toContain('Bearer eyJhbG...ture');
    });

    it('should redact Authorization headers', () => {
      const text = 'Request headers: Authorization: Basic dXNlcjpwYXNzd29yZA==';
      const result = redactSensitiveText(text);
      expect(result).toBe('Request headers: Authorization: [redacted]');
    });

    it('should redact database URI passwords', () => {
      const text = 'Failed to connect: postgresql://admin:MySecretPassword123@192.168.1.10:5432/my_db';
      const result = redactSensitiveText(text);
      expect(result).not.toContain('MySecretPassword123');
      expect(result).toBe('Failed to connect: postgresql://admin:***@192.168.1.10:5432/my_db');
    });

    it('should redact PEM private keys', () => {
      const text =
        'Error loading key:\n-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0Y...\n-----END RSA PRIVATE KEY-----\ncorrupted';
      const result = redactSensitiveText(text);
      expect(result).not.toContain('MIIEowIBAAKCAQEA0Y');
      expect(result).toContain('[redacted private key]');
    });

    it('should redact sensitive URL query parameters', () => {
      const text = 'GET https://api.example.com/v1?token=sk-9876543210fedcba&foo=bar&api_key=secretKey123456';
      const result = redactSensitiveText(text);
      expect(result).not.toContain('sk-9876543210fedcba');
      expect(result).not.toContain('secretKey123456');
      expect(result).toContain('token=sk-987...dcba');
      expect(result).toContain('api_key=secret...3456');
      expect(result).toContain('foo=bar');
    });

    it('should redact OS-level absolute user home paths to ~/ without breaking relative or API paths', () => {
      const text = 'Disk error: /Users/yululiu/projects/AI/data.db: file locked';
      const result = redactSensitiveText(text);
      expect(result).not.toContain('/Users/yululiu');
      expect(result).toBe('Disk error: ~/projects/AI/data.db: file locked');

      const linuxText = 'File not found: /home/ubuntu/app/config.json';
      expect(redactSensitiveText(linuxText)).toBe('File not found: ~/app/config.json');

      const winText = 'IO error: C:\\Users\\Administrator\\data.db';
      expect(redactSensitiveText(winText)).toBe('IO error: ~/data.db');
    });

    it('should NOT over-redact API paths, MIME types, or model names', () => {
      const apiPath = 'Endpoint /api/v1/chats/404 returned 404';
      expect(redactSensitiveText(apiPath)).toBe(apiPath);

      const mimeType = 'Unsupported Content-Type: application/json; charset=utf-8';
      expect(redactSensitiveText(mimeType)).toBe(mimeType);

      const modelName = 'Model deepseek-ai/DeepSeek-V3 not found';
      expect(redactSensitiveText(modelName)).toBe(modelName);
    });
  });

  describe('redactErrorMessage', () => {
    it('should redact string error messages', () => {
      const raw = 'Invalid key sk-1234567890abcdef';
      expect(redactErrorMessage(raw)).toBe('Invalid key sk-123...cdef');
    });

    it('should redact Error instance messages', () => {
      const err = new TypeError('Failed to load /Users/alice/config.json with sk-1234567890abcdef');
      const sanitized = redactErrorMessage(err);
      expect(sanitized).not.toContain('/Users/alice');
      expect(sanitized).not.toContain('sk-1234567890abcdef');
      expect(sanitized).toContain('~/config.json');
      expect(sanitized).toContain('sk-123...cdef');
    });

    it('should safely passthrough null and undefined as empty string', () => {
      expect(redactErrorMessage(null)).toBe('');
      expect(redactErrorMessage(undefined)).toBe('');
    });
  });

  describe('redactErrorObject', () => {
    it('should redact sensitive keys in nested error objects', () => {
      const errObj = {
        status: 422,
        detail: [
          {
            loc: ['body', 'api_key'],
            msg: 'Invalid key',
            input: 'sk-1234567890abcdef',
          },
        ],
      };
      const cleaned = redactErrorObject(errObj);
      expect(cleaned.detail[0].input).toBe('sk-123...cdef');
    });
  });

  describe('formatUiError', () => {
    it('should format and redact Error objects with fallback', () => {
      expect(formatUiError(null, 'Custom fallback')).toBe('Custom fallback');
      expect(formatUiError(new Error('Key sk-1234567890abcdef expired'))).toBe('Key sk-123...cdef expired');
      expect(formatUiError('Direct error /Users/test/path')).toBe('Direct error [path]');
      expect(formatUiError({ message: 'Object error with sk-1234567890abcdef' })).toBe(
        'Object error with sk-123...cdef',
      );
    });
  });
});
