import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import { ReconciledDynamicFormCard } from '../ReconciledDynamicFormCard';
import { useGenUIAnswersReconciliationStore } from '../useGenUIAnswersReconciliationStore';

describe('ReconciledDynamicFormCard', () => {
  beforeEach(() => {
    act(() => {
      useGenUIAnswersReconciliationStore.getState().resetForm();
    });
  });

  it('渲染表单标题、默认 Spec 版本与所有初始表单项', () => {
    render(<ReconciledDynamicFormCard />);

    expect(screen.getByText('生产级无损金丝雀灰度发布审批')).toBeInTheDocument();
    expect(screen.getByText('GenUI Spec v1')).toBeInTheDocument();
    expect(screen.getByText('调和守卫保护中')).toBeInTheDocument();
    expect(screen.getByLabelText(/目标集群名称/)).toHaveValue('k8s-edge-shanghai-01');
    expect(screen.getByLabelText(/初始 Pod 副本数量/)).toHaveValue(3);
  });

  it('用户修改字段后显示调和豁免徽标，演进新 Spec 时用户输入不受影响', () => {
    render(<ReconciledDynamicFormCard />);

    const clusterInput = screen.getByLabelText(/目标集群名称/);
    act(() => {
      fireEvent.change(clusterInput, { target: { value: 'my-custom-prod-cluster' } });
    });

    expect(screen.getByText('用户已改动 (调和豁免)')).toBeInTheDocument();
    expect(clusterInput).toHaveValue('my-custom-prod-cluster');

    // 点击模拟刷新演进
    const evolveBtn = screen.getByRole('button', { name: /模拟 Agent 演进新规格/ });
    act(() => {
      fireEvent.click(evolveBtn);
    });

    // 检查版本更新并展示调和完成通知条
    expect(screen.getByText('GenUI Spec v2')).toBeInTheDocument();
    expect(screen.getByText(/已完成状态调和/)).toBeInTheDocument();
    // 用户自定义的值仍然完好无损！
    expect(screen.getByLabelText(/目标集群名称/)).toHaveValue('my-custom-prod-cluster');
    // 新增字段已成功追加
    expect(screen.getByLabelText(/安全观测静默窗口/)).toBeInTheDocument();
  });

  it('能够成功提交表单并展示持久化流水提示', () => {
    render(<ReconciledDynamicFormCard />);

    const submitBtn = screen.getByRole('button', { name: /确认并提交审批/ });
    act(() => {
      fireEvent.click(submitBtn);
    });

    expect(screen.getByText('参数已安全提交并生成不可篡改审批流水。')).toBeInTheDocument();
  });

  it('点击恢复默认按钮能够清空脏标记并重置输入', () => {
    render(<ReconciledDynamicFormCard />);

    const clusterInput = screen.getByLabelText(/目标集群名称/);
    act(() => {
      fireEvent.change(clusterInput, { target: { value: 'some-temp-value' } });
    });
    expect(screen.getByText('用户已改动 (调和豁免)')).toBeInTheDocument();

    const resetBtn = screen.getByRole('button', { name: /恢复默认/ });
    act(() => {
      fireEvent.click(resetBtn);
    });

    expect(screen.queryByText('用户已改动 (调和豁免)')).toBeNull();
    expect(clusterInput).toHaveValue('k8s-edge-shanghai-01');
  });
});
