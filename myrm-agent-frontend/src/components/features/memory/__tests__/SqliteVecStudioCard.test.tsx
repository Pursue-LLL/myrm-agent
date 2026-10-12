/** @vitest-environment jsdom */

/**
 * [INPUT]
 * @/services/memory::(fetchSqliteVecStats, searchSqliteVec)
 * ../command-center/SqliteVecStudioCard::SqliteVecStudioCard
 *
 * [OUTPUT]
 * Test suite verifying SqliteVec Embedded Vector Store Studio Card (Item 130 P0):
 * 1. Default render of HUD telemetry metrics, engine mode badge, and query console
 * 2. Execution of dense vector search and rendering results with temporal decay comparison
 * 3. Switching preset query vector samples
 * 4. Refreshing database metrics via HUD button
 * 5. Error handling and alert banner display on retrieval failure
 *
 * [POS]
 * Unit tests for Item 130.
 * Strict typing applied: Zero `any` types. Single file < 200 lines.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SqliteVecStudioCard } from '../command-center/SqliteVecStudioCard';
import {
  FALLBACK_SQLITE_VEC_SEARCH_RESPONSE,
  FALLBACK_SQLITE_VEC_STATS,
} from '../command-center/sqliteVecFallbacks';

const { mockFetchStats, mockSearchVectors } = vi.hoisted(() => ({
  mockFetchStats: vi.fn(),
  mockSearchVectors: vi.fn(),
}));

vi.mock('@/services/memory', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    fetchSqliteVecStats: mockFetchStats,
    searchSqliteVec: mockSearchVectors,
  };
});

describe('SqliteVecStudioCard (Item 130 P0)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchStats.mockResolvedValue(FALLBACK_SQLITE_VEC_STATS);
    mockSearchVectors.mockResolvedValue(FALLBACK_SQLITE_VEC_SEARCH_RESPONSE);
  });

  it('renders default HUD metrics, engine mode, and query console', async () => {
    render(<SqliteVecStudioCard />);

    expect(screen.getByText('SQLite-Vec 嵌入式向量引擎')).toBeInTheDocument();
    expect(screen.getByText('文件体积:')).toBeInTheDocument();
    expect(screen.getByText('存储文档数:')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('Native SIMD (vec0)')).toBeInTheDocument();
      expect(screen.getByText('1250')).toBeInTheDocument();
    });

    expect(
      screen.getByText('稠密向量近邻检索控制台 (Dense Vector Retrieval Console)')
    ).toBeInTheDocument();
  });

  it('executes dense vector retrieval and displays results with temporal decay analysis', async () => {
    render(<SqliteVecStudioCard />);

    const searchBtn = screen.getByRole('button', { name: /执行稠密向量检索/i });
    fireEvent.click(searchBtn);

    await waitFor(() => {
      expect(mockSearchVectors).toHaveBeenCalledTimes(1);
    });

    await waitFor(() => {
      expect(
        screen.getByText(/检索结果与时间衰减比对 \(3 条命中\)/)
      ).toBeInTheDocument();
      expect(screen.getByText('doc_arch_001')).toBeInTheDocument();
      expect(
        screen.getByText(/单文件严格不超过400行，严禁使用any类型/)
      ).toBeInTheDocument();
      expect(screen.getByText(/有效得分: 0.940/)).toBeInTheDocument();
    });
  });

  it('switches preset query vector sample when clicked', async () => {
    render(<SqliteVecStudioCard />);

    const prefSampleBtn = screen.getByRole('button', {
      name: /用户日常偏好与交互风格 \(User Preference\)/i,
    });
    fireEvent.click(prefSampleBtn);

    expect(prefSampleBtn.className).toContain('border-primary');
  });

  it('refreshes telemetry metrics via HUD refresh button', async () => {
    render(<SqliteVecStudioCard />);

    await waitFor(() => {
      expect(mockFetchStats).toHaveBeenCalledTimes(1);
    });

    const refreshBtn = screen.getByRole('button', { name: /刷新向量引擎统计指标/i });
    fireEvent.click(refreshBtn);

    await waitFor(() => {
      expect(mockFetchStats).toHaveBeenCalledTimes(2);
    });
  });

  it('handles search failure gracefully by adapting fallback and rendering alert banner', async () => {
    mockSearchVectors.mockRejectedValueOnce(new Error('向量检索超时或引擎降级'));

    render(<SqliteVecStudioCard />);

    const searchBtn = screen.getByRole('button', { name: /执行稠密向量检索/i });
    fireEvent.click(searchBtn);

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(screen.getByText(/向量检索超时或引擎降级/)).toBeInTheDocument();
    });
  });
});
