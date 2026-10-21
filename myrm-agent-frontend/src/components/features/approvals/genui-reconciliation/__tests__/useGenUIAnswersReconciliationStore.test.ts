import { describe, expect, it, beforeEach } from 'vitest';
import { useGenUIAnswersReconciliationStore } from '../useGenUIAnswersReconciliationStore';

describe('useGenUIAnswersReconciliationStore', () => {
  beforeEach(() => {
    useGenUIAnswersReconciliationStore.getState().resetForm();
  });

  it('应该在更新字段时将其标记为 dirty 并更新 answers 状态', () => {
    const store = useGenUIAnswersReconciliationStore.getState();
    expect(store.dirtyFields.cluster_name).toBeUndefined();

    store.updateFieldValue('cluster_name', 'my-custom-cluster');

    const updated = useGenUIAnswersReconciliationStore.getState();
    expect(updated.answers.cluster_name).toBe('my-custom-cluster');
    expect(updated.dirtyFields.cluster_name).toBe(true);
    expect(updated.isSubmitted).toBe(false);
  });

  it('在执行 simulateAgentSpecRefresh 时，用户已改动的字段不应被覆盖，并能成功追加新规格参数', () => {
    const store = useGenUIAnswersReconciliationStore.getState();
    // 用户编辑 cluster_name
    store.updateFieldValue('cluster_name', 'user-preserved-cluster-name');

    // 触发 Agent 演进
    const outcome = store.simulateAgentSpecRefresh();

    const evolved = useGenUIAnswersReconciliationStore.getState();
    expect(evolved.currentSpec.version).toBe(2);
    expect(evolved.answers.cluster_name).toBe('user-preserved-cluster-name');
    expect(outcome.preservedUserFieldsCount).toBe(1);

    // 验证新注入的字段
    expect(evolved.answers.risk_mitigation_window_2).toBe(15);
    expect(evolved.answers.notify_oncall_lead_2).toBe(true);
  });

  it('能够成功提交表单并设置 isSubmitted 状态', () => {
    const store = useGenUIAnswersReconciliationStore.getState();
    expect(store.isSubmitted).toBe(false);

    const answers = store.submitForm();
    expect(answers.cluster_name).toBe('k8s-edge-shanghai-01');
    expect(useGenUIAnswersReconciliationStore.getState().isSubmitted).toBe(true);
  });

  it('执行 resetForm 时清空脏标记并恢复初始 Spec 默认值', () => {
    const store = useGenUIAnswersReconciliationStore.getState();
    store.updateFieldValue('cluster_name', 'temporary-name');
    expect(useGenUIAnswersReconciliationStore.getState().dirtyFields.cluster_name).toBe(true);

    store.resetForm();

    const resetState = useGenUIAnswersReconciliationStore.getState();
    expect(resetState.dirtyFields).toEqual({});
    expect(resetState.isSubmitted).toBe(false);
    expect(resetState.lastReconciliation).toBeNull();
  });
});
