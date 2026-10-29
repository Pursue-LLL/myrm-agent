import { describe, expect, it } from 'vitest';
import { isSafeLinkUrl } from '../exportUrlPolicy';

describe('isSafeLinkUrl', () => {
  it.each([
    'https://example.com/a?b=c#d',
    'http://example.com',
    'HTTPS://EXAMPLE.COM',
    'mailto:someone@example.com',
    'tel:+15551234567',
    '#section',
    '/docs/page',
    './relative/page.html',
    '../up.html',
    '?query=1',
    '//cdn.example.com/x',
    'page.html',
    '  https://example.com  ',
  ])('keeps %j', (url) => {
    expect(isSafeLinkUrl(url)).toBe(true);
  });

  it.each([
    'javascript:alert(1)',
    'JaVaScRiPt:alert(1)',
    ' javascript:alert(1)',
    '\u0001javascript:alert(1)',
    'java\tscript:alert(1)',
    'java\nscript:alert(1)',
    'javascript\t:alert(1)',
    'vbscript:msgbox(1)',
    'data:text/html,<script>alert(1)</script>',
    'data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==',
    'file:///etc/passwd',
    'blob:https://example.com/uuid',
    'ftp://example.com/x',
    'view-source:https://example.com',
    'about:blank',
  ])('refuses %j', (url) => {
    expect(isSafeLinkUrl(url)).toBe(false);
  });

  it('treats a percent-encoded scheme separator as a relative path, as the browser does', () => {
    expect(isSafeLinkUrl('java%09script:alert(1)')).toBe(true);
  });

  it('refuses an empty-looking target that cannot be parsed', () => {
    expect(isSafeLinkUrl('http://')).toBe(false);
  });
});
