import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import useChatStore from '@/store/useChatStore';
import { useLaneSemanticStore } from '../useLaneSemanticStore';
import { LaneGraduationPromptDialog } from '../LaneGraduationPromptDialog';

describe('LaneGraduationPromptDialog', () => {
  beforeEach(() => {
    act(() => {
      useChatStore.setState({
        actionMode: 'fast',
        sandboxMode: false,
        workspaceDir: null,
      });
      useLaneSemanticStore.setState({
        manualLaneOverride: null,
        pendingGraduation: null,
        isGraduationDialogOpen: false,
        graduationHistory: [],
      });
    });
  });

  it('renders nothing when dialog is closed', () => {
    const { container } = render(<LaneGraduationPromptDialog />);
    expect(container.firstChild).toBeNull();
  });

  it('renders dialog details when open with pending match', () => {
    act(() => {
      useLaneSemanticStore.setState({
        isGraduationDialogOpen: true,
        pendingGraduation: {
          triggerKind: 'file_write',
          matchedKeyword: '保存到',
          confidence: 0.92,
          reason: '检测到文件写入或代码保存意图',
          suggestedTargetMode: 'local_workspace',
          detectedSnippet: '请将这段内容保存到 src/App.tsx',
        },
      });
    });

    render(<LaneGraduationPromptDialog />);

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('通道即时毕业引导')).toBeInTheDocument();
    expect(screen.getByText('检测到文件写入或代码保存意图')).toBeInTheDocument();
    expect(screen.getByText('保存到')).toBeInTheDocument();
    expect(screen.getByText('请将这段内容保存到 src/App.tsx')).toBeInTheDocument();
  });

  it('handles graduation to local workspace on button click', () => {
    const onGraduated = vi.fn();
    act(() => {
      useLaneSemanticStore.setState({
        isGraduationDialogOpen: true,
        pendingGraduation: {
          triggerKind: 'file_write',
          matchedKeyword: '修改代码',
          confidence: 0.95,
          reason: '修改代码意图',
          suggestedTargetMode: 'local_workspace',
          detectedSnippet: '修改代码',
        },
      });
    });

    render(<LaneGraduationPromptDialog onGraduated={onGraduated} />);

    const localBtn = screen.getByRole('button', { name: /毕业到本地工作区/ });
    fireEvent.click(localBtn);

    expect(onGraduated).toHaveBeenCalledWith('local_workspace');
    expect(useLaneSemanticStore.getState().isGraduationDialogOpen).toBe(false);
    expect(useChatStore.getState().actionMode).toBe('agent');
    expect(useChatStore.getState().sandboxMode).toBe(false);
  });

  it('handles graduation to cloud sandbox on button click', () => {
    const onGraduated = vi.fn();
    act(() => {
      useLaneSemanticStore.setState({
        isGraduationDialogOpen: true,
        pendingGraduation: {
          triggerKind: 'dependency_install',
          matchedKeyword: '安装依赖',
          confidence: 0.9,
          reason: '依赖安装意图',
          suggestedTargetMode: 'cloud_sandbox',
          detectedSnippet: '安装依赖 axios',
        },
      });
    });

    render(<LaneGraduationPromptDialog onGraduated={onGraduated} />);

    const cloudBtn = screen.getByRole('button', { name: /毕业到云端沙箱/ });
    fireEvent.click(cloudBtn);

    expect(onGraduated).toHaveBeenCalledWith('cloud_sandbox');
    expect(useLaneSemanticStore.getState().isGraduationDialogOpen).toBe(false);
    expect(useChatStore.getState().actionMode).toBe('agent');
    expect(useChatStore.getState().sandboxMode).toBe(true);
  });

  it('handles dismiss via close button and footer button', () => {
    const onDismissed = vi.fn();
    act(() => {
      useLaneSemanticStore.setState({
        isGraduationDialogOpen: true,
      });
    });

    const { rerender } = render(<LaneGraduationPromptDialog onDismissed={onDismissed} />);

    const closeBtn = screen.getByRole('button', { name: '关闭提示' });
    fireEvent.click(closeBtn);

    expect(onDismissed).toHaveBeenCalledTimes(1);
    expect(useLaneSemanticStore.getState().isGraduationDialogOpen).toBe(false);

    // Reopen and test footer dismiss
    act(() => {
      useLaneSemanticStore.setState({
        isGraduationDialogOpen: true,
      });
    });
    rerender(<LaneGraduationPromptDialog onDismissed={onDismissed} />);

    const footerDismiss = screen.getByRole('button', { name: '仅以对话模式继续（忽略）' });
    fireEvent.click(footerDismiss);

    expect(onDismissed).toHaveBeenCalledTimes(2);
    expect(useLaneSemanticStore.getState().isGraduationDialogOpen).toBe(false);
  });
});
