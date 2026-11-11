import { describe, it, expect } from 'vitest';
import { redactSensitiveClientText, containsSensitiveData } from '../clientRedact';
import { jwtShaped } from '@/test-utils/fakeSecrets';

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
    const jwt = jwtShaped(
      'hbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9',
      'zdWIiOiIxMjM0NTY3ODkwIn0',
      'doNotLeakThisSignaturePart',
    );
    const raw = `Authorization: Bearer ${jwt}`;
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

describe('clientRedact: secrets in a URL query string', () => {
  const SECRET = 'abcd1234efgh5678';
  // A link as an object store hands it out: the signature alone opens the file until the link expires.
  const PRESIGNED =
    'https://bucket.s3.amazonaws.com/report.pdf?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Date=20261111T000000Z' +
    `&X-Amz-Expires=3600&X-Amz-SignedHeaders=host&X-Amz-Signature=${SECRET}${SECRET}`;

  it('masks the signature of a presigned link and leaves the rest of the link as it is', () => {
    expect(redactSensitiveClientText(PRESIGNED)).toBe(
      'https://bucket.s3.amazonaws.com/report.pdf?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Date=20261111T000000Z' +
        '&X-Amz-Expires=3600&X-Amz-SignedHeaders=host&X-Amz-Signature=[REDACTED_SECRET]',
    );
    expect(containsSensitiveData(PRESIGNED)).toBe(true);
  });

  it.each([
    'access_token',
    'refresh_token',
    'id_token',
    'auth_token',
    'token',
    'jwt',
    'api_key',
    'api-key',
    'apikey',
    'x-api-key',
    'X-API-KEY',
    'x-goog-api-key',
    'key',
    'client_secret',
    'secret',
    'password',
    'passwd',
    'x-amz-signature',
    'X-Amz-Security-Token',
    'x-goog-signature',
    'signature',
    'sig',
    'session',
    'code',
  ])('masks the value of the "%s" parameter, first or later in the query, and keeps the rest', (param) => {
    const base = 'https://app.example.com/path';
    expect(redactSensitiveClientText(`${base}?${param}=${SECRET}&last=2`)).toBe(
      `${base}?${param}=[REDACTED_SECRET]&last=2`,
    );
    expect(redactSensitiveClientText(`${base}?first=1&${param}=${SECRET}&last=2`)).toBe(
      `${base}?first=1&${param}=[REDACTED_SECRET]&last=2`,
    );
  });

  it('keeps the rest of the link when a configuration-style key sits in a query string', () => {
    expect(redactSensitiveClientText(`https://api.example.com/v1/data?api_key=${SECRET}&page=2`)).toBe(
      'https://api.example.com/v1/data?api_key=[REDACTED_SECRET]&page=2',
    );
  });

  // Where the link ends in the text around it: a Markdown link, an autolink, a quoted address, a sentence, a line.
  it.each([')', ']', '>', '<br>', '"', "'", ' and more', '\nnext line', '#section', '&next=1'])(
    'ends the masked value at %j and keeps what follows',
    (end) => {
      const text = (value: string): string => `see https://x.example.com/a?token=${value}`;
      expect(redactSensitiveClientText(text(`${SECRET}${end}`))).toBe(text(`[REDACTED_SECRET]${end}`));
    },
  );

  it('masks a value of six characters or more, so a one-time code goes and a short flag stays', () => {
    const link = (value: string): string => `https://app.example.com/verify?code=${value}`;
    expect(redactSensitiveClientText(link('123456'))).toBe(link('[REDACTED_SECRET]'));
    expect(redactSensitiveClientText(link('12345'))).toBe(link('12345'));
  });

  it('keeps the label of the more specific rule that already masked the value', () => {
    const jwt = jwtShaped('hbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9', 'zdWIiOiIxMjM0NTY3ODkwIn0', 'abcd1234efgh5678ijkl');
    expect(redactSensitiveClientText(`https://app.example.com/a?token=${jwt}&x=1`)).toBe(
      'https://app.example.com/a?token=[REDACTED_JWT]&x=1',
    );
  });

  it('gives the same text when it runs a second time', () => {
    const once = redactSensitiveClientText(PRESIGNED);
    expect(redactSensitiveClientText(once)).toBe(once);
  });

  it.each([
    'https://example.com/search?q=tokens&page=2&keyword=abcd1234efgh5678&utm_source=news',
    'https://example.com/docs?code=ja&key=1&session=2',
    'https://example.com/watch?v=abcd1234efgh5678&t=42',
    'max_tokens=4096 and monkey=abcd1234efgh5678 and tokens=abcd1234efgh5678',
    'token = request.headers["Authorization"]',
    'Set the token: refreshed values are cached for an hour.',
  ])('leaves ordinary links and text alone: %s', (text) => {
    expect(redactSensitiveClientText(text)).toBe(text);
    expect(containsSensitiveData(text)).toBe(false);
  });

  it('reads a long run of query-string separators and parameter names in linear time', () => {
    const started = performance.now();
    for (const hostile of [
      '?'.repeat(200_000),
      '&token'.repeat(50_000),
      '?token='.repeat(40_000),
      `?token=${'a'.repeat(1_000_000)}`,
    ]) {
      redactSensitiveClientText(hostile);
    }
    expect(performance.now() - started).toBeLessThan(2_000);
  });
});
