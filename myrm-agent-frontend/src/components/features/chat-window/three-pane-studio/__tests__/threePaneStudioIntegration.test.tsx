/**
 * [INPUT]
 * - @testing-library/react (POS: React Component Testing)
 * - @/components/features/chat-window/three-pane-studio/ThreePaneContextStudio
 * - @/components/features/chat-window/three-pane-studio/useThreePaneStudioStore
 * - @/components/features/chat-window/three-pane-studio/threePaneStudioEngine
 *
 * [OUTPUT]
 * - End-to-end integration test suite verifying real-time tool highlight linkage and reference insertion.
 */

import React from 'react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import { ThreePaneContextStudio } from '../ThreePaneContextStudio';
import { useThreePaneStudioStore } from '../useThreePaneStudioStore';
import {
  buildDefaultContextTree,
  dispatchStudioToolEvent,
} from '../threePaneStudioEngine';

describe('ThreePaneStudio Integration Linkage', () => {
  beforeEach(() => {
    useThreePaneStudioStore.getState().resetStore();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('should auto-unfold tree, apply pulse highlight, and load content into middle pane when agent triggers tool event', async () => {
    const customTree = buildDefaultContextTree({
      resources: [
        {
          id: 'math-utils',
          name: 'math.ts',
          path: '/workspace/src/math.ts',
          content: 'export const add = (a: number, b: number) => a + b;',
        },
      ],
    });

    useThreePaneStudioStore.getState().setRootNodes(customTree);

    render(<ThreePaneContextStudio />);

    // 初始状态：中栏为空
    expect(screen.getByTestId('middle-content-pane-empty')).toBeInTheDocument();

    // 模拟 Agent 在后台调用 read_file 工具
    act(() => {
      dispatchStudioToolEvent({
        toolName: 'read_file',
        targetPath: '/workspace/src/math.ts',
        actionType: 'read',
        timestamp: Date.now(),
      });
    });

    // 验证中栏自动切换并显示该文件内容
    await waitFor(() => {
      expect(screen.getByTestId('middle-content-pane')).toBeInTheDocument();
      expect(screen.getByTestId('node-title')).toHaveTextContent('math.ts');
      expect(screen.getByTestId('node-content-body')).toHaveTextContent('export const add = (a: number, b: number) => a + b;');
    });

    // 验证状态横幅显示读取中
    expect(screen.getByTestId('agent-live-action-banner')).toHaveTextContent('正在读取该条目上下文...');

    // 验证左栏高亮样式
    const targetNodeElement = screen.getByTestId('tree-node-res-math-utils');
    expect(targetNodeElement.className).toContain('ring-cyan-500');
  });

  it('should trigger onInsertReference callback when user clicks reference button on a context node', () => {
    const customTree = buildDefaultContextTree({
      memories: [
        {
          id: 'user-pref',
          title: '代码风格约定',
          content: '优先采用函数式纯组件，严格 TypeScript 类型。',
        },
      ],
    });

    useThreePaneStudioStore.getState().setRootNodes(customTree);
    // 展开记忆根节点
    useThreePaneStudioStore.getState().toggleNodeExpanded('root-user-memory', true);

    const onInsertReferenceMock = vi.fn();

    render(<ThreePaneContextStudio onInsertReference={onInsertReferenceMock} />);

    // 点击该记忆条目节点的一键引用按钮
    const refBtn = screen.getByTestId('btn-reference-mem-user-pref');
    fireEvent.click(refBtn);

    expect(onInsertReferenceMock).toHaveBeenCalledTimes(1);
    expect(onInsertReferenceMock).toHaveBeenCalledWith(
      expect.objectContaining({
        id: 'mem-user-pref',
        label: '代码风格约定',
      }),
    );
  });

  it('should copy content from middle pane to clipboard when copy button is clicked', async () => {
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    const customTree = buildDefaultContextTree({
      resources: [
        {
          id: 'config-yml',
          name: 'config.yml',
          path: '/workspace/config.yml',
          content: 'env: production\nport: 443',
        },
      ],
    });

    useThreePaneStudioStore.getState().setRootNodes(customTree);
    useThreePaneStudioStore.getState().selectNode('res-config-yml');

    render(<ThreePaneContextStudio />);

    const copyBtn = screen.getByTestId('btn-copy-content');
    fireEvent.click(copyBtn);

    await waitFor(() => {
      expect(writeTextMock).toHaveBeenCalledWith('env: production\nport: 443');
    });
  });
});
