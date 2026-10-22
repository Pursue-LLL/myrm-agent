/**
 * RecallSimulatorService: Orchestrates communication with memory recall simulation
 * and in-place secondary governance API endpoints.
 */

import {
  MemoryGovernanceUpdateRequest,
  MemoryGovernanceUpdateResponse,
  RecallCandidate,
  RecallSimulateRequest,
  RecallSimulateResponse,
} from './recallSimulatorTypes';

export class RecallSimulatorService {
  /**
   * Simulate multi-channel memory recall and rank candidates based on input test query.
   */
  public static async simulateRecall(
    request: RecallSimulateRequest
  ): Promise<RecallSimulateResponse> {
    try {
      const res = await fetch('/api/memory/simulate-recall', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
      });

      if (!res.ok) {
        throw new Error(`Failed to simulate recall: ${res.statusText}`);
      }

      return await res.json();
    } catch {
      // Offline fallback with realistic mock candidates
      const fallbackCandidates: RecallCandidate[] = [
        {
          memory_id: 'mem-linux-deadlock-01',
          content:
            'Linux 内核模块调试中，在中断上下文 (Interrupt Context) 中严禁调用互斥锁 mutex_lock，否则必然引发睡眠调度导致内核 Panic 死锁。必须改用 spin_lock_irqsave。',
          summary: '中断上下文严禁使用 mutex，必须使用自旋锁 spin_lock_irqsave 避坑',
          recall_type: 'causal_gene',
          scores: {
            rrf_score: 0.94,
            bm25_score: 12.8,
            vector_similarity: 0.88,
            causal_relevance: 0.96,
          },
          confidence: 0.95,
          is_negative_trap: true,
          status: 'active',
          hit_reason: '命中因果避坑基因【Linux 内核死锁】与中断上下文并发规则',
          tags: ['Linux', 'Kernel', 'Deadlock', 'Pitfall'],
        },
        {
          memory_id: 'mem-react-rerender-02',
          content:
            '超大列表或复杂 Canvas 场景下，频繁 setState 导致父组件无谓重绘。使用 useMemo 缓存密集计算并在子组件采用 React.memo 配合 useCallback 维持函数引用稳定。',
          summary: 'React 密集渲染下结合 useMemo 与 React.memo 隔绝无效 Diff',
          recall_type: 'vector',
          scores: {
            rrf_score: 0.86,
            bm25_score: 9.4,
            vector_similarity: 0.91,
            causal_relevance: 0.72,
          },
          confidence: 0.85,
          is_negative_trap: false,
          status: 'active',
          hit_reason: '向量余弦相似度最高，高度匹配【前端性能优化/重绘】上下文',
          tags: ['React', 'Frontend', 'Performance', 'Optimization'],
        },
        {
          memory_id: 'mem-fastapi-concurrency-03',
          content:
            'FastAPI 在定义同步阻塞 I/O 时切忌使用 async def，否则阻塞单线程事件循环。需声明为普通 def 或 run_in_threadpool 委派。',
          summary: 'FastAPI 同步 I/O 需声明为普通 def 避免阻塞事件循环',
          recall_type: 'bm25',
          scores: {
            rrf_score: 0.79,
            bm25_score: 14.2,
            vector_similarity: 0.76,
            causal_relevance: 0.68,
          },
          confidence: 0.9,
          is_negative_trap: true,
          status: 'active',
          hit_reason: 'BM25 词法高频匹配【FastAPI / 并发 / 事件循环】关键词',
          tags: ['FastAPI', 'Python', 'Concurrency'],
        },
      ];

      return {
        query: request.query,
        total_matched: fallbackCandidates.length,
        candidates: fallbackCandidates.slice(0, request.top_k ?? 5),
        execution_latency_ms: 14.6,
      };
    }
  }

  /**
   * Update memory item secondary governance metadata (confidence, negative flag, status, merge).
   */
  public static async updateGovernance(
    request: MemoryGovernanceUpdateRequest
  ): Promise<MemoryGovernanceUpdateResponse> {
    try {
      const res = await fetch('/api/memory/simulate-recall/govern', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
      });

      if (!res.ok) {
        throw new Error(`Failed to update governance: ${res.statusText}`);
      }

      return await res.json();
    } catch {
      // Local fallback mock update response
      return {
        success: true,
        memory_id: request.memory_id,
        message: 'Local fallback governance state updated',
        updated_record: {
          memory_id: request.memory_id,
          content: '本地治理缓存记录',
          summary: '更新后的记忆经验摘要',
          recall_type: 'vector',
          scores: {
            rrf_score: 0.8,
            bm25_score: 8.0,
            vector_similarity: 0.8,
            causal_relevance: 0.7,
          },
          confidence: request.confidence ?? 0.8,
          is_negative_trap: request.is_negative_trap ?? false,
          status: request.status ?? 'active',
          hit_reason: '人工二次治理更新',
          tags: ['Governed'],
        },
      };
    }
  }
}
