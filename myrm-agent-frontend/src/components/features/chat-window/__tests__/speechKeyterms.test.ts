import { describe, expect, it } from 'vitest';
import { extractKeyterms } from '../speechKeyterms';

const msg = (content: string) => ({ content, role: 'user' });

describe('extractKeyterms', () => {
  it('returns an empty list when there is no usable term', () => {
    expect(extractKeyterms([])).toEqual([]);
    expect(extractKeyterms([msg('')])).toEqual([]);
    expect(extractKeyterms([msg('   ')])).toEqual([]);
    expect(extractKeyterms([msg('123 !!! ???')])).toEqual([]);
  });

  it('drops single-character CJK fragments', () => {
    expect(extractKeyterms([msg('好')])).toEqual([]);
  });

  it('keeps CJK terms of two or more characters', () => {
    expect(extractKeyterms([msg('好的')])).toEqual(['好的']);
  });

  it('lower-cases and de-duplicates terms regardless of original casing', () => {
    expect(extractKeyterms([msg('Alpha alpha ALPHA')])).toEqual(['alpha']);
    expect(extractKeyterms([msg('ClaudeCode 很强')])).toEqual(['claudecode', '很强']);
  });

  it('extracts acronym-style and dotted identifier terms', () => {
    expect(extractKeyterms([msg('API 和 LLM 都重要')])).toEqual(['api', 'llm', '都重要']);
    expect(extractKeyterms([msg('见 myrm.com 文档')])).toEqual(['myrm.com', '文档']);
  });

  it('orders terms by descending frequency', () => {
    expect(extractKeyterms([msg('定价 定价 定价 成本')])).toEqual(['定价', '成本']);
  });

  it('only reads the most recent messages so stale context cannot bias recognition', () => {
    const words = ['定价', '成本', '竞品', '报告', '图表', '数据', '市场', '价格'];
    const result = extractKeyterms(words.map(msg));

    expect(result).toHaveLength(6);
    expect(result).toEqual(['竞品', '报告', '图表', '数据', '市场', '价格']);
  });

  it('caps the emitted term list to bound the STT keyword payload', () => {
    const words = [
      '定价',
      '成本',
      '竞品',
      '报告',
      '图表',
      '数据',
      '市场',
      '价格',
      '渠道',
      '用户',
      '记忆',
      '工具',
      '技能',
      '模型',
      '部署',
      '沙箱',
      '框架',
      '协议',
    ];
    const result = extractKeyterms([msg(words.join(' '))]);

    expect(result).toHaveLength(15);
    expect(result).toEqual(words.slice(0, 15));
  });
});
