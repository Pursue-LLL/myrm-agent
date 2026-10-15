import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { ArtifactForkDiffStudio } from '../ArtifactForkDiffStudio';
import { useMultiRoleRelayStore } from '../useMultiRoleRelayStore';

describe('ArtifactForkDiffStudio component', () => {
  beforeEach(() => {
    act(() => {
      useMultiRoleRelayStore.getState().resetState();
    });
  });

  it('renders null when diff studio is not open', () => {
    const { container } = render(<ArtifactForkDiffStudio />);
    expect(container.firstChild).toBeNull();
  });

  it('renders diff modal with diff view and baseline version info when open', () => {
    act(() => {
      useMultiRoleRelayStore.getState().openDiffStudio();
    });

    render(<ArtifactForkDiffStudio />);

    expect(
      screen.getByTestId('artifact-fork-diff-studio')
    ).toBeInTheDocument();
    expect(
      screen.getByText('中间产物分支修改与双向对比工作室')
    ).toBeInTheDocument();
    expect(screen.getByText('基准版本: v1.0')).toBeInTheDocument();
    expect(screen.getByText('差量比对 (Diff View)')).toBeInTheDocument();
    expect(screen.getByText('源码编辑 (Editor)')).toBeInTheDocument();
  });

  it('switches to editor tab and edits modified content', () => {
    act(() => {
      useMultiRoleRelayStore.getState().openDiffStudio();
    });

    render(<ArtifactForkDiffStudio />);

    const editorTabBtn = screen.getByText('源码编辑 (Editor)');
    fireEvent.click(editorTabBtn);

    const textarea = screen.getByLabelText('分支修改后内容');
    expect(textarea).toBeInTheDocument();

    fireEvent.change(textarea, {
      target: { value: '{\n  "VendorA": { "price": "$39/mo" }\n}' },
    });

    // Switch back to diff tab
    const diffTabBtn = screen.getByText('差量比对 (Diff View)');
    fireEvent.click(diffTabBtn);

    expect(screen.getAllByText('+').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/"price": "\$39\/mo"/)).toBeInTheDocument();
  });

  it('submits fork branch and updates target stage snapshot version', () => {
    act(() => {
      useMultiRoleRelayStore.getState().openDiffStudio();
    });

    render(<ArtifactForkDiffStudio />);

    const branchInput = screen.getByLabelText('分支标识名称');
    fireEvent.change(branchInput, {
      target: { value: 'custom-pricing-fork' },
    });

    const noteInput = screen.getByLabelText(
      '修改原因与下流指示 (User Note)'
    );
    fireEvent.change(noteInput, {
      target: { value: '调整价格模型' },
    });

    const submitBtn = screen.getByRole('button', {
      name: '提交分支并推向下游 Agent',
    });
    act(() => {
      fireEvent.click(submitBtn);
    });

    expect(useMultiRoleRelayStore.getState().isDiffStudioOpen).toBe(false);
    expect(useMultiRoleRelayStore.getState().forkHistory.length).toBe(1);
    expect(
      useMultiRoleRelayStore.getState().forkHistory[0].branchName
    ).toBe('custom-pricing-fork');

    const researcherStage = useMultiRoleRelayStore
      .getState()
      .stages.find((s) => s.id === 'stage-researcher');
    expect(researcherStage?.snapshot?.version).toBe(2);
  });

  it('closes studio without saving when close button is clicked', () => {
    act(() => {
      useMultiRoleRelayStore.getState().openDiffStudio();
    });

    render(<ArtifactForkDiffStudio />);

    const closeBtn = screen.getByRole('button', {
      name: '关闭分支修改工作台',
    });
    act(() => {
      fireEvent.click(closeBtn);
    });

    expect(useMultiRoleRelayStore.getState().isDiffStudioOpen).toBe(false);
  });
});
