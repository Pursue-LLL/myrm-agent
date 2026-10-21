import { describe, expect, it } from 'vitest';
import { containsWeixinArticleUrl, isWechatArticleFormatterActive } from '../wechatComposerHintUtils';

describe('wechatComposerHintUtils', () => {
  it('detects mp.weixin.qq.com article urls', () => {
    expect(containsWeixinArticleUrl('read https://mp.weixin.qq.com/s/abc')).toBe(true);
    expect(containsWeixinArticleUrl('hello world')).toBe(false);
  });

  it('reports formatter active when mounted and not session-disabled', () => {
    expect(
      isWechatArticleFormatterActive({
        selectedSkillIds: ['skill-1'],
        sessionSkillOverrides: null,
        formatterSkillIds: ['skill-1'],
      }),
    ).toBe(true);
    expect(
      isWechatArticleFormatterActive({
        selectedSkillIds: ['skill-1'],
        sessionSkillOverrides: ['other-skill'],
        formatterSkillIds: ['skill-1'],
      }),
    ).toBe(false);
  });
});
