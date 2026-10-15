import { describe, it, expect } from 'vitest';
import type {
  FinalCardStatus,
  FinalCardActionOption,
  FinalCardArtifact,
  FinalCardPresentationContract,
  FinalCardStoreState,
} from '../finalCardTypes';

describe('finalCardTypes', () => {
  it('should validate type contract assignments correctly', () => {
    const status: FinalCardStatus = 'completed';
    expect(status).toBe('completed');

    const actionOption: FinalCardActionOption = {
      id: 'opt-1',
      label: '运行测试',
      actionKind: 'run_tests',
      payload: 'pnpm test',
      isPrimary: true,
    };
    expect(actionOption.id).toBe('opt-1');
    expect(actionOption.actionKind).toBe('run_tests');
    expect(actionOption.isPrimary).toBe(true);

    const artifact: FinalCardArtifact = {
      id: 'art-1',
      name: 'index.ts',
      type: 'code',
      path: '/src/index.ts',
      sizeBytes: 1024,
      previewable: true,
    };
    expect(artifact.type).toBe('code');
    expect(artifact.sizeBytes).toBe(1024);

    const contract: FinalCardPresentationContract = {
      id: 'card-1',
      turnId: 'turn-1',
      status: 'completed',
      title: '任务已完成',
      summary: '全部模块已编译通过',
      keyDecisions: ['采用 Zustand 状态总线', '解耦主消息流与日志流'],
      artifacts: [artifact],
      actionOptions: [actionOption],
      executionDurationMs: 1500,
      tokensUsed: {
        prompt: 120,
        completion: 300,
        total: 420,
      },
      transcriptUrl: '/api/transcripts/turn-1',
      rawLogLinesCount: 45,
      rawLogsPreview: ['[Step 1] Initializing', '[Step 2] Complete'],
      timestamp: 1760000000000,
    };

    expect(contract.turnId).toBe('turn-1');
    expect(contract.status).toBe('completed');
    expect(contract.keyDecisions.length).toBe(2);
    expect(contract.tokensUsed?.total).toBe(420);

    const storeState: FinalCardStoreState = {
      cards: {
        'card-1': contract,
      },
      activeTranscriptCardId: 'card-1',
    };

    expect(storeState.activeTranscriptCardId).toBe('card-1');
    expect(storeState.cards['card-1'].title).toBe('任务已完成');
  });
});
