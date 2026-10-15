import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useClarificationQuestionnaireStore } from '../useClarificationQuestionnaireStore';
import { isQuestionnaireReadyToSubmit } from '../clarificationQuestionnaireEngine';

describe('clarificationQuestionnaireIntegration', () => {
  beforeEach(() => {
    useClarificationQuestionnaireStore.getState().reset();
  });

  it('全链路：问卷加载 -> 逐题决策 -> 补充附件 -> 契约锁定与目标同步闭环', () => {
    const store = useClarificationQuestionnaireStore.getState();

    // 1. 验证初始状态
    expect(store.status).toBe('draft');
    expect(store.questions.length).toBe(4);

    // 2. 模拟用户决策：第1题选 CLI 工具
    store.selectOption('q-shape', 'opt-cli');
    // 第2题选 MVP 计算
    store.selectOption('q-complexity', 'opt-mvp-calc');
    // 第3题选本地存储
    store.selectOption('q-storage', 'opt-local-storage');
    // 第4题多选追加排除项：排除多语言
    store.selectOption('q-non-goals', 'opt-exclude-i18n');

    // 3. 补充说明与上传附件 (T3 Code 对标)
    store.updateCustomText('q-complexity', '公式按照：基础价 * 材质系数 计算');
    store.addAttachment('q-complexity', {
      id: 'att-integration-1',
      name: 'formula_spec.csv',
      size: 2048,
      type: 'text/csv',
      uploadStatus: 'ready',
    });

    // 4. 验证就绪状态校验
    const readyResult = isQuestionnaireReadyToSubmit(
      useClarificationQuestionnaireStore.getState().questions
    );
    expect(readyResult.isReady).toBe(true);

    // 5. 预览克制 V1 契约 (Spec Synthesizer)
    const spec = store.synthesizeAndPreviewSpec();
    expect(spec.productShape).toBe('轻量命令行 CLI 工具');
    expect(spec.coreCapabilities).toContain('补充细节: 公式按照：基础价 * 材质系数 计算');
    expect(spec.coreCapabilities.some((c) => c.includes('formula_spec.csv'))).toBe(true);
    expect(spec.nonGoals).toContain('不建多语言本地化资源包');
    expect(useClarificationQuestionnaireStore.getState().isSpecModalOpen).toBe(true);

    // 6. 最终锁定提交
    const onSubmitCallback = vi.fn();
    const finalContract = store.submitQuestionnaire();
    onSubmitCallback(finalContract);

    expect(onSubmitCallback).toHaveBeenCalledWith(finalContract);
    const finalState = useClarificationQuestionnaireStore.getState();
    expect(finalState.status).toBe('submitted');
    expect(finalState.isSpecModalOpen).toBe(false);
    expect(finalState.lastSubmittedTime).toBeGreaterThan(0);
  });
});
