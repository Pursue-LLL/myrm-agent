import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { CommandCenterUsageTab } from '../CommandCenterUsageTab';
import { useCommandCenterStore } from '../useCommandCenterStore';

describe('CommandCenterUsageTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useCommandCenterStore.getState().resetStore();
  });

  it('应正确渲染用量大盘卡片、Top Models 与 Top Skills', () => {
    render(<CommandCenterUsageTab />);

    expect(screen.getByTestId('command-center-usage-tab')).toBeInTheDocument();
    expect(screen.getByText(/用量与资产透视大盘/)).toBeInTheDocument();
    expect(screen.getByText('SESSIONS')).toBeInTheDocument();
    expect(screen.getByText('API CALLS')).toBeInTheDocument();
    expect(screen.getByText('TOKENS IN')).toBeInTheDocument();
    expect(screen.getByText('TOKENS OUT')).toBeInTheDocument();

    expect(screen.getByText(/Claude 3.7 Thinking/)).toBeInTheDocument();
    expect(screen.getByText(/DeepSeek-R1/)).toBeInTheDocument();
    expect(screen.getByText(/code_execution/)).toBeInTheDocument();
  });

  it('点击 30 天用量按钮能动态更新指标乘数', () => {
    render(<CommandCenterUsageTab />);

    const btn30 = screen.getByRole('button', { name: /30 天用量/i });
    fireEvent.click(btn30);

    expect(useCommandCenterStore.getState().usageHorizon).toBe(30);
    // 30 天会话数为 7 天的 4 倍 (697 * 4 = 2,788)
    expect(screen.getByText('2,788')).toBeInTheDocument();
  });
});
