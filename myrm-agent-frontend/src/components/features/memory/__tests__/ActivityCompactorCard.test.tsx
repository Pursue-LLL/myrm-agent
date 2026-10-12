/** @vitest-environment jsdom */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ActivityCompactorCard } from '../command-center/ActivityCompactorCard';
import type {
  CompactorPipelineTelemetryDTO,
  DailyPreferenceArchiveDTO,
  MacroMilestoneFoldDTO,
  MicroActivitySliceDTO,
} from '@/services/memory/activityCompactor';

const {
  mockGetActivityCompactorTelemetry,
  mockGetRecentMicroSlices,
  mockGetRecentMacroFolds,
  mockIngestActivityEvent,
  mockTriggerMicroFold,
  mockTriggerMacroDistill,
  mockSynthesizeDailyArchive,
} = vi.hoisted(() => ({
  mockGetActivityCompactorTelemetry: vi.fn(),
  mockGetRecentMicroSlices: vi.fn(),
  mockGetRecentMacroFolds: vi.fn(),
  mockIngestActivityEvent: vi.fn(),
  mockTriggerMicroFold: vi.fn(),
  mockTriggerMacroDistill: vi.fn(),
  mockSynthesizeDailyArchive: vi.fn(),
}));

vi.mock('@/services/memory/activityCompactor', () => ({
  getActivityCompactorTelemetry: mockGetActivityCompactorTelemetry,
  getRecentMicroSlices: mockGetRecentMicroSlices,
  getRecentMacroFolds: mockGetRecentMacroFolds,
  ingestActivityEvent: mockIngestActivityEvent,
  triggerMicroFold: mockTriggerMicroFold,
  triggerMacroDistill: mockTriggerMacroDistill,
  synthesizeDailyArchive: mockSynthesizeDailyArchive,
}));

describe('ActivityCompactorCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockTelemetry: CompactorPipelineTelemetryDTO = {
    total_raw_events: 120,
    total_micro_slices: 12,
    total_macro_folds: 2,
    idle_events_dropped: 7,
    estimated_tokens_saved: 45000,
    compression_ratio: 0.92,
  };

  const mockMicroSlices: MicroActivitySliceDTO[] = [
    {
      slice_id: 'slice_mock_01',
      start_time: '2026-10-08T01:00:00Z',
      end_time: '2026-10-08T01:10:00Z',
      primary_app: 'VSCode',
      raw_event_count: 35,
      folded_summary: '在 VSCode 中连续编辑 35 次代码并保存',
      unique_windows: ['main.ts'],
      is_idle: false,
      active_minutes: 9.5,
    },
  ];

  const mockMacroFolds: MacroMilestoneFoldDTO[] = [
    {
      fold_id: 'fold_mock_01',
      start_time: '2026-10-08T00:00:00Z',
      end_time: '2026-10-08T06:00:00Z',
      milestone_summary: '完成用户认证与鉴权模块的重构与回归测试',
      key_activities: ['单测通过', '性能达标'],
      tags: ['开发', '测试'],
      micro_slices_count: 18,
      confidence: 0.96,
    },
  ];

  it('renders correctly and loads telemetry and timeline data', async () => {
    mockGetActivityCompactorTelemetry.mockResolvedValueOnce(mockTelemetry);
    mockGetRecentMicroSlices.mockResolvedValueOnce(mockMicroSlices);
    mockGetRecentMacroFolds.mockResolvedValueOnce(mockMacroFolds);

    render(<ActivityCompactorCard />);

    expect(screen.getByTestId('activity-compactor-card')).toBeInTheDocument();
    expect(screen.getByText('Item 87 · P0')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('120')).toBeInTheDocument();
      expect(screen.getByText('12')).toBeInTheDocument();
      expect(screen.getByText('2')).toBeInTheDocument();
      expect(screen.getByText('45.0k')).toBeInTheDocument();
    });

    // Check timeline items
    expect(screen.getByText('[VSCode]')).toBeInTheDocument();
    expect(screen.getByText('在 VSCode 中连续编辑 35 次代码并保存')).toBeInTheDocument();
    expect(screen.getByText('完成用户认证与鉴权模块的重构与回归测试')).toBeInTheDocument();
  });

  it('updates form inputs when quick presets are clicked', async () => {
    mockGetActivityCompactorTelemetry.mockResolvedValueOnce(mockTelemetry);
    mockGetRecentMicroSlices.mockResolvedValueOnce([]);
    mockGetRecentMacroFolds.mockResolvedValueOnce([]);

    render(<ActivityCompactorCard />);

    const appInput = screen.getByLabelText(/应用名称/) as HTMLInputElement;
    const windowInput = screen.getByLabelText(/窗口标题/) as HTMLInputElement;
    const payloadInput = screen.getByLabelText(/事件内容/) as HTMLInputElement;

    // Default values
    expect(appInput.value).toBe('VSCode');

    // Click Terminal preset
    fireEvent.click(screen.getByText('终端回归测试 (Terminal)'));
    expect(appInput.value).toBe('Terminal');
    expect(windowInput.value).toBe('zsh - tests');
    expect(payloadInput.value).toBe('bun run vitest run test_api.test.ts');

    // Click Chrome preset
    fireEvent.click(screen.getByText('网页代码评审 (Chrome)'));
    expect(appInput.value).toBe('Chrome');
    expect(windowInput.value).toBe('GitHub PR #108 - Code Review');
    expect(payloadInput.value).toBe('https://github.com/myrm-org/myrm-agent/pull/108');

    // Click VSCode preset back
    fireEvent.click(screen.getByText('代码高频开发 (VSCode)'));
    expect(appInput.value).toBe('VSCode');
    expect(windowInput.value).toBe('src/services/api.ts - editor');
  });

  it('triggers event ingestion and refreshes telemetry', async () => {
    mockGetActivityCompactorTelemetry.mockResolvedValue(mockTelemetry);
    mockGetRecentMicroSlices.mockResolvedValue([]);
    mockGetRecentMacroFolds.mockResolvedValue([]);
    mockIngestActivityEvent.mockResolvedValueOnce({
      event_id: 'evt_new_01',
      app_name: 'VSCode',
      window_title: 'src/services/api.ts - editor',
      action_type: 'keystroke_burst',
      payload: '编辑 API 路由并优化错误边界',
      duration_seconds: 5.0,
      timestamp: '2026-10-08T02:00:00Z',
    });

    render(<ActivityCompactorCard />);

    const ingestBtn = screen.getByText('注入单条操作事件');
    fireEvent.click(ingestBtn);

    await waitFor(() => {
      expect(mockIngestActivityEvent).toHaveBeenCalledWith({
        app_name: 'VSCode',
        window_title: 'src/services/api.ts - editor',
        action_type: 'keystroke_burst',
        event_payload: '编辑 API 路由并优化错误边界',
        duration_seconds: 5.0,
      });
    });
  });

  it('triggers 10min micro fold and reloads status', async () => {
    mockGetActivityCompactorTelemetry.mockResolvedValue(mockTelemetry);
    mockGetRecentMicroSlices.mockResolvedValue(mockMicroSlices);
    mockGetRecentMacroFolds.mockResolvedValue([]);
    mockTriggerMicroFold.mockResolvedValueOnce({
      slices_created: mockMicroSlices,
      buffered_remaining_count: 0,
    });

    render(<ActivityCompactorCard />);

    const microFoldBtn = screen.getByText('触发 10min 微观折叠 (0 Token)');
    fireEvent.click(microFoldBtn);

    await waitFor(() => {
      expect(mockTriggerMicroFold).toHaveBeenCalledWith({ force: true });
      expect(screen.getByText('在 VSCode 中连续编辑 35 次代码并保存')).toBeInTheDocument();
    });
  });

  it('triggers 6h macro distill and reloads macro folds', async () => {
    mockGetActivityCompactorTelemetry.mockResolvedValue(mockTelemetry);
    mockGetRecentMicroSlices.mockResolvedValue([]);
    mockGetRecentMacroFolds.mockResolvedValue(mockMacroFolds);
    mockTriggerMacroDistill.mockResolvedValueOnce({
      folds_created: mockMacroFolds,
      remaining_slices_count: 0,
    });

    render(<ActivityCompactorCard />);

    const macroDistillBtn = screen.getByText('触发 6h 宏观提纯');
    fireEvent.click(macroDistillBtn);

    await waitFor(() => {
      expect(mockTriggerMacroDistill).toHaveBeenCalledWith({ hours_back: 6 });
      expect(screen.getByText('完成用户认证与鉴权模块的重构与回归测试')).toBeInTheDocument();
    });
  });

  it('triggers 24h daily archive synthesis and renders preferences and facts', async () => {
    mockGetActivityCompactorTelemetry.mockResolvedValue(mockTelemetry);
    mockGetRecentMicroSlices.mockResolvedValue([]);
    mockGetRecentMacroFolds.mockResolvedValue([]);
    const archiveResult: DailyPreferenceArchiveDTO = {
      archive_id: 'arch_20261008',
      date_str: '2026-10-08',
      consolidated_facts: ['修复了三个高危内存泄漏与注入漏洞'],
      preference_updates: ['偏好使用严格强类型和 Vitest 单元测试驱动开发'],
      total_raw_events_processed: 300,
      macro_folds_count: 4,
    };
    mockSynthesizeDailyArchive.mockResolvedValueOnce(archiveResult);

    render(<ActivityCompactorCard />);

    const dailyArchiveBtn = screen.getByText('生成 24h 每日归档');
    fireEvent.click(dailyArchiveBtn);

    await waitFor(() => {
      expect(mockSynthesizeDailyArchive).toHaveBeenCalledWith({});
      expect(screen.getByText('修复了三个高危内存泄漏与注入漏洞')).toBeInTheDocument();
      expect(screen.getByText(/偏好使用严格强类型和 Vitest/)).toBeInTheDocument();
    });
  });

  it('handles API errors gracefully with fallback state', async () => {
    mockGetActivityCompactorTelemetry.mockRejectedValue(new Error('Network error'));
    mockGetRecentMicroSlices.mockRejectedValue(new Error('Network error'));
    mockGetRecentMacroFolds.mockRejectedValue(new Error('Network error'));

    render(<ActivityCompactorCard />);

    // Renders without crashing and falls back to mock stats and folds
    expect(screen.getByTestId('activity-compactor-card')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('完成了为期 5.2 小时的高专注开发推进；核心工具链集中于 VSCode, Terminal')).toBeInTheDocument();
    });

    // Trigger daily archive with API rejection to test fallback archive
    mockSynthesizeDailyArchive.mockRejectedValueOnce(new Error('Archive failed'));
    const dailyArchiveBtn = screen.getByText('生成 24h 每日归档');
    fireEvent.click(dailyArchiveBtn);

    await waitFor(() => {
      expect(screen.getByText('完成了认证模块的回归测试并修复 2 处逻辑缺陷')).toBeInTheDocument();
      expect(screen.getByText(/偏好使用本地终端自动化测试与严谨类型检查/)).toBeInTheDocument();
    });
  });
});
