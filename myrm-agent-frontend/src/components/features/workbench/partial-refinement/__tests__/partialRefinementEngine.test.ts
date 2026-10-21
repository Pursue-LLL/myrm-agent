import { describe, it, expect } from 'vitest';
import {
  validateSelectionOffsets,
  extractSelectionWithContext,
  applyInPlaceReplacement,
  estimateTokenSavings,
  generateSimulatedRefinement,
} from '../partialRefinementEngine';
import { SelectionRange } from '../workbenchTypes';

describe('partialRefinementEngine pure algorithm unit tests', () => {
  const sampleDocument = '这是研报前言。\n智能体算力需求在2026年激进扩张。\n这是研报结语。';

  describe('validateSelectionOffsets', () => {
    it('validates offsets accurately within boundaries', () => {
      expect(validateSelectionOffsets(sampleDocument, 0, 7)).toBe(true);
      expect(validateSelectionOffsets(sampleDocument, 8, 20)).toBe(true);
      expect(validateSelectionOffsets(sampleDocument, -1, 5)).toBe(false);
      expect(validateSelectionOffsets(sampleDocument, 10, 5)).toBe(false);
      expect(validateSelectionOffsets(sampleDocument, 0, 9999)).toBe(false);
    });
  });

  describe('extractSelectionWithContext', () => {
    it('extracts target text and bounding context correctly', () => {
      const range = extractSelectionWithContext(sampleDocument, 8, 25, 6);

      expect(range.startOffset).toBe(8);
      expect(range.endOffset).toBe(25);
      expect(range.selectedText).toBe('智能体算力需求在2026年激进扩张');
      expect(range.contextBefore).toBe('研报前言。\n');
      expect(range.contextAfter).toBe('。\n这是研报');
    });

    it('clamps offsets when out of bounds', () => {
      const range = extractSelectionWithContext(sampleDocument, -5, 100);
      expect(range.startOffset).toBe(0);
      expect(range.endOffset).toBe(sampleDocument.length);
      expect(range.selectedText).toBe(sampleDocument);
    });
  });

  describe('applyInPlaceReplacement', () => {
    it('replaces target chunk precisely using offset coordinates', () => {
      const range: SelectionRange = {
        startOffset: 8,
        endOffset: 25,
        selectedText: '智能体算力需求在2026年激进扩张',
        contextBefore: '',
        contextAfter: '',
      };

      const replaced = applyInPlaceReplacement(
        sampleDocument,
        range,
        '智能体算力需求稳健增长'
      );

      expect(replaced).toBe(
        '这是研报前言。\n智能体算力需求稳健增长。\n这是研报结语。'
      );
    });

    it('falls back to substring matching if offsets are invalid but text is found', () => {
      const range: SelectionRange = {
        startOffset: 999, // Invalid offset
        endOffset: 10,
        selectedText: '智能体算力需求在2026年激进扩张',
        contextBefore: '',
        contextAfter: '',
      };

      const replaced = applyInPlaceReplacement(
        sampleDocument,
        range,
        '智能体算力稳健增长'
      );

      expect(replaced).toBe(
        '这是研报前言。\n智能体算力稳健增长。\n这是研报结语。'
      );
    });
  });

  describe('estimateTokenSavings', () => {
    it('calculates significant token savings when modifying small chunks', () => {
      const fullTextLength = 4000; // ~1000 tokens
      const chunkLength = 120; // ~30 tokens

      const stats = estimateTokenSavings(fullTextLength, chunkLength);

      expect(stats.fullTokens).toBe(1000);
      expect(stats.chunkTokens).toBe(30);
      expect(stats.tokensSaved).toBe(970);
      expect(stats.savingsPercent).toBeGreaterThanOrEqual(90);
    });
  });

  describe('generateSimulatedRefinement', () => {
    it('modifies wording when conservative risk instruction is provided', () => {
      const original = '预计激进扩张，高增长延续。';
      const result = generateSimulatedRefinement(original, '改为保守估值并补充风险');

      expect(result).toContain('稳健增长');
      expect(result).toContain('防范准备金');
    });

    it('condenses content when brevity instruction is provided', () => {
      const original = '第一行\n第二行\n第三行\n第四行\n第五行';
      const result = generateSimulatedRefinement(original, '保持精炼简明');

      const lines = result.split('\n');
      expect(lines.length).toBeLessThanOrEqual(3);
    });

    it('bolds content when emphasis instruction is provided', () => {
      const original = '核心关键指标';
      const result = generateSimulatedRefinement(original, '重点加粗强调');

      expect(result).toBe('**核心关键指标**');
    });

    it('returns original chunk unchanged if instruction is blank', () => {
      const original = '保持不变';
      expect(generateSimulatedRefinement(original, '   ')).toBe('保持不变');
    });
  });
});
