import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { WorkflowTraceService } from '../workflowTraceService';
import { WorkflowTraceResponse } from '../workflowTraceTypes';

describe('WorkflowTraceService', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('getWorkflowTrace', () => {
    it('returns parsed trace when fetch succeeds', async () => {
      const mockTrace: WorkflowTraceResponse = {
        workflow_id: 'wf-mock-01',
        task_id: 'task-mock-01',
        title: '测试多步工作流',
        current_stage: 'closure',
        nodes: [
          {
            node_id: 'node-1',
            step_number: 1,
            title: '需求接入',
            stage: 'intake',
            status: 'completed',
            input_payload: { query: 'test' },
            output_payload: { parsed: true },
            prompt_excerpt: 'prompt test',
            tools_called: ['test_tool'],
            tokens_consumed: 150,
            validation_scores: {
              completeness: 0.95,
              accuracy: 0.95,
              compliance: 1.0,
              relevance: 0.95,
              composite_score: 0.96,
            },
            duration_ms: 200.0,
            created_at: '2026-10-13T00:00:00Z',
            identity_hash: 'hash-01',
          },
        ],
        total_tokens: 150,
        total_duration_ms: 200.0,
      };

      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: true,
        json: async () => mockTrace,
      } as Response);

      const result = await WorkflowTraceService.getWorkflowTrace('wf-mock-01');
      expect(result).toEqual(mockTrace);
    });

    it('returns realistic 5-stage fallback trace when fetch fails', async () => {
      vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new Error('Network error'));

      const result = await WorkflowTraceService.getWorkflowTrace('wf-fallback-99');
      expect(result.workflow_id).toBe('wf-fallback-99');
      expect(result.nodes).toHaveLength(5);
      expect(result.nodes[0].stage).toBe('intake');
      expect(result.nodes[4].stage).toBe('closure');
      expect(result.total_tokens).toBeGreaterThan(0);
    });
  });

  describe('replayFromNode', () => {
    it('returns replay response when API succeeds', async () => {
      const mockReplayResponse = {
        workflow_id: 'wf-mock-01',
        replayed_from_node_id: 'node-3',
        status: 'completed' as const,
        message: 'Replay completed',
        replayed_nodes: [],
      };

      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: true,
        json: async () => mockReplayResponse,
      } as Response);

      const result = await WorkflowTraceService.replayFromNode({
        workflow_id: 'wf-mock-01',
        node_id: 'node-3',
        override_inputs: { concurrency: 4 },
        steer_prompt: '提升并发',
      });

      expect(result).toEqual(mockReplayResponse);
    });

    it('returns local mock fallback response when fetch fails', async () => {
      vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new Error('Network error'));

      const result = await WorkflowTraceService.replayFromNode({
        workflow_id: 'wf-local-01',
        node_id: 'node-2',
      });

      expect(result.status).toBe('completed');
      expect(result.replayed_from_node_id).toBe('node-2');
    });
  });
});
