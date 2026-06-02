import { describe, it, expect } from 'vitest';
import { linkifyUrls, containsUrl } from '../urlLinkify';

describe('urlLinkify', () => {
  describe('containsUrl', () => {
    it('should detect http URLs', () => {
      expect(containsUrl('Check http://example.com for details')).toBe(true);
    });

    it('should detect https URLs', () => {
      expect(containsUrl('Visit https://example.com/path')).toBe(true);
    });

    it('should return false for text without URLs', () => {
      expect(containsUrl('No URL here')).toBe(false);
    });

    it('should detect multiple URLs', () => {
      expect(containsUrl('Visit https://a.com and http://b.com')).toBe(true);
    });
  });

  describe('linkifyUrls', () => {
    it('should convert HTTP URL to link', () => {
      const input = 'Check http://example.com for details';
      const output = linkifyUrls(input);

      expect(output).toContain('<a href="http://example.com"');
      expect(output).toContain('target="_blank"');
      expect(output).toContain('rel="noopener noreferrer"');
    });

    it('should convert HTTPS URL to link', () => {
      const input = 'Visit https://example.com/path';
      const output = linkifyUrls(input);

      expect(output).toContain('<a href="https://example.com/path"');
      expect(output).toContain('target="_blank"');
    });

    it('should convert multiple URLs', () => {
      const input = 'Visit https://a.com and http://b.com';
      const output = linkifyUrls(input);

      expect(output).toContain('<a href="https://a.com"');
      expect(output).toContain('<a href="http://b.com"');
    });

    it('should preserve non-URL text', () => {
      const input = 'Visit https://example.com for more info';
      const output = linkifyUrls(input);

      expect(output).toContain('Visit ');
      expect(output).toContain(' for more info');
    });

    it('should handle text without URLs', () => {
      const input = 'No URL here';
      const output = linkifyUrls(input);

      expect(output).toBe('No URL here');
    });

    it('should handle URLs with query parameters', () => {
      const input = 'API: http://localhost:11434/v1/models?page=1';
      const output = linkifyUrls(input);

      expect(output).toContain('<a href="http://localhost:11434/v1/models?page=1"');
    });

    it('should handle URLs with hash', () => {
      const input = 'Docs: https://example.com/docs#section';
      const output = linkifyUrls(input);

      expect(output).toContain('<a href="https://example.com/docs#section"');
    });

    it('should not linkify URL inside parentheses incorrectly', () => {
      const input = 'Check (http://example.com) for details';
      const output = linkifyUrls(input);

      // URL should stop before closing parenthesis
      expect(output).toContain('http://example.com');
      expect(output).not.toContain('http://example.com)');
    });
  });
});
