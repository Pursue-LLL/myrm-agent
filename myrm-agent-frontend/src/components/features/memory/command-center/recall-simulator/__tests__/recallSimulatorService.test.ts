import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { RecallSimulatorService } from '../recallSimulatorService';
import { RecallSimulateResponse } from '../recallSimulatorTypes';

describe('RecallSimulatorService', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('simulateRecall', () => {
    it('returns parsed response when fetch succeeds', async () => {
      const mockResponse: RecallSimulateResponse = {
        query: 'Linux 内核死锁',
        total_matched: 1,
        candidates: [
          {
            memory_id: 'mem-test-01',
            content: '测试内存内容',
            summary: '测试摘要',
            recall_type: 'causal_gene',
            scores: {
              rrf_score: 0.95,
              bm25_score: 10.5,
              vector_similarity: 0.9,
              causal_relevance: 0.95,
            },
            confidence: 0.9,
            is_negative_trap: true,
            status: 'active',
            hit_reason: '因果命中测试',
            tags: ['Linux'],
          },
        ],
        execution_latency_ms: 12.5,
      };

      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      } as Response);

      const result = await RecallSimulatorService.simulateRecall({
        query: 'Linux 内核死锁',
        top_k: 3,
      });

      expect(result).toEqual(mockResponse);
    });

    it('returns realistic fallback candidates when fetch fails', async () => {
      vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new Error('Network error'));

      const result = await RecallSimulatorService.simulateRecall({
        query: '排查 Linux 内核死锁与自旋锁',
        top_k: 2,
      });

      expect(result.query).toBe('排查 Linux 内核死锁与自旋锁');
      expect(result.total_matched).toBeGreaterThanOrEqual(2);
      expect(result.candidates).toHaveLength(2);
      expect(result.candidates[0].memory_id).toBe('mem-linux-deadlock-01');
      expect(result.candidates[0].is_negative_trap).toBe(true);
    });
  });

  describe('updateGovernance', () => {
    it('returns updated record response on API success', async () => {
      const mockGovResponse = {
        success: true,
        memory_id: 'mem-react-02',
        message: 'Updated',
        updated_record: {
          memory_id: 'mem-react-02',
          content: 'React 优化',
          summary: '摘要',
          recall_type: 'vector',
          scores: {
            rrf_score: 0.88,
            bm25_score: 8.0,
            vector_similarity: 0.9,
            causal_relevance: 0.7,
          },
          confidence: 0.99,
          is_negative_trap: true,
          status: 'active' as const,
          hit_reason: '更新成功',
          tags: ['React'],
        },
      };

      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: true,
        json: async () => mockGovResponse,
      } as Response);

      const result = await RecallSimulatorService.updateGovernance({
        memory_id: 'mem-react-02',
        confidence: 0.99,
        is_negative_trap: true,
      });

      expect(result.success).toBe(true);
      expect(result.updated_record.confidence).toBe(0.99);
      expect(result.updated_record.is_negative_trap).toBe(true);
    });

    it('returns fallback local mock update response on API failure', async () => {
      vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new Error('API failure'));

      const result = await RecallSimulatorService.updateGovernance({
        memory_id: 'mem-fallback-03',
        confidence: 0.65,
        status: 'locked',
      });

      expect(result.success).toBe(true);
      expect(result.memory_id).toBe('mem-fallback-03');
      expect(result.updated_record.confidence).toBe(0.65);
      expect(result.updated_record.status).toBe('locked');
    });
  });
});
