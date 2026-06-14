import { describe, it, expect, vi } from 'vitest';

vi.mock('@/components/agent/agent-icons', () => ({
  AGENT_ICON_REGISTRY: {
    general: { svg: null, gradient: ['#8b5cf6', '#7c3aed'] },
    writer: { svg: null, gradient: ['#f43f5e', '#e11d48'] },
  },
}));

import { parseAvatarUrl, isIconAvatar } from '../avatar-utils';

describe('avatar-utils', () => {
  describe('parseAvatarUrl', () => {
    it('returns null for null/undefined/empty input', () => {
      expect(parseAvatarUrl(null)).toBeNull();
      expect(parseAvatarUrl(undefined)).toBeNull();
      expect(parseAvatarUrl('')).toBeNull();
    });

    it('parses valid icon: format', () => {
      expect(parseAvatarUrl('icon:general')).toEqual({ type: 'icon', iconId: 'general' });
      expect(parseAvatarUrl('icon:writer')).toEqual({ type: 'icon', iconId: 'writer' });
    });

    it('returns null for invalid icon ID', () => {
      expect(parseAvatarUrl('icon:nonexistent')).toBeNull();
    });

    it('parses emoji: format', () => {
      expect(parseAvatarUrl('emoji:🤖')).toEqual({ type: 'emoji', emoji: '🤖' });
      expect(parseAvatarUrl('emoji:A')).toEqual({ type: 'emoji', emoji: 'A' });
    });

    it('parses home:// format with agentId', () => {
      expect(parseAvatarUrl('home://avatar.png', 'agent-123')).toEqual({
        type: 'image',
        src: '/api/v1/user-agents/agent-123/files/avatar.png',
      });
    });

    it('returns null for home:// without agentId', () => {
      expect(parseAvatarUrl('home://avatar.png')).toBeNull();
      expect(parseAvatarUrl('home://avatar.png', undefined)).toBeNull();
    });

    it('parses http/https URLs', () => {
      expect(parseAvatarUrl('https://example.com/img.png')).toEqual({
        type: 'image',
        src: 'https://example.com/img.png',
      });
      expect(parseAvatarUrl('http://cdn.test/a.jpg')).toEqual({
        type: 'image',
        src: 'http://cdn.test/a.jpg',
      });
    });

    it('parses gradient: format', () => {
      expect(parseAvatarUrl('gradient:3')).toEqual({ type: 'gradient', index: 3 });
      expect(parseAvatarUrl('gradient:0')).toEqual({ type: 'gradient', index: 0 });
    });

    it('returns null for invalid gradient index', () => {
      expect(parseAvatarUrl('gradient:abc')).toBeNull();
    });

    it('parses lucide: format', () => {
      expect(parseAvatarUrl('lucide:database')).toEqual({ type: 'lucide', iconName: 'database' });
      expect(parseAvatarUrl('lucide:file-spreadsheet')).toEqual({ type: 'lucide', iconName: 'file-spreadsheet' });
      expect(parseAvatarUrl('lucide:layout')).toEqual({ type: 'lucide', iconName: 'layout' });
    });

    it('returns null for unrecognized formats', () => {
      expect(parseAvatarUrl('random-string')).toBeNull();
      expect(parseAvatarUrl('ftp://something')).toBeNull();
    });
  });

  describe('isIconAvatar', () => {
    it('returns true for valid icon URLs', () => {
      expect(isIconAvatar('icon:general')).toBe(true);
      expect(isIconAvatar('icon:writer')).toBe(true);
    });

    it('returns false for invalid icon IDs', () => {
      expect(isIconAvatar('icon:nonexistent')).toBe(false);
    });

    it('returns false for non-icon formats', () => {
      expect(isIconAvatar('emoji:🤖')).toBe(false);
      expect(isIconAvatar('https://example.com')).toBe(false);
      expect(isIconAvatar(null)).toBe(false);
      expect(isIconAvatar(undefined)).toBe(false);
    });
  });
});
