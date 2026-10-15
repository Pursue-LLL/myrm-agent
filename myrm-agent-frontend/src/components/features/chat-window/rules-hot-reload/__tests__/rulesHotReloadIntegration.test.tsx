/**
 * [INPUT]
 * - @testing-library/react (POS: React Component Testing)
 * - @/components/features/chat-window/rules-hot-reload/WorkspaceRulesIndicatorBar
 * - @/components/features/chat-window/rules-hot-reload/useWorkspaceRulesStore
 * - @/components/features/chat-window/rules-hot-reload/rulesHotReloadTypes
 *
 * [OUTPUT]
 * - End-to-end integration test suite verifying file-watcher event broadcasting and UI updates.
 */

import React from 'react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import { WorkspaceRulesIndicatorBar } from '../WorkspaceRulesIndicatorBar';
import { useWorkspaceRulesStore } from '../useWorkspaceRulesStore';
import type { RulesReloadEventPayload } from '../rulesHotReloadTypes';

describe('WorkspaceRules Hot-Reload Integration Workflow', () => {
  const capturedEvents: RulesReloadEventPayload[] = [];

  const handleRulesEvent = (e: Event) => {
    const custom = e as CustomEvent<RulesReloadEventPayload>;
    if (custom.detail) {
      capturedEvents.push(custom.detail);
    }
  };

  beforeEach(() => {
    capturedEvents.length = 0;
    useWorkspaceRulesStore.getState().resetStore();
    window.addEventListener('myrm:workspace-rules-reloaded', handleRulesEvent);
    vi.restoreAllMocks();
  });

  afterEach(() => {
    window.removeEventListener('myrm:workspace-rules-reloaded', handleRulesEvent);
    vi.restoreAllMocks();
  });

  it('should broadcast custom DOM event on file modification and render real-time UI indicator', async () => {
    render(<WorkspaceRulesIndicatorBar />);

    // 初始状态：无规则文件
    expect(screen.getByTestId('rules-badge-active')).toHaveTextContent('规则已装配 (0 个文件)');

    // 模拟文件监听器触发：新增 AGENTS.md
    act(() => {
      useWorkspaceRulesStore.getState().upsertRuleFile(
        {
          path: '/workspace/AGENTS.md',
          filename: 'AGENTS.md',
          content: 'You are an AI Agent with strict PEP8 and ESLint standards.',
        },
        'file_watcher',
      );
    });

    // 验证事件广播
    expect(capturedEvents).toHaveLength(1);
    expect(capturedEvents[0].source).toBe('file_watcher');
    expect(capturedEvents[0].diffs).toHaveLength(1);
    expect(capturedEvents[0].diffs[0].filename).toBe('AGENTS.md');
    expect(capturedEvents[0].diffs[0].diffType).toBe('added');

    // 验证 UI 自动呈现更新
    expect(screen.getByTestId('rules-badge-active')).toHaveTextContent('规则已装配 (1 个文件)');
    expect(screen.getByTestId('rules-reload-toast')).toHaveTextContent('AGENTS.md (新增)');

    // 模拟文件内容发生二次变更
    const firstHash = capturedEvents[0].combinedHash;
    act(() => {
      useWorkspaceRulesStore.getState().upsertRuleFile(
        {
          path: '/workspace/AGENTS.md',
          filename: 'AGENTS.md',
          content: 'You are an AI Agent. Single file lines must be below 400.',
        },
        'file_watcher',
      );
    });

    // 验证捕获第二个修改事件
    expect(capturedEvents).toHaveLength(2);
    expect(capturedEvents[1].diffs[0].diffType).toBe('modified');
    expect(capturedEvents[1].combinedHash).not.toBe(firstHash);
    expect(screen.getByTestId('rules-reload-toast')).toHaveTextContent('AGENTS.md (已修改)');
  });

  it('should toggle rules bypass mode across store and UI seamlessly', () => {
    render(<WorkspaceRulesIndicatorBar />);

    expect(screen.getByTestId('rules-badge-active')).toBeInTheDocument();

    // 点击绕过规则
    const bypassBtn = screen.getByTestId('btn-toggle-bypass');
    fireEvent.click(bypassBtn);

    expect(screen.getByTestId('rules-badge-bypass')).toBeInTheDocument();
    expect(useWorkspaceRulesStore.getState().bypassRules).toBe(true);

    // 再次点击恢复注入规则
    fireEvent.click(bypassBtn);
    expect(screen.getByTestId('rules-badge-active')).toBeInTheDocument();
    expect(useWorkspaceRulesStore.getState().bypassRules).toBe(false);
  });

  it('should broadcast manual_reload event on /reload click', async () => {
    useWorkspaceRulesStore.getState().upsertRuleFile({
      path: '/workspace/CLAUDE.md',
      filename: 'CLAUDE.md',
      content: '# Initial Claude Rule',
    });

    render(<WorkspaceRulesIndicatorBar />);
    capturedEvents.length = 0;

    const reloadBtn = screen.getByTestId('btn-reload-rules');
    fireEvent.click(reloadBtn);

    await waitFor(() => {
      expect(capturedEvents.length).toBeGreaterThanOrEqual(1);
      expect(capturedEvents[capturedEvents.length - 1].source).toBe('manual_reload');
    });
  });
});
