import { describe, it, expect } from 'vitest';
import {
  generatePrefilledPrompt,
  filterPlaybooksByCategory,
  searchPlaybooks,
  getCategoryMeta,
  STATIC_COMPARISON_FEATURES,
} from '../nonCodingPlaybookEngine';
import { PlaybookScenario } from '../nonCodingPlaybookTypes';

describe('nonCodingPlaybookEngine', () => {
  const sampleScenario: PlaybookScenario = {
    id: 'test-sc',
    title: '发票报销整理',
    category: 'finance',
    description: '自动 OCR 发票并导出 Excel',
    inputPlaceholder: '发票路径',
    toolsUsed: ['ocr_scanner', 'excel_generator'],
    expectedOutput: '报销明细表.xlsx',
    pipelineFlow: ['OCR 识别', '生成表格'],
    parameters: [
      {
        id: 'invoice_path',
        label: '路径',
        type: 'text',
        defaultValue: './invoices',
      },
      {
        id: 'category',
        label: '分类',
        type: 'text',
        defaultValue: '差旅交通',
      },
    ],
    defaultPromptTemplate:
      '请处理 {{invoice_path}} 下的发票，类别为 {{category}}。',
  };

  describe('generatePrefilledPrompt', () => {
    it('replaces placeholders with provided form values', () => {
      const prompt = generatePrefilledPrompt(sampleScenario, {
        invoice_path: '/my/custom/path',
        category: '办公采购',
      });
      expect(prompt).toBe(
        '请处理 /my/custom/path 下的发票，类别为 办公采购。',
      );
    });

    it('falls back to default parameter values when not provided in form', () => {
      const prompt = generatePrefilledPrompt(sampleScenario, {});
      expect(prompt).toBe('请处理 ./invoices 下的发票，类别为 差旅交通。');
    });
  });

  describe('filterPlaybooksByCategory', () => {
    const list: PlaybookScenario[] = [
      sampleScenario,
      {
        ...sampleScenario,
        id: 'test-admin',
        title: '会议纪要',
        category: 'admin',
      },
      {
        ...sampleScenario,
        id: 'test-legal',
        title: '合同审查',
        category: 'legal',
      },
    ];

    it('returns all scenarios when category is all', () => {
      expect(filterPlaybooksByCategory(list, 'all').length).toBe(3);
    });

    it('filters scenarios by specific category', () => {
      const financeList = filterPlaybooksByCategory(list, 'finance');
      expect(financeList.length).toBe(1);
      expect(financeList[0]?.id).toBe('test-sc');

      const legalList = filterPlaybooksByCategory(list, 'legal');
      expect(legalList.length).toBe(1);
      expect(legalList[0]?.id).toBe('test-legal');
    });
  });

  describe('searchPlaybooks', () => {
    const list: PlaybookScenario[] = [
      sampleScenario,
      {
        ...sampleScenario,
        id: 'test-research',
        title: '行业研报深度对比',
        description: '对比多篇 PDF 报告',
        expectedOutput: '决策内参.md',
        toolsUsed: ['pdf_reader'],
        category: 'research',
      },
    ];

    it('returns all scenarios if keyword is empty', () => {
      expect(searchPlaybooks(list, '').length).toBe(2);
      expect(searchPlaybooks(list, '   ').length).toBe(2);
    });

    it('matches by title or tool or expected output case-insensitively', () => {
      expect(searchPlaybooks(list, '报销').length).toBe(1);
      expect(searchPlaybooks(list, 'EXCEL').length).toBe(1);
      expect(searchPlaybooks(list, 'PDF').length).toBe(1);
      expect(searchPlaybooks(list, '不存在的关键词').length).toBe(0);
    });
  });

  describe('getCategoryMeta', () => {
    it('returns label and styling classes for categories', () => {
      expect(getCategoryMeta('finance').label).toBe('财务发票');
      expect(getCategoryMeta('legal').label).toBe('合同法务');
      expect(getCategoryMeta('admin').label).toBe('行政办公');
      expect(getCategoryMeta('general').label).toBe('通用生产力');
    });
  });

  describe('STATIC_COMPARISON_FEATURES', () => {
    it('contains 4 core comparison dimensions with advantages', () => {
      expect(STATIC_COMPARISON_FEATURES.length).toBe(4);
      expect(STATIC_COMPARISON_FEATURES[0]?.title).toContain('本地文件');
      expect(STATIC_COMPARISON_FEATURES[1]?.title).toContain('数据计算');
      expect(STATIC_COMPARISON_FEATURES[2]?.title).toContain('持久记忆');
      expect(STATIC_COMPARISON_FEATURES[3]?.title).toContain('多智能体');
    });
  });
});
