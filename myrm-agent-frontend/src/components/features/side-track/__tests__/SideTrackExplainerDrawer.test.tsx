import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SideTrackExplainerDrawer } from '../SideTrackExplainerDrawer';
import { useSideTrackStore } from '../useSideTrackStore';
import { ReadOnlyCodeSnapshot, ReadOnlyStepSnapshot } from '../sideTrackTypes';

describe('SideTrackExplainerDrawer', () => {
  const mockStep: ReadOnlyStepSnapshot = {
    stepId: 'step-01',
    stepTitle: 'AST 并发解析与符号表构建',
    toolAction: 'ast_parse_symbols',
  };

  const mockCode: ReadOnlyCodeSnapshot = {
    filePath: 'src/core/parser.ts',
    codeSnippet: 'export function parseAST() { return true; }',
    language: 'typescript',
  };

  beforeEach(() => {
    useSideTrackStore.getState().clearSession();
  });

  it('renders nothing when closed or no active session', () => {
    const { container } = render(<SideTrackExplainerDrawer />);
    expect(container.firstChild).toBeNull();
  });

  it('renders drawer header, zero-pollution banner, and system message when open', () => {
    useSideTrackStore
      .getState()
      .openSideTrack('main-sess-123456', '自动化构建全栈工作台', mockStep, [
        mockCode,
      ]);

    render(<SideTrackExplainerDrawer />);

    expect(screen.getByTestId('side-track-explainer-drawer')).toBeInTheDocument();
    expect(screen.getByText('侧边独立解释分支')).toBeInTheDocument();
    expect(screen.getByText('只读快照')).toBeInTheDocument();
    expect(screen.getByText('源自主任务: 自动化构建全栈工作台')).toBeInTheDocument();
    expect(
      screen.getByText('主 Agent 全速执行中 · 零上下文污染')
    ).toBeInTheDocument();
    expect(screen.getByText('AST 并发解析与符号表构建')).toBeInTheDocument();
  });

  it('handles closing the drawer when close button is clicked', () => {
    useSideTrackStore
      .getState()
      .openSideTrack('main-sess-123456', '自动化构建全栈工作台', mockStep);

    render(<SideTrackExplainerDrawer />);
    const closeBtn = screen.getByRole('button', { name: '关闭侧边解释抽屉' });
    fireEvent.click(closeBtn);

    expect(useSideTrackStore.getState().isDrawerOpen).toBe(false);
  });

  it('toggles code preview and inspects code snippet', () => {
    useSideTrackStore
      .getState()
      .openSideTrack('main-sess-123456', '自动化构建全栈工作台', mockStep, [
        mockCode,
      ]);

    render(<SideTrackExplainerDrawer />);
    expect(screen.getByText('挂载代码快照 (1)')).toBeInTheDocument();
    expect(screen.getByText('parser.ts')).toBeInTheDocument();

    const togglePreviewBtn = screen.getByText('展开代码预览');
    fireEvent.click(togglePreviewBtn);

    expect(screen.getByText('折叠代码预览')).toBeInTheDocument();
    expect(
      screen.getByText('export function parseAST() { return true; }')
    ).toBeInTheDocument();
  });

  it('submits inquiry via input form and renders assistant explanation', () => {
    useSideTrackStore
      .getState()
      .openSideTrack('main-sess-123456', '自动化构建全栈工作台', mockStep);

    render(<SideTrackExplainerDrawer />);

    const input = screen.getByPlaceholderText(
      '询问当前步骤设计原理、架构决策或代码实现...'
    );
    fireEvent.change(input, {
      target: { value: '请解释当前架构设计的模块分层与单一职责' },
    });

    const sendBtn = screen.getByRole('button', { name: '发送提问' });
    fireEvent.click(sendBtn);

    expect(
      screen.getByText('请解释当前架构设计的模块分层与单一职责')
    ).toBeInTheDocument();
    expect(screen.getByText(/只读架构师分析/)).toBeInTheDocument();
  });

  it('handles clicking recommended preset inquiry chips', () => {
    useSideTrackStore
      .getState()
      .openSideTrack('main-sess-123456', '自动化构建全栈工作台', mockStep, [
        mockCode,
      ]);

    render(<SideTrackExplainerDrawer />);

    const chips = screen.getAllByRole('button', {
      name: /解释当前执行动作/i,
    });
    expect(chips.length).toBeGreaterThan(0);

    fireEvent.click(chips[0]);
    expect(screen.getByText(/只读架构师分析/)).toBeInTheDocument();
  });
});
