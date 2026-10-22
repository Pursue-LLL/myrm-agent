import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ClarificationGateDrawer } from '../ClarificationGateDrawer';
import { useClarificationGateStore } from '../useClarificationGateStore';
import type { GoalSpec } from '../clarificationGateTypes';

describe('ClarificationGateDrawer', () => {
  beforeEach(() => {
    useClarificationGateStore.getState().resetState();
  });

  it('renders nothing when isOpen is false', () => {
    const { container } = render(<ClarificationGateDrawer />);
    expect(container.firstChild).toBeNull();
  });

  it('renders dialog and question groups when opened', () => {
    useClarificationGateStore.getState().openGate('做一个宣传落地页', 'button');
    render(<ClarificationGateDrawer />);

    const dialog = screen.getByRole('dialog', { name: '苏格拉底式需求澄清门禁抽屉' });
    expect(dialog).toBeInTheDocument();

    expect(screen.getByText('目标运行环境与平台')).toBeInTheDocument();
    expect(screen.getByText('期望交付产物深度')).toBeInTheDocument();
    expect(screen.getByText('架构风格与工程约束')).toBeInTheDocument();
    expect(screen.getByText(/做一个宣传落地页/)).toBeInTheDocument();
  });

  it('toggles option capsule selection', () => {
    useClarificationGateStore.getState().openGate('构建跨平台桌面端', 'command');
    render(<ClarificationGateDrawer />);

    const desktopOption = screen.getByRole('button', { name: /Tauri \/ 跨平台桌面客户端/ });
    expect(desktopOption).toHaveAttribute('aria-pressed', 'false');

    fireEvent.click(desktopOption);
    expect(desktopOption).toHaveAttribute('aria-pressed', 'true');
  });

  it('triggers onConfirmSpec when skipping clarification', () => {
    const handleConfirm = vi.fn();
    useClarificationGateStore.getState().openGate('写个抓取脚本', 'auto');
    render(<ClarificationGateDrawer onConfirmSpec={handleConfirm} />);

    const skipBtn = screen.getByRole('button', { name: /跳过提问，按推荐默认启动/ });
    fireEvent.click(skipBtn);

    expect(handleConfirm).toHaveBeenCalledTimes(1);
    const spec = handleConfirm.mock.calls[0]?.[0] as GoalSpec;
    expect(spec.isSkippedByUser).toBe(true);
    expect(useClarificationGateStore.getState().isOpen).toBe(false);
  });

  it('compiles Goal Spec and triggers onConfirmSpec upon confirm', () => {
    const handleConfirm = vi.fn();
    useClarificationGateStore.getState().openGate('做个离线记事本', 'button');
    render(<ClarificationGateDrawer onConfirmSpec={handleConfirm} />);

    const notesInput = screen.getByLabelText('其他自定义约束或业务背景补充（可选）');
    fireEvent.change(notesInput, { target: { value: '必须支持 SQLite 本地持久化' } });

    const confirmBtn = screen.getByRole('button', { name: '提炼无歧义 Goal Spec 并启动' });
    fireEvent.click(confirmBtn);

    expect(handleConfirm).toHaveBeenCalledTimes(1);
    const spec = handleConfirm.mock.calls[0]?.[0] as GoalSpec;
    expect(spec.isSkippedByUser).toBe(false);
    expect(spec.constraints.some((c) => c.includes('SQLite 本地持久化'))).toBe(true);
    expect(useClarificationGateStore.getState().isOpen).toBe(false);
  });
});
