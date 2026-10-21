import { describe, it, expect, vi, beforeEach } from 'vitest';
import { writebackService, type UsageLedgerRecord, type WritebackApplyRequest } from '../writeback';
import * as api from '@/lib/api';

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn(),
  getApiUrl: vi.fn((path: string) => path),
}));

describe('writebackService API client', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('records usage ledger with correct payload and scope', async () => {
    const mockRecord: UsageLedgerRecord = {
      task_id: 'task_001',
      title: '分布式事务治理',
      executed_at: '2026-09-23T10:00:00Z',
      items: [
        {
          concept_or_path: 'concepts/tcc-pattern.md',
          contribution_type: 'referenced',
          detail: '引用了 TCC 模式的最佳实践',
        },
      ],
      deliverable_paths: ['deliverables/solution.pdf'],
    };

    vi.mocked(api.apiRequest).mockResolvedValueOnce({ status: 'ok', saved_path: '/path/to/ledger.json' });

    const result = await writebackService.recordUsageLedger(mockRecord, 'agent_dev');
    expect(api.apiRequest).toHaveBeenCalledWith(
      '/wiki/writeback/ledger?agent_id=agent_dev',
      expect.objectContaining({
        method: 'POST',
      }),
    );
    expect(result.status).toBe('ok');
  });

  it('generates review slips via backend endpoint', async () => {
    const mockBatch = {
      task_id: 'task_002',
      title: '测试任务',
      generated_at: '2026-09-23T10:00:00Z',
      questions: [],
      excluded_matches_count: 3,
    };

    vi.mocked(api.apiRequest).mockResolvedValueOnce(mockBatch);

    const result = await writebackService.generateReviewSlips(
      {
        task_id: 'task_002',
        task_title: '测试任务',
        candidate_insights: [
          {
            topic: '双写平滑迁移',
            content: '四步法操作步骤',
            rationale: '通用架构重构规范',
          },
        ],
      },
      'agent_dev',
    );

    expect(api.apiRequest).toHaveBeenCalledWith(
      '/wiki/writeback/review-slips?agent_id=agent_dev',
      expect.objectContaining({
        method: 'POST',
      }),
    );
    expect(result.excluded_matches_count).toBe(3);
  });

  it('applies writeback decisions safely', async () => {
    const request: WritebackApplyRequest = {
      task_id: 'task_003',
      decisions: [
        {
          question_id: 'q_1',
          selected_option_id: 'opt_method',
          target_layer: 'methods',
          candidate_title: '双写迁移经验',
          candidate_content: '步骤...',
        },
      ],
    };

    vi.mocked(api.apiRequest).mockResolvedValueOnce({
      task_id: 'task_003',
      committed_count: 1,
      discarded_count: 0,
      created_paths: ['knowledge/methods/双写迁移经验.md'],
      message: 'Committed 1 item',
    });

    const result = await writebackService.applyWritebackDecisions(request, 'agent_dev');
    expect(result.committed_count).toBe(1);
    expect(result.created_paths).toHaveLength(1);
  });

  it('fetches layers stats', async () => {
    const mockStats = {
      agent_id: 'agent_dev',
      raw_files_count: 10,
      sources_count: 5,
      concepts_count: 12,
      claims_count: 4,
      methods_count: 3,
      templates_count: 2,
      deliverables_count: 8,
      inbox_count: 1,
    };

    vi.mocked(api.apiRequest).mockResolvedValueOnce(mockStats);

    const result = await writebackService.getLayersStats('agent_dev');
    expect(result.raw_files_count).toBe(10);
    expect(result.deliverables_count).toBe(8);
  });
});
