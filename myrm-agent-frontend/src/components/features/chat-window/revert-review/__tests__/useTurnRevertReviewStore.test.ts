import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  useTurnRevertReviewStore,
  buildSurgicalFixPrompt,
} from '../useTurnRevertReviewStore';
import type { TurnFileChange, SurgicalFixPayload } from '../revertReviewTypes';

describe('useTurnRevertReviewStore', () => {
  beforeEach(() => {
    useTurnRevertReviewStore.getState().reset();
    vi.restoreAllMocks();
  });

  it('builds surgical fix prompt correctly with formatted structure', () => {
    const payload: SurgicalFixPayload = {
      filePath: 'src/lib/utils.ts',
      lineNumber: 42,
      selectedCode: 'const x = null;',
      comment: '需要做判空校验',
      sessionId: 'sess-1',
    };
    const prompt = buildSurgicalFixPrompt(payload);
    expect(prompt).toContain('目标文件：src/lib/utils.ts（第 42 行）');
    expect(prompt).toContain('const x = null;');
    expect(prompt).toContain('审查意见：需要做判空校验');
    expect(prompt).toContain('严格保持其余无关代码不变');
  });

  it('handles setting turn changes and updating store', () => {
    const changes: TurnFileChange[] = [
      {
        path: 'src/app.ts',
        operation: 'update',
        has_original: true,
        timestamp: Date.now(),
        additions: 10,
        deletions: 2,
      },
    ];
    useTurnRevertReviewStore.getState().setTurnChanges('msg-101', changes);
    expect(useTurnRevertReviewStore.getState().turnChanges['msg-101']).toEqual(changes);
  });

  it('adds and removes inline comments correctly', () => {
    const comment = useTurnRevertReviewStore.getState().addComment({
      filePath: 'src/index.ts',
      lineNumber: 15,
      lineType: 'addition',
      selectedCode: 'foo()',
      comment: '重命名为 bar()',
    });

    expect(comment.id).toBeDefined();
    expect(useTurnRevertReviewStore.getState().comments).toHaveLength(1);
    expect(useTurnRevertReviewStore.getState().comments[0].comment).toBe('重命名为 bar()');

    useTurnRevertReviewStore.getState().removeComment(comment.id);
    expect(useTurnRevertReviewStore.getState().comments).toHaveLength(0);
  });

  it('manages openDiff and closeDiff lifecycle', () => {
    useTurnRevertReviewStore.getState().openDiff('sess-99', 'msg-99');
    expect(useTurnRevertReviewStore.getState().activeDiffTarget).toEqual({
      sessionId: 'sess-99',
      messageId: 'msg-99',
    });

    useTurnRevertReviewStore.getState().closeDiff();
    expect(useTurnRevertReviewStore.getState().activeDiffTarget).toBeNull();
  });

  it('executes revertTurn successfully when API responds 200', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        reverted_files: ['src/app.ts'],
        warnings: [],
        skipped_files: [],
      }),
    });

    const success = await useTurnRevertReviewStore.getState().revertTurn('sess-1', 'msg-1');
    expect(success).toBe(true);
    const state = useTurnRevertReviewStore.getState().revertStates['msg-1'];
    expect(state.status).toBe('success');
    expect(state.revertedFiles).toEqual(['src/app.ts']);
  });

  it('handles revertTurn network failure gracefully', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('Network error'));

    const success = await useTurnRevertReviewStore.getState().revertTurn('sess-1', 'msg-1');
    expect(success).toBe(false);
    const state = useTurnRevertReviewStore.getState().revertStates['msg-1'];
    expect(state.status).toBe('error');
    expect(state.errorMessage).toBe('Network error');
  });
});
