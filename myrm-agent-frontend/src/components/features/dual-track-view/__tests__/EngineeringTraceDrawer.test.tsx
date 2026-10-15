import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { EngineeringTraceDrawer } from '../EngineeringTraceDrawer';
import { useDualTrackStore } from '../useDualTrackStore';
import type { EngineeringTraceDetails } from '../dualTrackTypes';

describe('EngineeringTraceDrawer', () => {
  const mockTrace: EngineeringTraceDetails = {
    turnId: 'turn-999',
    toolCalls: [
      {
        id: 'c1',
        toolName: 'execute_python_script',
        inputSummary: 'import pandas as pd...',
        durationMs: 120,
      },
    ],
    codeDiffs: [
      {
        filePath: 'src/components/Chart.tsx',
        diffText: '+<canvas id="chart"/>',
        additions: 18,
        deletions: 2,
      },
    ],
    terminalLogs: [
      'pip install pandas numpy',
      'Execution completed with status code 0',
    ],
    testAssertions: [
      { id: 't1', testName: 'verify_data_schema', passed: true },
      { id: 't2', testName: 'verify_canvas_render', passed: false },
    ],
    timestamp: Date.now(),
  };

  beforeEach(() => {
    useDualTrackStore.getState().resetAll();
  });

  it('抽屉关闭或无活跃 trace 时不渲染任何内容', () => {
    useDualTrackStore.setState({
      isTraceDrawerOpen: false,
      activeTraceDetails: null,
    });
    const { container } = render(<EngineeringTraceDrawer />);
    expect(container.firstChild).toBeNull();
  });

  it('打开抽屉时正常渲染头部、统计徽章与工具调用面板', () => {
    useDualTrackStore.setState({
      isTraceDrawerOpen: true,
      activeTraceDetails: mockTrace,
    });

    render(<EngineeringTraceDrawer />);
    expect(
      screen.getByTestId('engineering-trace-drawer')
    ).toBeInTheDocument();
    expect(
      screen.getByText('底层工程执行细节')
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('trace-tools-panel')
    ).toBeInTheDocument();
    expect(
      screen.getByText('execute_python_script')
    ).toBeInTheDocument();
  });

  it('支持切换 Tab 检视代码 Diff、终端命令与测试断言', () => {
    useDualTrackStore.setState({
      isTraceDrawerOpen: true,
      activeTraceDetails: mockTrace,
    });

    render(<EngineeringTraceDrawer />);

    // 切换到 Diff 面板
    fireEvent.click(screen.getByTestId('tab-diffs-btn'));
    expect(
      screen.getByTestId('trace-diffs-panel')
    ).toBeInTheDocument();
    expect(
      screen.getByText('src/components/Chart.tsx')
    ).toBeInTheDocument();
    expect(screen.getByText('+18')).toBeInTheDocument();

    // 切换到终端面板
    fireEvent.click(screen.getByTestId('tab-terminal-btn'));
    expect(
      screen.getByTestId('trace-terminal-panel')
    ).toBeInTheDocument();
    expect(
      screen.getByText('pip install pandas numpy')
    ).toBeInTheDocument();

    // 切换到测试断言面板
    fireEvent.click(screen.getByTestId('tab-tests-btn'));
    expect(
      screen.getByTestId('trace-tests-panel')
    ).toBeInTheDocument();
    expect(screen.getByText('verify_data_schema')).toBeInTheDocument();
    expect(screen.getByText('verify_canvas_render')).toBeInTheDocument();
  });

  it('点击关闭按钮关闭抽屉并触发回调', () => {
    const handleClose = vi.fn();
    useDualTrackStore.setState({
      isTraceDrawerOpen: true,
      activeTraceDetails: mockTrace,
    });

    render(<EngineeringTraceDrawer onClose={handleClose} />);
    const closeBtn = screen.getByTestId('close-trace-drawer-btn');
    fireEvent.click(closeBtn);

    expect(handleClose).toHaveBeenCalledTimes(1);
    expect(useDualTrackStore.getState().isTraceDrawerOpen).toBe(false);
  });
});
