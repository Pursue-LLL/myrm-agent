import { describe, expect, it } from 'vitest';
import {
  resolvePositionalReference,
  sanitizePresentationText,
  validateSuggestionChipsPayload,
} from '../presentationToolEngine';
import { PresentationPayload } from '../presentationToolTypes';

describe('presentationToolEngine', () => {
  describe('sanitizePresentationText', () => {
    it('strips dangerous html and script tags', () => {
      const dirty = '<script>alert("xss")</script><b>关注发票</b><style>.bad{}</style>';
      expect(sanitizePresentationText(dirty)).toBe('关注发票');
    });

    it('returns empty string for empty input', () => {
      expect(sanitizePresentationText('')).toBe('');
    });
  });

  describe('validateSuggestionChipsPayload', () => {
    it('fails when raw payload is not an array', () => {
      const res = validateSuggestionChipsPayload('not-array');
      expect(res.valid).toBe(false);
      expect(res.error).toContain('必须为数组类型');
    });

    it('fails when chip count exceeds 4', () => {
      const excess = [
        { label: '1' },
        { label: '2' },
        { label: '3' },
        { label: '4' },
        { label: '5' },
      ];
      const res = validateSuggestionChipsPayload(excess);
      expect(res.valid).toBe(false);
      expect(res.error).toContain('最多为 4 个');
    });

    it('fails when chip text exceeds 32 characters', () => {
      const longText = '这是一个超过三十二个字符非常冗长完全不符合微建议芯片设计原则的长句子无法通过校验';
      const res = validateSuggestionChipsPayload([{ label: longText }]);
      expect(res.valid).toBe(false);
      expect(res.error).toContain('超出 32 字符上限');
    });

    it('succeeds and auto-assigns position index for valid chips', () => {
      const raw = [
        { label: '查看报销明细' },
        { label: '导出 Excel', actionQuery: '导出至 Excel' },
      ];
      const res = validateSuggestionChipsPayload(raw);
      expect(res.valid).toBe(true);
      expect(res.chips).toHaveLength(2);
      expect(res.chips[0]?.position).toBe(1);
      expect(res.chips[0]?.label).toBe('查看报销明细');
      expect(res.chips[1]?.position).toBe(2);
      expect(res.chips[1]?.actionQuery).toBe('导出至 Excel');
    });
  });

  describe('resolvePositionalReference', () => {
    const mockPresentation: PresentationPayload = {
      id: 'mock-pres-1',
      toolName: 'present_products',
      title: '推荐商品',
      createdAt: Date.now(),
      items: [
        {
          id: 'prod-1',
          title: 'MacBook Pro 14',
          position: 1,
        },
        {
          id: 'prod-2',
          title: 'MacBook Pro 16',
          position: 2,
        },
        {
          id: 'prod-3',
          title: 'Mac mini M4',
          position: 3,
        },
      ],
    };

    it('resolves explicit ordinal numbers accurately', () => {
      const res1 = resolvePositionalReference('帮我看看第 2 个', mockPresentation);
      expect(res1.position).toBe(2);
      expect(res1.matchedItem?.position).toBe(2);
      expect(res1.confidence).toBeGreaterThan(0.9);

      const res2 = resolvePositionalReference('选第一个', mockPresentation);
      expect(res2.position).toBe(1);

      const res3 = resolvePositionalReference('第三个配置是什么', mockPresentation);
      expect(res3.position).toBe(3);
    });

    it('resolves spatial references like left, right, and last', () => {
      const resLeft = resolvePositionalReference('我要左边那个', mockPresentation);
      expect(resLeft.position).toBe(1);

      const resRight = resolvePositionalReference('选最右边的', mockPresentation);
      expect(resRight.position).toBe(3);

      const resLast = resolvePositionalReference('最后一个', mockPresentation);
      expect(resLast.position).toBe(3);
    });

    it('returns null match when utterance has no positional keyword', () => {
      const res = resolvePositionalReference('今天周几', mockPresentation);
      expect(res.matchedItem).toBeNull();
      expect(res.position).toBeNull();
      expect(res.confidence).toBe(0);
    });
  });
});
