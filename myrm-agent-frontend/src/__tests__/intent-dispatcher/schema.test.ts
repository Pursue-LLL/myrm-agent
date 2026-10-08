import { parseIntentUrl, redactIntentUrl } from '@/lib/intent-dispatcher/schema';

describe('Universal Intent Protocol (UIP) Schema Parser', () => {
  describe('Valid Intents', () => {
    it('should parse chat intent correctly', () => {
      const result = parseIntentUrl('myrmagent://chat/12345');
      expect(result).toEqual({ scheme: 'myrmagent', action: 'chat', id: '12345' });
    });

    it('should parse agent intent correctly', () => {
      const result = parseIntentUrl('myrmagent://agent/agent-abc');
      expect(result).toEqual({ scheme: 'myrmagent', action: 'agent', id: 'agent-abc' });
    });

    it('should parse ask intent correctly with text', () => {
      const result = parseIntentUrl('myrmagent://ask?text=hello%20world');
      expect(result).toEqual({ scheme: 'myrmagent', action: 'ask', text: 'hello world' });
    });

    it('should parse oauth callback intent correctly', () => {
      const result = parseIntentUrl('myrmagent://oauth/callback?exchange=ex-1&state=st-1');
      expect(result).toEqual({
        scheme: 'myrmagent',
        action: 'oauth',
        path: 'callback',
        exchange: 'ex-1',
        state: 'st-1',
      });
    });

    it('should parse install-skill intent correctly', () => {
      const result = parseIntentUrl('myrmagent://install-skill?url=https%3A%2F%2Fexample.com%2Fskill.json');
      expect(result).toEqual({
        scheme: 'myrmagent',
        action: 'install-skill',
        url: 'https://example.com/skill.json',
      });
    });

    it('should parse web-based intent correctly', () => {
      const result = parseIntentUrl('https://app.myrmagent.com/intent/chat/67890');
      expect(result).toEqual({ scheme: 'https', action: 'chat', id: '67890' });
    });

    it('should parse web-based agent intent correctly', () => {
      const result = parseIntentUrl('https://app.myrmagent.com/intent/agent/office-doc');
      expect(result).toEqual({ scheme: 'https', action: 'agent', id: 'office-doc' });
    });

    it('should parse web-based ask intent correctly', () => {
      const result = parseIntentUrl('https://app.myrmagent.com/intent/ask?text=help%20me');
      expect(result).toEqual({ scheme: 'https', action: 'ask', text: 'help me' });
    });

    it('should parse web-based oauth callback correctly', () => {
      const result = parseIntentUrl('https://app.myrmagent.com/intent/oauth/callback?exchange=ex-2&state=st-2');
      expect(result).toEqual({
        scheme: 'https',
        action: 'oauth',
        path: 'callback',
        exchange: 'ex-2',
        state: 'st-2',
      });
    });

    it('should handle URL-encoded special characters in text', () => {
      const result = parseIntentUrl('myrmagent://ask?text=%E5%B8%AE%E6%88%91%E5%86%99%E6%8A%A5%E5%91%8A');
      expect(result).toEqual({ scheme: 'myrmagent', action: 'ask', text: '帮我写报告' });
    });
  });

  describe('Invalid Intents (Security Gateway)', () => {
    it('should throw on unsupported scheme', () => {
      expect(() => parseIntentUrl('ftp://chat/123')).toThrow();
    });

    it('should throw on unsupported action', () => {
      expect(() => parseIntentUrl('myrmagent://hack/123')).toThrow();
    });

    it('should throw on missing required parameters (chat id)', () => {
      expect(() => parseIntentUrl('myrmagent://chat/')).toThrow();
    });

    it('should throw on missing required parameters (ask text)', () => {
      expect(() => parseIntentUrl('myrmagent://ask')).toThrow();
    });

    it('should throw on oauth callback without a state', () => {
      expect(() => parseIntentUrl('myrmagent://oauth/callback?exchange=ex-1')).toThrow();
    });

    it('should throw on oauth callback without an exchange id', () => {
      expect(() => parseIntentUrl('myrmagent://oauth/callback?state=st-1')).toThrow();
    });

    it('should reject the legacy token-carrying oauth callback', () => {
      expect(() => parseIntentUrl('myrmagent://oauth/callback?token=abc')).toThrow();
    });

    it('should throw on malicious javascript injection attempt in URL', () => {
      expect(() => parseIntentUrl('javascript:alert(1)')).toThrow();
    });

    it('should throw on install-skill with invalid URL', () => {
      expect(() => parseIntentUrl('myrmagent://install-skill?url=not-a-url')).toThrow();
    });

    it('should throw on empty install-skill URL', () => {
      expect(() => parseIntentUrl('myrmagent://install-skill')).toThrow();
    });

    it('should throw on web path without intent prefix', () => {
      expect(() => parseIntentUrl('https://app.myrmagent.com/chat/123')).toThrow();
    });

    it('should safely resolve path traversal without filesystem access', () => {
      const result = parseIntentUrl('myrmagent://chat/../../../etc/passwd');
      expect(result.action).toBe('chat');
      expect(result).toHaveProperty('id');
    });
  });

  describe('redactIntentUrl', () => {
    it('masks exchange, state and token params while keeping the rest of the link', () => {
      const out = redactIntentUrl('myrmagent://oauth/callback?exchange=secret-ex&state=secret-st&token=secret-tk&x=1');
      expect(out).not.toContain('secret');
      expect(out).toContain('x=1');
      expect(out.startsWith('myrmagent://oauth/callback')).toBe(true);
    });

    it('leaves links without sensitive params untouched', () => {
      expect(redactIntentUrl('myrmagent://chat/123')).toBe('myrmagent://chat/123');
    });

    it('never echoes an unparseable input', () => {
      expect(redactIntentUrl('not a url token=secret')).toBe('[unparseable-url]');
    });
  });
});
