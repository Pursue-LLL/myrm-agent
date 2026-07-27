import { parseIntentUrl } from '@/lib/intent-dispatcher/schema';

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
      const result = parseIntentUrl('myrmagent://oauth/callback?token=secret-token');
      expect(result).toEqual({ scheme: 'myrmagent', action: 'oauth', path: 'callback', token: 'secret-token' });
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
      const result = parseIntentUrl('https://app.myrmagent.com/intent/oauth/callback?token=abc123');
      expect(result).toEqual({ scheme: 'https', action: 'oauth', path: 'callback', token: 'abc123' });
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
});
