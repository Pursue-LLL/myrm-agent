/** @vitest-environment jsdom */

/**
 * [INPUT]
 * @/services/memory/failureSessionRetrieval::queryFailureResolutions, fetchHistoricalResolutions, fetchFailureTriggerConfig, updateFailureTriggerConfig
 * ../command-center/FailureSessionRetrievalStudioCard::FailureSessionRetrievalStudioCard
 *
 * [OUTPUT]
 * Test suite verifying Failure-Triggered Historical Session Retrieval Studio Card (Item 109 P0):
 * 1. Default render of card header, 4-dimension HUD telemetry bar, and search form
 * 2. Search execution and dual-track resolution comparison rendering
 * 3. Tab switching to Historical Resolutions Catalog and filtering
 * 4. Tab switching to Interceptor Configuration and mutation
 *
 * [POS]
 * Unit test for Item 109.
 * Strict typing applied: No `any` types allowed. File lines < 300.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { FailureSessionRetrievalStudioCard } from '../command-center/FailureSessionRetrievalStudioCard';
import type {
  FailureRetrievalResultDTO,
  FailureTriggerConfigDTO,
  HistoricalResolutionEntryDTO,
} from '@/services/memory/failureSessionRetrieval';
import {
  FALLBACK_CONFIG,
  FALLBACK_RESOLUTIONS_CATALOG,
  FALLBACK_SAMPLE_RESULT,
} from '../command-center/failureSessionRetrievalFallbacks';

const {
  mockQueryFailureResolutions,
  mockFetchHistoricalResolutions,
  mockFetchFailureTriggerConfig,
  mockUpdateFailureTriggerConfig,
} = vi.hoisted(() => ({
  mockQueryFailureResolutions: vi.fn(),
  mockFetchHistoricalResolutions: vi.fn(),
  mockFetchFailureTriggerConfig: vi.fn(),
  mockUpdateFailureTriggerConfig: vi.fn(),
}));

vi.mock('@/services/memory/failureSessionRetrieval', () => ({
  queryFailureResolutions: mockQueryFailureResolutions,
  fetchHistoricalResolutions: mockFetchHistoricalResolutions,
  fetchFailureTriggerConfig: mockFetchFailureTriggerConfig,
  updateFailureTriggerConfig: mockUpdateFailureTriggerConfig,
}));

describe('FailureSessionRetrievalStudioCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchHistoricalResolutions.mockResolvedValue(FALLBACK_RESOLUTIONS_CATALOG);
    mockFetchFailureTriggerConfig.mockResolvedValue(FALLBACK_CONFIG);
    mockQueryFailureResolutions.mockResolvedValue(FALLBACK_SAMPLE_RESULT);
    mockUpdateFailureTriggerConfig.mockResolvedValue({
      ...FALLBACK_CONFIG,
      max_matches: 5,
    });
  });

  it('renders card header, HUD bar metrics, and search form by default', async () => {
    render(<FailureSessionRetrievalStudioCard />);

    // Header & Badge
    expect(screen.getByText('历史会话报错检索与自愈中枢')).toBeInTheDocument();
    expect(screen.getByText('Item 109 · P0')).toBeInTheDocument();
    expect(screen.getByText('对标 AgentGit · 零提示自愈')).toBeInTheDocument();

    // 4 HUD metrics
    await waitFor(() => {
      expect(screen.getByText('5')).toBeInTheDocument();
    });
    expect(screen.getByText(/正向解法占比/)).toBeInTheDocument();
    expect(screen.getByText('避坑死胡同库')).toBeInTheDocument();
    expect(screen.getByText('条踩坑教训')).toBeInTheDocument();
    expect(screen.getByText('自动静默接管')).toBeInTheDocument();

    // Search input
    expect(screen.getByLabelText(/原始错误日志/)).toBeInTheDocument();
    expect(screen.getByText('提取指纹并检索历史解法')).toBeInTheDocument();
  });

  it('executes search query and renders dual-track resolutions', async () => {
    render(<FailureSessionRetrievalStudioCard />);

    await waitFor(() => {
      expect(screen.getByText('5')).toBeInTheDocument();
    });

    const searchBtn = screen.getByText('提取指纹并检索历史解法');
    fireEvent.click(searchBtn);

    await waitFor(() => {
      expect(mockQueryFailureResolutions).toHaveBeenCalledTimes(1);
    });

    // 验证提取指纹与建议动作展示
    expect(screen.getByText('PortAlreadyInUseError')).toBeInTheDocument();
    expect(screen.getByText(/建议解法动作:/)).toBeInTheDocument();

    // 验证正向验证解法卡片
    expect(screen.getByText(/正向验证解法/)).toBeInTheDocument();
    expect(screen.getByText('sess_port_resolved_20260903')).toBeInTheDocument();
    expect(
      screen.getByText('lsof -ti:8000 | xargs kill -9 && start_server'),
    ).toBeInTheDocument();

    // 验证避坑死胡同卡片
    expect(screen.getByText(/避坑死胡同警示/)).toBeInTheDocument();
    expect(screen.getByText('sess_port_loop_20260903')).toBeInTheDocument();
    expect(screen.getByText('sleep 5 && retry_start_server')).toBeInTheDocument();
  });

  it('switches to catalog tab and filters between success and cautionary cases', async () => {
    render(<FailureSessionRetrievalStudioCard />);

    await waitFor(() => {
      expect(screen.getByText('5')).toBeInTheDocument();
    });

    // 点击切换至历史解法库 Tab
    const catalogTabBtn = screen.getByRole('button', { name: '切换至历史解法库' });
    fireEvent.click(catalogTabBtn);

    // 校验解法库列表项渲染
    expect(screen.getByText('sess_git_reject_20260901')).toBeInTheDocument();
    expect(screen.getByText('sess_pg_lock_20260908')).toBeInTheDocument();

    // 过滤为仅避坑警示
    const cautionaryFilterBtn = screen.getByRole('button', {
      name: /避坑警示 \(1\)/,
    });
    fireEvent.click(cautionaryFilterBtn);

    // 避坑条目保留，正向条目被过滤
    expect(screen.getByText('sess_port_loop_20260903')).toBeInTheDocument();
    expect(screen.queryByText('sess_git_reject_20260901')).not.toBeInTheDocument();
  });

  it('switches to config tab and saves updated interceptor settings', async () => {
    render(<FailureSessionRetrievalStudioCard />);

    await waitFor(() => {
      expect(screen.getByText('5')).toBeInTheDocument();
    });

    // 切换至配置 Tab
    const configTabBtn = screen.getByRole('button', { name: '切换至拦截器配置' });
    fireEvent.click(configTabBtn);

    expect(screen.getByText('自动化失败拦截自愈参数设置')).toBeInTheDocument();

    // 修改 Top-N 参数
    const maxMatchesInput = screen.getByLabelText(/最大返回历史会话数/);
    fireEvent.change(maxMatchesInput, { target: { value: '5' } });

    // 提交保存配置
    const saveBtn = screen.getByRole('button', { name: /保存拦截参数/ });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(mockUpdateFailureTriggerConfig).toHaveBeenCalledTimes(1);
    });
    expect(screen.getByText('拦截器参数已成功保存')).toBeInTheDocument();
  });
});
