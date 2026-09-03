import { describe, expect, it } from 'vitest';
import {
  extractVideoEmbedInfo,
  formatPlayerTime,
} from '../VideoKnowledgePlayer';
import { isValidVideoUrl } from '../WikiVideoImportDialog';
import { buildWikiApiPath } from '@/services/wikiService';

describe('VideoKnowledgePlayer utils', () => {
  it('formats player time properly for seconds, minutes, and hours', () => {
    expect(formatPlayerTime(0)).toBe('00:00');
    expect(formatPlayerTime(45)).toBe('00:45');
    expect(formatPlayerTime(75)).toBe('01:15');
    expect(formatPlayerTime(3600)).toBe('01:00:00');
    expect(formatPlayerTime(3672)).toBe('01:01:12');
  });

  it('correctly parses Bilibili video embed URLs with seek offset', () => {
    const info = extractVideoEmbedInfo('https://www.bilibili.com/video/BV1xx411c7Xz', 125);
    expect(info.type).toBe('bilibili');
    expect(info.sourceId).toBe('BV1xx411c7Xz');
    expect(info.embedUrl).toContain('player.bilibili.com');
    expect(info.embedUrl).toContain('bvid=BV1xx411c7Xz');
    expect(info.embedUrl).toContain('t=125');
  });

  it('correctly parses standard YouTube URLs with start offset', () => {
    const info = extractVideoEmbedInfo('https://www.youtube.com/watch?v=dQw4w9WgXcQ', 90);
    expect(info.type).toBe('youtube');
    expect(info.sourceId).toBe('dQw4w9WgXcQ');
    expect(info.embedUrl).toContain('youtube-nocookie.com/embed/dQw4w9WgXcQ');
    expect(info.embedUrl).toContain('start=90');
  });

  it('correctly parses youtu.be short URLs', () => {
    const info = extractVideoEmbedInfo('https://youtu.be/dQw4w9WgXcQ', 30);
    expect(info.type).toBe('youtube');
    expect(info.sourceId).toBe('dQw4w9WgXcQ');
    expect(info.embedUrl).toContain('start=30');
  });

  it('falls back to direct video format for regular links', () => {
    const info = extractVideoEmbedInfo('https://example.com/assets/video.mp4', 0);
    expect(info.type).toBe('direct');
    expect(info.embedUrl).toBe('https://example.com/assets/video.mp4');
  });
});

describe('WikiVideoImportDialog URL validation', () => {
  it('identifies supported video platforms', () => {
    expect(isValidVideoUrl('https://www.bilibili.com/video/BV1xx411c7Xz')).toBe(true);
    expect(isValidVideoUrl('https://b23.tv/av170001')).toBe(true);
    expect(isValidVideoUrl('https://www.youtube.com/watch?v=dQw4w9WgXcQ')).toBe(true);
    expect(isValidVideoUrl('https://youtu.be/dQw4w9WgXcQ')).toBe(true);
  });

  it('rejects unsupported or empty URLs', () => {
    expect(isValidVideoUrl('')).toBe(false);
    expect(isValidVideoUrl('   ')).toBe(false);
    expect(isValidVideoUrl('https://example.com/article')).toBe(false);
    expect(isValidVideoUrl('not-a-url')).toBe(false);
  });
});

describe('wikiService video API path builder', () => {
  it('formats import video path correctly with and without agent scope', () => {
    expect(buildWikiApiPath('/wiki/import/video', null)).toBe('/wiki/import/video');
    expect(buildWikiApiPath('/wiki/import/video', 'agent-kb')).toBe('/wiki/import/video?agent_id=agent-kb');
  });
});
