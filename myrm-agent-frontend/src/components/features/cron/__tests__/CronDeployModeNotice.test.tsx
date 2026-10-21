import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

const mockUseDeployMode = vi.hoisted(() => vi.fn());

vi.mock('@/hooks/shared/useDeployMode', () => ({
  useDeployMode: mockUseDeployMode,
}));

import CronDeployModeNotice from '../CronDeployModeNotice';

function deployState(
  overrides: Partial<{
    isLoading: boolean;
    isLocal: boolean;
    isSandbox: boolean;
    mode: 'local' | 'tauri' | 'sandbox';
  }> = {},
) {
  return {
    mode: 'local' as const,
    isLoading: false,
    isLocal: true,
    isSandbox: false,
    ...overrides,
  };
}

describe('CronDeployModeNotice', () => {
  it('加载中不渲染', () => {
    mockUseDeployMode.mockReturnValue(deployState({ isLoading: true }));
    const { container } = render(<CronDeployModeNotice />);
    expect(container.firstChild).toBeNull();
  });

  it('本地模式展示主机依赖与休眠提示', () => {
    mockUseDeployMode.mockReturnValue(deployState());
    render(<CronDeployModeNotice />);
    expect(screen.getByText('deployLocalNotice')).toBeInTheDocument();
    expect(screen.getByText('deployLocalSleepHint')).toBeInTheDocument();
    expect(screen.queryByText('deployCloudNotice')).not.toBeInTheDocument();
  });

  it('tauri 模式按本地处理', () => {
    mockUseDeployMode.mockReturnValue(deployState({ mode: 'tauri' }));
    render(<CronDeployModeNotice />);
    expect(screen.getByText('deployLocalNotice')).toBeInTheDocument();
  });

  it('云端模式展示 7×24 说明', () => {
    mockUseDeployMode.mockReturnValue(deployState({ isLocal: false, isSandbox: true, mode: 'sandbox' }));
    render(<CronDeployModeNotice />);
    expect(screen.getByText('deployCloudNotice')).toBeInTheDocument();
    expect(screen.queryByText('deployLocalNotice')).not.toBeInTheDocument();
  });
});
