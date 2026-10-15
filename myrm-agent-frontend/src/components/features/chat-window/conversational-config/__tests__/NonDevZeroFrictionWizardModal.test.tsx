import { fireEvent, render, screen } from '@testing-library/react';
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { NonDevZeroFrictionWizardModal } from '../NonDevZeroFrictionWizardModal';
import { useConversationalConfigStore } from '../useConversationalConfigStore';

describe('NonDevZeroFrictionWizardModal', () => {
  beforeEach(() => {
    useConversationalConfigStore.getState().reset();
  });

  it('renders nothing when isNonDevWizardOpen is false', () => {
    const { container } = render(<NonDevZeroFrictionWizardModal />);
    expect(container.firstChild).toBeNull();
  });

  it('renders modal and steps when open', () => {
    useConversationalConfigStore.getState().toggleNonDevWizard(true);
    render(<NonDevZeroFrictionWizardModal />);

    expect(screen.getByTestId('non-dev-wizard-modal')).toBeDefined();
    expect(screen.getByText('开启您的 Myrm AI 协同体验')).toBeDefined();
    expect(screen.getByText('第 1 步: 选择您的核心工作场景')).toBeDefined();
    expect(screen.getByText('通用办公与研报发票')).toBeDefined();
  });

  it('allows selecting options and navigating steps', () => {
    useConversationalConfigStore.getState().toggleNonDevWizard(true);
    const onCompleted = vi.fn();
    render(<NonDevZeroFrictionWizardModal onCompleted={onCompleted} />);

    // 选择极客研发
    fireEvent.click(screen.getByText('极客研发与代码工程'));

    // 下一步 -> 步骤 2
    fireEvent.click(screen.getByText('下一步'));
    expect(screen.getByText('第 2 步: 选择首选大模型接入方式')).toBeDefined();

    // 在第 2 步点击上一步 -> 步骤 1
    fireEvent.click(screen.getByText('上一步'));
    expect(screen.getByText('第 1 步: 选择您的核心工作场景')).toBeDefined();

    // 再次下一步 -> 步骤 2
    fireEvent.click(screen.getByText('下一步'));
    // 步骤 2 点下一步 -> 步骤 3
    fireEvent.click(screen.getByText('下一步'));
    expect(screen.getByText('第 3 步: 准备就绪，开启首个任务')).toBeDefined();

    // 点击完成
    const finishButton = screen.getByText('完成并立即开启');
    fireEvent.click(finishButton);

    expect(onCompleted).toHaveBeenCalledTimes(1);
    expect(useConversationalConfigStore.getState().isNonDevWizardOpen).toBe(
      false,
    );
  });

  it('closes modal when close button is clicked', () => {
    useConversationalConfigStore.getState().toggleNonDevWizard(true);
    render(<NonDevZeroFrictionWizardModal />);

    const closeBtn = screen.getByLabelText('关闭入驻向导');
    fireEvent.click(closeBtn);

    expect(useConversationalConfigStore.getState().isNonDevWizardOpen).toBe(
      false,
    );
  });

  it('closes modal when Escape key is pressed', () => {
    useConversationalConfigStore.getState().toggleNonDevWizard(true);
    render(<NonDevZeroFrictionWizardModal />);

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(useConversationalConfigStore.getState().isNonDevWizardOpen).toBe(
      false,
    );
  });
});
