import { describe, it, expect } from 'vitest';
import { redactSensitiveClientText, containsSensitiveData } from '../clientRedact';

describe('clientRedact', () => {
  it('redacts OpenAI/Anthropic style API keys', () => {
    const raw = 'Config: API_KEY="sk-abcdefghijklmnopqrstuvwxyz1234567890"';
    const redacted = redactSensitiveClientText(raw);
    expect(redacted).not.toContain('sk-abcdefghijklmnopqrstuvwxyz1234567890');
    expect(redacted).toContain('[REDACTED_API_KEY]');
    expect(containsSensitiveData(raw)).toBe(true);
  });

  it('redacts GitHub personal access tokens', () => {
    const raw = 'Token: ghp_1234567890abcdefghijklmnopqrstuvwxyzAB';
    const redacted = redactSensitiveClientText(raw);
    expect(redacted).not.toContain('ghp_1234567890abcdefghijklmnopqrstuvwxyzAB');
    expect(redacted).toContain('[REDACTED_GH_TOKEN]');
  });

  it('redacts AWS access key ID', () => {
    const raw = 'AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE';
    const redacted = redactSensitiveClientText(raw);
    expect(redacted).not.toContain('AKIAIOSFODNN7EXAMPLE');
    expect(redacted).toContain('[REDACTED_AWS_KEY]');
  });

  it('redacts PEM private keys', () => {
    const raw = `-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEA0Y1+
...secret bytes...
-----END RSA PRIVATE KEY-----`;
    const redacted = redactSensitiveClientText(raw);
    expect(redacted).toBe('[REDACTED_PRIVATE_KEY]');
    expect(containsSensitiveData(raw)).toBe(true);
  });

  it('redacts JWT bearer authorization header', () => {
    const raw =
      'Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.doNotLeakThisSignaturePart';
    const redacted = redactSensitiveClientText(raw);
    expect(redacted).not.toContain('doNotLeakThisSignaturePart');
    expect(redacted).toContain('[REDACTED_TOKEN]');
  });

  it('redacts key-value passwords and secrets', () => {
    const raw = 'db_pass="super_secret_db_password_123"';
    const redacted = redactSensitiveClientText(raw);
    expect(redacted).not.toContain('super_secret_db_password_123');
    expect(redacted).toContain('[REDACTED_SECRET]');
  });

  it('leaves safe regular text untouched', () => {
    const raw = 'This is a normal conversation about React and Next.js performance optimizations.';
    expect(redactSensitiveClientText(raw)).toBe(raw);
    expect(containsSensitiveData(raw)).toBe(false);
  });
});
