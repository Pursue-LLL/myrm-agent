import { describe, it, expect, beforeEach } from 'vitest';
import { useClarificationQuestionnaireStore } from '../useClarificationQuestionnaireStore';

describe('useClarificationQuestionnaireStore', () => {
  beforeEach(() => {
    useClarificationQuestionnaireStore.getState().reset();
  });

  it('初始状态合规并加载默认题目', () => {
    const state = useClarificationQuestionnaireStore.getState();
    expect(state.status).toBe('draft');
    expect(state.questions.length).toBe(4);
    expect(state.currentQuestionIndex).toBe(0);
    expect(state.isSpecModalOpen).toBe(false);
    expect(state.activeSpecContract).toBeNull();
  });

  it('支持单选题和多选题的选项切换与反选', () => {
    const store = useClarificationQuestionnaireStore.getState();

    // 单选题：q-shape，切换到 opt-cli
    store.selectOption('q-shape', 'opt-cli');
    const qShape = useClarificationQuestionnaireStore
      .getState()
      .questions.find((q) => q.id === 'q-shape');
    expect(qShape?.selectedOptionIds).toEqual(['opt-cli']);

    // 多选题：q-non-goals，初始有 opt-exclude-auth 与 opt-exclude-pdf
    const qNonGoalsBefore = useClarificationQuestionnaireStore
      .getState()
      .questions.find((q) => q.id === 'q-non-goals');
    expect(qNonGoalsBefore?.selectedOptionIds).toContain('opt-exclude-auth');

    // 反选 opt-exclude-auth
    store.selectOption('q-non-goals', 'opt-exclude-auth');
    const qNonGoalsAfter = useClarificationQuestionnaireStore
      .getState()
      .questions.find((q) => q.id === 'q-non-goals');
    expect(qNonGoalsAfter?.selectedOptionIds).not.toContain('opt-exclude-auth');
    expect(qNonGoalsAfter?.selectedOptionIds).toContain('opt-exclude-pdf');
  });

  it('支持补充自定义文本与附件的增删改查', () => {
    const store = useClarificationQuestionnaireStore.getState();
    store.updateCustomText('q-shape', '需要支持 Electron 桌面壳打包');

    const qShape = useClarificationQuestionnaireStore
      .getState()
      .questions.find((q) => q.id === 'q-shape');
    expect(qShape?.customTextAnswer).toBe('需要支持 Electron 桌面壳打包');

    // 添加附件
    const attachmentId = 'att-test-1';
    store.addAttachment('q-shape', {
      id: attachmentId,
      name: 'architecture_diagram.png',
      size: 1024,
      type: 'image/png',
      uploadStatus: 'uploading',
    });

    let att = useClarificationQuestionnaireStore
      .getState()
      .questions.find((q) => q.id === 'q-shape')
      ?.attachments.find((a) => a.id === attachmentId);
    expect(att?.uploadStatus).toBe('uploading');

    // 更新附件状态
    store.updateAttachmentStatus('q-shape', attachmentId, 'ready', 'https://example.com/pic.png');
    att = useClarificationQuestionnaireStore
      .getState()
      .questions.find((q) => q.id === 'q-shape')
      ?.attachments.find((a) => a.id === attachmentId);
    expect(att?.uploadStatus).toBe('ready');
    expect(att?.url).toBe('https://example.com/pic.png');

    // 移除附件
    store.removeAttachment('q-shape', attachmentId);
    const attList = useClarificationQuestionnaireStore
      .getState()
      .questions.find((q) => q.id === 'q-shape')?.attachments;
    expect(attList?.length).toBe(0);
  });

  it('一键应用全部推荐项', () => {
    const store = useClarificationQuestionnaireStore.getState();
    // 先清空
    store.setQuestions(
      store.questions.map((q) => ({ ...q, selectedOptionIds: [] }))
    );

    store.applyAllRecommendations();
    const questions = useClarificationQuestionnaireStore.getState().questions;
    for (const q of questions) {
      expect(q.selectedOptionIds.length).toBeGreaterThan(0);
    }
  });

  it('支持聚合生成 V1 Spec 并在提交后更新状态', () => {
    const store = useClarificationQuestionnaireStore.getState();
    const spec = store.synthesizeAndPreviewSpec();

    expect(useClarificationQuestionnaireStore.getState().isSpecModalOpen).toBe(true);
    expect(spec.productShape).toBeDefined();

    const submittedSpec = store.submitQuestionnaire();
    const state = useClarificationQuestionnaireStore.getState();
    expect(state.status).toBe('submitted');
    expect(state.isSpecModalOpen).toBe(false);
    expect(state.lastSubmittedTime).toBeGreaterThan(0);
    expect(submittedSpec.productShape).toBe(spec.productShape);
  });
});
