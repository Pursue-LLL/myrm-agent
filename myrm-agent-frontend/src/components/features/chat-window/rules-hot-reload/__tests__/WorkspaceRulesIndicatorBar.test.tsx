/**
 * [INPUT]
 * - @testing-library/react (POS: React Component Testing)
 * - @/components/features/chat-window/rules-hot-reload/WorkspaceRulesIndicatorBar
 * - @/components/features/chat-window/rules-hot-reload/useWorkspaceRulesStore
 *
 * [OUTPUT]
 * - Component UI unit test suite for WorkspaceRulesIndicatorBar status rendering, toggles, and toasts.
 */

import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { WorkspaceRulesIndicatorBar } from '../WorkspaceRulesIndicatorBar';
import { useWorkspaceRulesStore } from '../useWorkspaceRulesStore';

describe('WorkspaceRulesIndicatorBar Component', () => {
  beforeEach(() => {
    useWorkspaceRulesStore.getState().resetStore();
    vi.restoreAllMocks();
  });

  it('should render active rules badge with file count and combined hash', () => {
    const store = useWorkspaceRulesStore.getState();
    store.upsertRuleFile({
      path: '/workspace/AGENTS.md',
      filename: 'AGENTS.md',
      content: '# AGENTS Rule',
    });

    render(<WorkspaceRulesIndicatorBar />);

    expect(screen.getByTestId('workspace-rules-indicator-bar')).toBeInTheDocument();
    expect(screen.getByTestId('rules-badge-active')).toHaveTextContent('规则已装配 (1 个文件)');
    expect(screen.getByTestId('combined-hash-label')).toBeInTheDocument();
  });

  it('should render bypass badge when rules are temporarily bypassed', () => {
    const store = useWorkspaceRulesStore.getState();
    store.setBypassRules(true);

    render(<WorkspaceRulesIndicatorBar />);

    expect(screen.getByTestId('rules-badge-bypass')).toHaveTextContent('已临时绕过项目规则 (裸跑模式)');
    expect(screen.queryByTestId('rules-badge-active')).not.toBeInTheDocument();
  });

  it('should toggle bypass state when bypass button is clicked', () => {
    render(<WorkspaceRulesIndicatorBar />);

    const toggleBtn = screen.getByTestId('btn-toggle-bypass');
    expect(useWorkspaceRulesStore.getState().bypassRules).toBe(false);

    fireEvent.click(toggleBtn);
    expect(useWorkspaceRulesStore.getState().bypassRules).toBe(true);

    fireEvent.click(toggleBtn);
    expect(useWorkspaceRulesStore.getState().bypassRules).toBe(false);
  });

  it('should trigger reload rules and call onReload callback on button click', async () => {
    const onReloadMock = vi.fn();
    render(<WorkspaceRulesIndicatorBar onReload={onReloadMock} />);

    const reloadBtn = screen.getByTestId('btn-reload-rules');
    fireEvent.click(reloadBtn);

    await waitFor(() => {
      expect(onReloadMock).toHaveBeenCalledTimes(1);
    });
  });

  it('should render and dismiss reload toast notification', () => {
    const store = useWorkspaceRulesStore.getState();
    store.upsertRuleFile({
      path: '/workspace/CLAUDE.md',
      filename: 'CLAUDE.md',
      content: '# Guidelines',
    });

    render(<WorkspaceRulesIndicatorBar />);

    expect(screen.getByTestId('rules-reload-toast')).toHaveTextContent('CLAUDE.md (新增)');

    const dismissBtn = screen.getByTestId('btn-dismiss-toast');
    fireEvent.click(dismissBtn);

    expect(screen.queryByTestId('rules-reload-toast')).not.toBeInTheDocument();
  });
});
