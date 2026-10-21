import { describe, expect, it } from 'vitest';
import { extractFirstLocalImageSrc } from '../wechatDraftCoverUtils';

describe('extractFirstLocalImageSrc', () => {
  it('returns the first local image src and skips remote urls', () => {
    const html = [
      '<p>intro</p>',
      '<img src="https://example.com/remote.png" alt="remote">',
      '<img src="images/cover.png" alt="cover">',
      '<img src="./hero.jpg" alt="hero">',
    ].join('');
    expect(extractFirstLocalImageSrc(html)).toBe('images/cover.png');
  });

  it('accepts absolute workspace paths from formatter output', () => {
    const html = '<img src="/Users/me/.myrm/workspace/chat_1/images/hero.png" alt="hero">';
    expect(extractFirstLocalImageSrc(html)).toBe('/Users/me/.myrm/workspace/chat_1/images/hero.png');
  });

  it('returns null when no local images exist', () => {
    const html = '<p>text only</p><img src="https://cdn.example/a.png">';
    expect(extractFirstLocalImageSrc(html)).toBeNull();
  });
});
