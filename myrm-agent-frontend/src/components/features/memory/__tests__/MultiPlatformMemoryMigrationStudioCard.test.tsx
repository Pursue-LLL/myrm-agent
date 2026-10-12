/** @vitest-environment jsdom */

/**
 * Test suite verifying Item 134 MultiPlatformMemoryMigrationAndImportEngineSuite:
 * 1. Default render of HUD telemetry bar, detected candidate assets, and preview section.
 * 2. Candidate selection pre-filling file path and target ecosystem.
 * 3. Preview trigger calling memoryMigrationService.previewMemory.
 * 4. One-click import execution calling memoryMigrationService.importMemory and displaying audit telemetry.
 * 5. Resilient fallback on network/service failure.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { MultiPlatformMemoryMigrationStudioCard } from '../command-center/MultiPlatformMemoryMigrationStudioCard';
import {
  mockDetectedCandidates,
  mockImportReport,
  mockPreviewUnits,
  mockSupportedSources,
} from '../command-center/memoryMigrationFallbacks';

const {
  mockListSources,
  mockDetectAssets,
  mockPreviewMemory,
  mockImportMemory,
} = vi.hoisted(() => ({
  mockListSources: vi.fn(),
  mockDetectAssets: vi.fn(),
  mockPreviewMemory: vi.fn(),
  mockImportMemory: vi.fn(),
}));

vi.mock('@/services/memory/memoryMigration', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    memoryMigrationService: {
      listSources: mockListSources,
      detectAssets: mockDetectAssets,
      previewMemory: mockPreviewMemory,
      importMemory: mockImportMemory,
    },
  };
});

describe('MultiPlatformMemoryMigrationStudioCard (Item 134 P1)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListSources.mockResolvedValue({ supported_sources: mockSupportedSources });
    mockDetectAssets.mockResolvedValue({
      total_detected: mockDetectedCandidates.length,
      candidates: mockDetectedCandidates,
    });
    mockPreviewMemory.mockResolvedValue({
      total_extracted: mockPreviewUnits.length,
      units: mockPreviewUnits,
    });
    mockImportMemory.mockResolvedValue({
      success: true,
      report: mockImportReport,
    });
  });

  it('1. should render HUD telemetry bar, detected assets, and preview cards', async () => {
    render(<MultiPlatformMemoryMigrationStudioCard />);

    expect(screen.getByText('全平台记忆迁移引擎')).toBeInTheDocument();
    expect(screen.getByText('零成本资产导入')).toBeInTheDocument();
    expect(screen.getByText('本地竞品记忆资产探测器')).toBeInTheDocument();
    expect(screen.getByText('认知分层归一化映射与事实预览')).toBeInTheDocument();
    expect(screen.getByText('一键迁移导入控制台')).toBeInTheDocument();

    await waitFor(() => {
      expect(mockListSources).toHaveBeenCalledTimes(1);
      expect(mockDetectAssets).toHaveBeenCalledTimes(1);
    });
  });

  it('2. should pre-fill file path when selecting a detected candidate asset', async () => {
    render(<MultiPlatformMemoryMigrationStudioCard />);

    await waitFor(() => {
      expect(screen.getByText('~/.openclaw/memory.json')).toBeInTheDocument();
    });

    const selectButtons = screen.getAllByRole('button', { name: /选择导入/i });
    expect(selectButtons.length).toBeGreaterThan(0);

    fireEvent.click(selectButtons[0]);

    const filePathInput = screen.getByLabelText(/外部文件绝对路径/i) as HTMLInputElement;
    expect(filePathInput.value).toBe('~/.openclaw/memory.json');
  });

  it('3. should trigger previewMemory when clicking preview button', async () => {
    render(<MultiPlatformMemoryMigrationStudioCard />);

    await waitFor(() => {
      expect(screen.getByText('~/.openclaw/memory.json')).toBeInTheDocument();
    });

    // Select candidate
    const selectButtons = screen.getAllByRole('button', { name: /选择导入/i });
    fireEvent.click(selectButtons[0]);

    const previewButton = screen.getByRole('button', { name: /预览映射/i });
    fireEvent.click(previewButton);

    await waitFor(() => {
      expect(mockPreviewMemory).toHaveBeenCalledWith(
        expect.objectContaining({
          source_type: 'openclaw',
          file_path: '~/.openclaw/memory.json',
        })
      );
    });
  });

  it('4. should trigger importMemory and display latest migration audit telemetry', async () => {
    render(<MultiPlatformMemoryMigrationStudioCard />);

    await waitFor(() => {
      expect(screen.getByText('~/.openclaw/memory.json')).toBeInTheDocument();
    });

    // Select candidate
    const selectButtons = screen.getAllByRole('button', { name: /选择导入/i });
    fireEvent.click(selectButtons[0]);

    const importButton = screen.getByRole('button', { name: /一键导入/i });
    fireEvent.click(importButton);

    await waitFor(() => {
      expect(mockImportMemory).toHaveBeenCalledWith(
        expect.objectContaining({
          source_type: 'openclaw',
          file_path: '~/.openclaw/memory.json',
        })
      );
    });

    await waitFor(() => {
      expect(screen.getByText('最新迁移遥测审计账本')).toBeInTheDocument();
      expect(screen.getByText(/mig-demo-773a9/i)).toBeInTheDocument();
    });
  });

  it('5. should gracefully fall back to default data when api fails', async () => {
    render(<MultiPlatformMemoryMigrationStudioCard />);

    const scanButton = screen.getByRole('button', { name: /一键扫描本地记忆资产/i });
    await waitFor(() => {
      expect(scanButton).not.toBeDisabled();
    });

    mockDetectAssets.mockRejectedValueOnce(new Error('Network error'));
    fireEvent.click(scanButton);

    await waitFor(() => {
      expect(screen.getByText(/网络离线，已加载默认扫描资产/i)).toBeInTheDocument();
    });
  });
});
