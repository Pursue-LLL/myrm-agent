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

    it('should parse web-based intent correctly', () => {
      const result = parseIntentUrl('https://app.myrmagent.com/intent/chat/67890');
      expect(result).toEqual({ scheme: 'https', action: 'chat', id: '67890' });
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
  });
});
