import { describe, expect, it } from 'vitest';
import {
  buildAgentSkillsSettingsHref,
  containsWeixinArticleUrl,
  isWechatArticleFormatterActive,
  WECHAT_ARTICLE_FORMATTER_SKILL,
} from '../wechatComposerHintUtils';

describe('containsWeixinArticleUrl', () => {
  it.each([
    'https://mp.weixin.qq.com/s/D6PTZsG3DgbEOB11vvQQMA',
    'https://mp.weixin.qq.com/s?__biz=Mzg2NzY0MTkzOQ==&mid=2247493844&idx=1',
    'http://mp.weixin.qq.com/s/abc',
    'HTTPS://MP.WEIXIN.QQ.COM/S/abc',
    'https://sub.mp.weixin.qq.com/s/abc',
    'read https://mp.weixin.qq.com/s/abc and summarise it',
    'two links https://example.com/a and\nhttps://mp.weixin.qq.com/s?__biz=x',
  ])('recognises an article link: %s', (text) => {
    expect(containsWeixinArticleUrl(text)).toBe(true);
  });

  it.each([
    'hello world',
    '',
    'mp.weixin.qq.com/s/abc',
    'https://mp.weixin.qq.com/',
    'https://mp.weixin.qq.com/s',
    'https://mp.weixin.qq.com/s#rd',
    'https://mp.weixin.qq.com/s and then some words',
    'https://mp.weixin.qq.com/mp/homepage?__biz=x',
    'https://mp.weixin.qq.com/search?q=x',
    'https://mp.weixin.qq.com/sx/abc',
    'https://example.com/s/abc',
    'https://evilmp.weixin.qq.com/s/abc',
    'https://mp.weixin.qq.com.evil.example/s/abc',
    'ftp://mp.weixin.qq.com/s/abc',
  ])('ignores everything else: %s', (text) => {
    expect(containsWeixinArticleUrl(text)).toBe(false);
  });

  it('stays correct when called repeatedly (no sticky regex state)', () => {
    const text = 'https://mp.weixin.qq.com/s/abc';

    expect([containsWeixinArticleUrl(text), containsWeixinArticleUrl(text), containsWeixinArticleUrl(text)]).toEqual([
      true,
      true,
      true,
    ]);
  });
});

describe('buildAgentSkillsSettingsHref', () => {
  it('opens the skills section of the given agent, with the id escaped', () => {
    expect(buildAgentSkillsSettingsHref('agent-1')).toBe('/settings/agents?agentId=agent-1#loadout');
    expect(buildAgentSkillsSettingsHref('a b&c')).toBe('/settings/agents?agentId=a%20b%26c#loadout');
  });

  it.each([null, undefined, ''])('falls back to the agent list when there is no agent: %j', (agentId) => {
    expect(buildAgentSkillsSettingsHref(agentId)).toBe('/settings/agents#loadout');
  });
});

describe('isWechatArticleFormatterActive', () => {
  const formatterSkillIds = ['formatter-1'];

  it('is off when the skill is not installed at all', () => {
    expect(
      isWechatArticleFormatterActive({
        selectedSkillIds: ['formatter-1'],
        sessionSkillOverrides: null,
        formatterSkillIds: [],
      }),
    ).toBe(false);
  });

  it('is off when the agent has not mounted it, whatever the session says', () => {
    expect(
      isWechatArticleFormatterActive({ selectedSkillIds: ['other'], sessionSkillOverrides: null, formatterSkillIds }),
    ).toBe(false);
    expect(
      isWechatArticleFormatterActive({
        selectedSkillIds: ['other'],
        sessionSkillOverrides: [WECHAT_ARTICLE_FORMATTER_SKILL],
        formatterSkillIds,
      }),
    ).toBe(false);
  });

  it('is on when mounted and the session has no override', () => {
    expect(
      isWechatArticleFormatterActive({
        selectedSkillIds: ['x', 'formatter-1'],
        sessionSkillOverrides: null,
        formatterSkillIds,
      }),
    ).toBe(true);
  });

  it('with a session override, is on only if the override names the skill', () => {
    const base = { selectedSkillIds: ['formatter-1'], formatterSkillIds };

    expect(
      isWechatArticleFormatterActive({ ...base, sessionSkillOverrides: [WECHAT_ARTICLE_FORMATTER_SKILL, 'x'] }),
    ).toBe(true);
    expect(isWechatArticleFormatterActive({ ...base, sessionSkillOverrides: ['other-skill'] })).toBe(false);
    expect(isWechatArticleFormatterActive({ ...base, sessionSkillOverrides: [] })).toBe(false);
  });

  it('accepts any one of several installed copies of the skill', () => {
    expect(
      isWechatArticleFormatterActive({
        selectedSkillIds: ['formatter-2'],
        sessionSkillOverrides: null,
        formatterSkillIds: ['formatter-1', 'formatter-2'],
      }),
    ).toBe(true);
  });
});
