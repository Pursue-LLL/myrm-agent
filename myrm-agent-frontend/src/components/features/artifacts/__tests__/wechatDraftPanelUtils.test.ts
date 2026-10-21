import { describe, expect, it } from 'vitest';
import {
  clampWechatAuthor,
  resolveDefaultWechatAuthor,
  resolveDefaultWechatDraftTitle,
} from '../wechatDraftPanelUtils';

describe('wechatDraftPanelUtils', () => {
  it('clamps author to eight characters', () => {
    expect(clampWechatAuthor('某某科技有限公司部')).toBe('某某科技有限公司');
  });

  it('resolves default title from wechat html filename', () => {
    expect(resolveDefaultWechatDraftTitle('post.wechat.html')).toBe('post');
  });

  it('prefers agent name for default author', () => {
    expect(resolveDefaultWechatAuthor('编辑部', null)).toBe('编辑部');
    expect(resolveDefaultWechatAuthor('', '预设号')).toBe('预设号');
  });
});
