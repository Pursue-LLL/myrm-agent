import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { UnifiedMultiTabWorkbench } from '../UnifiedMultiTabWorkbench';
import { useWorkbenchStore } from '../useWorkbenchStore';

describe('UnifiedMultiTabWorkbench component', () => {
  beforeEach(() => {
    act(() => {
      useWorkbenchStore.getState().resetState();
    });
  });

  it('renders workbench container, header, token savings stats and default tabs', () => {
    render(<UnifiedMultiTabWorkbench />);

    expect(
      screen.getByTestId('unified-multitab-workbench')
    ).toBeInTheDocument();
    expect(screen.getByText('统一全要素侧边工作台')).toBeInTheDocument();
    expect(
      screen.getByText(/累计就地微调 3 次 · 节省 14.2k Token/)
    ).toBeInTheDocument();
    expect(screen.getByText('行业调研深度研报.md')).toBeInTheDocument();
    expect(screen.getByText('沙箱内无头浏览器')).toBeInTheDocument();
    expect(screen.getByText('沙箱 Bash 终端')).toBeInTheDocument();
    expect(screen.getByText('workflowEngine.ts')).toBeInTheDocument();
    expect(
      screen.getByTestId('document-resource-viewer')
    ).toBeInTheDocument();
  });

  it('switches between resource types and renders corresponding viewers', () => {
    render(<UnifiedMultiTabWorkbench />);

    // Switch to Browser
    const browserTab = screen.getByText('沙箱内无头浏览器');
    fireEvent.click(browserTab);
    expect(
      screen.getByTestId('browser-resource-viewer')
    ).toBeInTheDocument();

    // Switch to Terminal
    const terminalTab = screen.getByText('沙箱 Bash 终端');
    fireEvent.click(terminalTab);
    expect(
      screen.getByTestId('terminal-resource-viewer')
    ).toBeInTheDocument();

    // Switch to Code
    const codeTab = screen.getByText('workflowEngine.ts');
    fireEvent.click(codeTab);
    expect(screen.getByTestId('code-resource-viewer')).toBeInTheDocument();
  });

  it('creates new scratchpad tab on plus button click', () => {
    render(<UnifiedMultiTabWorkbench />);

    const addBtn = screen.getByRole('button', { name: '新建协同草稿标签' });
    act(() => {
      fireEvent.click(addBtn);
    });

    expect(screen.getByText('新草稿笔记.md')).toBeInTheDocument();
    expect(
      useWorkbenchStore.getState().activeTabId.startsWith('tab-scratch-')
    ).toBe(true);
  });

  it('closes a tab when close button is clicked', () => {
    render(<UnifiedMultiTabWorkbench />);

    const closeBtn = screen.getByRole('button', {
      name: '关闭标签 workflowEngine.ts',
    });
    act(() => {
      fireEvent.click(closeBtn);
    });

    expect(screen.queryByText('workflowEngine.ts')).not.toBeInTheDocument();
  });

  it('toggles expansion width and dock/undock collapsed states', () => {
    render(<UnifiedMultiTabWorkbench />);

    // Expand width
    const expandBtn = screen.getByRole('button', { name: '加宽工作台视界' });
    fireEvent.click(expandBtn);
    expect(screen.getByTestId('unified-multitab-workbench').className).toContain(
      'w-[720px]'
    );

    // Restore standard width
    const restoreBtn = screen.getByRole('button', { name: '恢复标准宽度' });
    fireEvent.click(restoreBtn);
    expect(screen.getByTestId('unified-multitab-workbench').className).toContain(
      'w-[480px]'
    );

    // Collapse dock
    const collapseBtn = screen.getByRole('button', { name: '收起侧边工作台' });
    act(() => {
      fireEvent.click(collapseBtn);
    });
    expect(useWorkbenchStore.getState().isDocked).toBe(false);
    expect(screen.getByText('全要素工作台')).toBeInTheDocument();

    // Re-open dock
    const openBtn = screen.getByRole('button', { name: '展开侧边工作台' });
    act(() => {
      fireEvent.click(openBtn);
    });
    expect(useWorkbenchStore.getState().isDocked).toBe(true);
  });

  it('triggers selection and renders in-place refinement popover via simulated quick select', () => {
    render(<UnifiedMultiTabWorkbench />);

    const quickSelectBtn = screen.getByRole('button', {
      name: '快速划选测试段落',
    });
    act(() => {
      fireEvent.click(quickSelectBtn);
    });

    expect(
      screen.getByTestId('in-place-partial-refinement-popover')
    ).toBeInTheDocument();
    expect(screen.getByText('划选就地重构精修')).toBeInTheDocument();
  });
});
