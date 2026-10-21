import { describe, expect, it } from 'vitest';
import {
  enrichModelJudgmentsWithAuthoritativeFacts,
  sanitizeNoteCurrencyAndTemporalConflict,
} from '../uiEnrichmentEngine';
import {
  AuthoritativeFactRecord,
  ModelJudgmentInput,
} from '../uiEnrichmentTypes';

describe('uiEnrichmentEngine', () => {
  const mockFactStore: Record<string, AuthoritativeFactRecord> = {
    'prod-server-1': {
      id: 'prod-server-1',
      officialTitle: '企业级大模型推理专机',
      officialPrice: 29999,
      officialCurrency: 'CNY',
      stockStatus: 'in_stock',
      verifiedWeekday: '周四',
      effectiveDate: '2026-10-15',
    },
    'prod-server-2': {
      id: 'prod-server-2',
      officialTitle: '全球云漫游算力包',
      officialPrice: 99,
      officialCurrency: 'USD',
      stockStatus: 'in_stock',
      verifiedWeekday: '周一',
    },
  };

  describe('sanitizeNoteCurrencyAndTemporalConflict', () => {
    it('corrects currency mismatch when fact is CNY and model says USD', () => {
      const fact = mockFactStore['prod-server-1'];
      expect(fact).toBeDefined();
      if (!fact) {
        return;
      }

      const note = '特惠售价仅需 $29999，性价比极高';
      const result = sanitizeNoteCurrencyAndTemporalConflict(note, fact);

      expect(result.currencyModified).toBe(true);
      expect(result.sanitizedNote).toContain('¥29999');
    });

    it('corrects temporal weekday mismatch when fact is verifiedWeekday', () => {
      const fact = mockFactStore['prod-server-1'];
      expect(fact).toBeDefined();
      if (!fact) {
        return;
      }

      const note = '本周五生效折扣优惠';
      const result = sanitizeNoteCurrencyAndTemporalConflict(note, fact);

      expect(result.temporalModified).toBe(true);
      expect(result.sanitizedNote).toBe('本周四生效折扣优惠');
    });

    it('retains text unchanged when no currency or weekday conflict', () => {
      const fact = mockFactStore['prod-server-1'];
      expect(fact).toBeDefined();
      if (!fact) {
        return;
      }

      const note = '性能优异，推荐采购';
      const result = sanitizeNoteCurrencyAndTemporalConflict(note, fact);

      expect(result.currencyModified).toBe(false);
      expect(result.temporalModified).toBe(false);
      expect(result.sanitizedNote).toBe(note);
    });
  });

  describe('enrichModelJudgmentsWithAuthoritativeFacts', () => {
    it('joins authoritative facts and drops unknown ids with provenance warning', () => {
      const judgments: ModelJudgmentInput[] = [
        {
          id: 'prod-server-1',
          userNote: '只要 $29999 就能拿下',
          comparisonHighlight: '首选高并发推理',
        },
        {
          id: 'unknown-fake-id-999',
          userNote: '模型瞎编的低价商品',
        },
        {
          id: 'prod-server-2',
          userNote: '只要 ¥99 极速漫游',
        },
      ];

      const res = enrichModelJudgmentsWithAuthoritativeFacts(
        judgments,
        mockFactStore,
        'custom-pres-id',
      );

      expect(res.presentationId).toBe('custom-pres-id');
      expect(res.items).toHaveLength(2); // 2 个真实 ID，1 个虚假 ID 被拦截丢弃

      // 验证第 1 项
      const first = res.items[0];
      expect(first).toBeDefined();
      expect(first?.id).toBe('prod-server-1');
      expect(first?.officialTitle).toBe('企业级大模型推理专机');
      expect(first?.officialPrice).toBe(29999);
      expect(first?.officialCurrency).toBe('CNY');
      expect(first?.sanitizedNote).toContain('¥29999');
      expect(first?.rank).toBe(1);

      // 验证第 2 项（原第 3 项）
      const second = res.items[1];
      expect(second).toBeDefined();
      expect(second?.id).toBe('prod-server-2');
      expect(second?.sanitizedNote).toContain('$99');
      expect(second?.rank).toBe(2);

      // 验证审计日志中的拦截记录
      expect(res.auditLog.droppedUnknownIds).toContain('unknown-fake-id-999');
      expect(res.auditLog.currencyFixedCount).toBe(2);
      expect(res.auditLog.auditNotes.some((n) => n.includes('[溯源拦截]'))).toBe(
        true,
      );
    });
  });
});
