import { describe, expect, it } from 'vitest';
import {
  isPlaceholderLink,
  inferCategoryAndEntity,
  scanLinksFromHtml,
  replaceLinksInHtml,
} from '../realLinkDetector';
import type { DetectedLinkEntity } from '../realLinkTypes';

describe('realLinkDetector', () => {
  it('isPlaceholderLink 准确识别各类占位假链', () => {
    expect(isPlaceholderLink('#')).toBe(true);
    expect(isPlaceholderLink('   #   ')).toBe(true);
    expect(isPlaceholderLink('javascript:void(0)')).toBe(true);
    expect(isPlaceholderLink('https://example.com/apply')).toBe(true);
    expect(isPlaceholderLink('http://placeholder.domain/shop')).toBe(true);
    expect(isPlaceholderLink('about:blank')).toBe(true);

    // 真实链接返回 false
    expect(isPlaceholderLink('https://careers.3squirrels.com/campus')).toBe(false);
    expect(isPlaceholderLink('https://docs.myrm.io/guide')).toBe(false);
  });

  it('inferCategoryAndEntity 能够结合锚文本推断业务意图与匹配权威企业实体', () => {
    const recruitMatch = inferCategoryAndEntity('立即投递校招岗位');
    expect(recruitMatch.category).toBe('recruitment');
    expect(recruitMatch.targetEntityName).toBe('三只松鼠官方校园招聘门户');
    expect(recruitMatch.resolvedRealUrl).toBe('https://careers.3squirrels.com/campus');

    const shopMatch = inferCategoryAndEntity('前往天猫官方商城购买');
    expect(shopMatch.category).toBe('commerce');
    expect(shopMatch.targetEntityName).toBe('三只松鼠天猫官方旗舰店');

    const generalMatch = inferCategoryAndEntity('随意跳转');
    expect(generalMatch.category).toBe('general');
  });

  it('scanLinksFromHtml 提取 HTML 中所有链接并赋予对应审计状态', () => {
    const sampleHtml = `
      <div>
        <a href="#">投递简历</a>
        <a href="https://docs.myrm.io">查看开发文档</a>
      </div>
    `;

    const scanned = scanLinksFromHtml(sampleHtml);
    expect(scanned.length).toBe(2);

    expect(scanned[0].originalHref).toBe('#');
    expect(scanned[0].status).toBe('placeholder_detected');
    expect(scanned[0].category).toBe('recruitment');
    expect(scanned[0].resolvedRealUrl).toBe('https://careers.3squirrels.com/campus');

    expect(scanned[1].originalHref).toBe('https://docs.myrm.io');
    expect(scanned[1].status).toBe('aligned');
    expect(scanned[1].category).toBe('documentation');
  });

  it('replaceLinksInHtml 能够安全将对齐后的真实链接替换回 HTML 字符串', () => {
    const originalHtml = '<a href="#" class="btn">立即投递校招岗位</a>';
    const mockEntities: DetectedLinkEntity[] = [
      {
        id: 'link_1',
        originalHref: '#',
        anchorText: '立即投递校招岗位',
        category: 'recruitment',
        status: 'aligned',
        resolvedRealUrl: 'https://careers.3squirrels.com/campus',
        confidenceScore: 0.95,
      },
    ];

    const replaced = replaceLinksInHtml(originalHtml, mockEntities);
    expect(replaced).toContain('href="https://careers.3squirrels.com/campus"');
    expect(replaced).not.toContain('href="#"');
  });
});
