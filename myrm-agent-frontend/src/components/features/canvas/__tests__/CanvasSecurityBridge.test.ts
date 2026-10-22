import { describe, expect, it } from 'vitest';
import {
  compileSandboxedHtml,
  STRICT_CSP_META,
  STRICT_SANDBOX_POLICY,
  validateInboundCanvasMessage,
} from '../CanvasSecurityBridge';

describe('CanvasSecurityBridge', () => {
  it('enforces strict sandbox policy without allow-same-origin', () => {
    expect(STRICT_SANDBOX_POLICY).toBe('allow-scripts allow-forms');
    expect(STRICT_SANDBOX_POLICY).not.toContain('allow-same-origin');
  });

  it('compiles HTML fragments with strict CSP and runtime injection script', () => {
    const rawHtml = '<div id="app"><h1>Canvas Content</h1></div>';
    const compiled = compileSandboxedHtml(rawHtml);

    expect(compiled).toContain(STRICT_CSP_META);
    expect(compiled).toContain('default-src \'none\'');
    expect(compiled).toContain('connect-src \'none\'');
    expect(compiled).toContain('window.fetch = function');
    expect(compiled).toContain('<div id="app"><h1>Canvas Content</h1></div>');
  });

  it('injects CSP and runtime into existing complete HTML head', () => {
    const fullHtml = '<!DOCTYPE html><html><head><title>Test</title></head><body>Hello</body></html>';
    const compiled = compileSandboxedHtml(fullHtml);

    expect(compiled).toContain('<head><meta http-equiv="Content-Security-Policy"');
    expect(compiled).toContain('window.parent.postMessage');
    expect(compiled).toContain('Hello</body>');
  });

  it('handles empty content safely with standard fallback container', () => {
    const compiled = compileSandboxedHtml('');
    expect(compiled).toContain(STRICT_CSP_META);
    expect(compiled).toContain('<!DOCTYPE html><html><head>');
  });

  describe('validateInboundCanvasMessage', () => {
    const fakeWindow = {} as Window;
    const anotherWindow = {} as Window;

    it('rejects messages originating from unknown windows', () => {
      const event = {
        source: anotherWindow,
        data: { type: 'canvas-egress-request', url: 'https://example.com' },
      } as MessageEvent;

      const result = validateInboundCanvasMessage(event, fakeWindow);
      expect(result).toBeNull();
    });

    it('rejects messages with non-object or invalid data payloads', () => {
      const event1 = {
        source: fakeWindow,
        data: 'string-data',
      } as MessageEvent;
      expect(validateInboundCanvasMessage(event1, fakeWindow)).toBeNull();

      const event2 = {
        source: fakeWindow,
        data: { noTypeField: true },
      } as MessageEvent;
      expect(validateInboundCanvasMessage(event2, fakeWindow)).toBeNull();
    });

    it('correctly parses and returns valid inbound canvas message', () => {
      const event = {
        source: fakeWindow,
        data: {
          type: 'canvas-egress-request',
          requestId: 'req_123',
          url: 'https://api.external.org/data',
          domain: 'api.external.org',
          method: 'POST',
        },
      } as MessageEvent;

      const parsed = validateInboundCanvasMessage(event, fakeWindow);
      expect(parsed).toEqual({
        type: 'canvas-egress-request',
        requestId: 'req_123',
        url: 'https://api.external.org/data',
        domain: 'api.external.org',
        method: 'POST',
      });
    });
  });
});
