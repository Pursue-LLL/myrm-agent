/** @vitest-environment jsdom */

/**
 * [INPUT]
 * @/services/memory/diskReconciliation::triggerReconciliation, checkWriteGate, setWriteGatePolicy,
 *   searchReconciledFts, getReconciliationStats
 * ../command-center/DiskMemoryReconciliationCard::DiskMemoryReconciliationCard
 *
 * [OUTPUT]
 * Test suite verifying bi-directional disk-memory reconciliation loop (Direction A & B),
 * FTS5 keyword verification search, explicit write gate policies, and permission probes.
 *
 * [POS]
 * Unit test for Item 94 (Disk Memory FTS Reconciliation Loop & Explicit Write Gate Suite).
 * Strict typing applied: No `any` types allowed. File lines < 400.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { DiskMemoryReconciliationCard } from '../command-center/DiskMemoryReconciliationCard';
import type {
  ReconciliationReportDTO,
  WriteGateCheckResultDTO,
  FtsReconciledHitDTO,
  ReconciliationStatsDTO,
} from '@/services/memory/diskReconciliation';

const {
  mockTriggerReconciliation,
  mockCheckWriteGate,
  mockSetWriteGatePolicy,
  mockSearchReconciledFts,
  mockGetReconciliationStats,
} = vi.hoisted(() => ({
  mockTriggerReconciliation: vi.fn(),
  mockCheckWriteGate: vi.fn(),
  mockSetWriteGatePolicy: vi.fn(),
  mockSearchReconciledFts: vi.fn(),
  mockGetReconciliationStats: vi.fn(),
}));

vi.mock('@/services/memory/diskReconciliation', () => ({
  triggerReconciliation: mockTriggerReconciliation,
  checkWriteGate: mockCheckWriteGate,
  setWriteGatePolicy: mockSetWriteGatePolicy,
  searchReconciledFts: mockSearchReconciledFts,
  getReconciliationStats: mockGetReconciliationStats,
}));

describe('DiskMemoryReconciliationCard', () => {
  const sampleStats: ReconciliationStatsDTO = {
    total_indexed_files: 18,
    global_write_policy: 'enabled',
  };

  const sampleReport: ReconciliationReportDTO = {
    reconcile_id: 'rec_test_pass_01',
    scanned_disk_files_count: 18,
    indexed_or_updated_count: 4,
    pruned_dead_rows_count: 1,
    duration_ms: 12.8,
    status: 'completed',
    created_at: '2026-10-08T02:00:00Z',
  };

  const sampleGateResult: WriteGateCheckResultDTO = {
    is_allowed: true,
    policy: 'enabled',
    reason: 'Memory writes are explicitly enabled.',
  };

  const sampleSearchResults: FtsReconciledHitDTO[] = [
    {
      file_path: '.myrm/memory/project_architecture.md',
      title: 'Project Architecture Decision',
      snippet: 'Using <b>hexagonal</b> decoupled persistence architecture.',
      rank_score: -1.245,
    },
    {
      file_path: '.myrm/memory/known_issues.md',
      title: 'Known Subagent Issues',
      snippet: 'Avoid blocking <b>hexagonal</b> gates in read-only sessions.',
      rank_score: -0.892,
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    mockGetReconciliationStats.mockResolvedValue(sampleStats);
    mockCheckWriteGate.mockResolvedValue(sampleGateResult);
    mockTriggerReconciliation.mockResolvedValue(sampleReport);
    mockSearchReconciledFts.mockResolvedValue(sampleSearchResults);
    mockSetWriteGatePolicy.mockResolvedValue({
      is_allowed: false,
      policy: 'read_only_session',
      reason: 'Session is configured in strict read-only mode to prevent side-effects.',
    });
  });

  it('renders HUD statistics and default reconciliation audit tab correctly', async () => {
    render(<DiskMemoryReconciliationCard />);

    await waitFor(() => {
      expect(screen.getByText('磁盘文件与 FTS5 双向对账及显式写入门禁套件')).toBeInTheDocument();
    });

    expect(screen.getByTestId('hud-total-indexed')).toHaveTextContent('18');
    expect(screen.getByTestId('hud-active-policy')).toHaveTextContent('ENABLED');
    expect(screen.getByTestId('hud-last-indexed')).toHaveTextContent('+2');
    expect(screen.getByTestId('hud-last-pruned')).toHaveTextContent('-0');

    // Direction A & B explanation in banner
    expect(screen.getByText(/磁盘文件与 SQLite FTS5 双向对账机制/)).toBeInTheDocument();
  });

  it('triggers a bi-directional reconciliation pass and refreshes report', async () => {
    render(<DiskMemoryReconciliationCard />);

    await waitFor(() => {
      expect(screen.getByTestId('reconciliation-sync-form')).toBeInTheDocument();
    });

    // Enter roots input
    const rootsInput = screen.getByLabelText(/扫描目标磁盘目录/);
    fireEvent.change(rootsInput, { target: { value: '.myrm/memory, docs/decisions' } });

    // Submit reconciliation form
    const syncBtn = screen.getByTestId('btn-trigger-reconcile');
    fireEvent.click(syncBtn);

    await waitFor(() => {
      expect(mockTriggerReconciliation).toHaveBeenCalledWith({
        roots: ['.myrm/memory', 'docs/decisions'],
      });
    });

    // Verify updated report counts
    expect(screen.getByTestId('report-scanned-count')).toHaveTextContent('18 篇');
    expect(screen.getByTestId('report-indexed-count')).toHaveTextContent('+4 条');
    expect(screen.getByTestId('report-pruned-count')).toHaveTextContent('-1 条');
    expect(screen.getByTestId('report-duration-ms')).toHaveTextContent('12.8 ms');
  });

  it('executes FTS5 keyword verification search and renders ranked hits', async () => {
    render(<DiskMemoryReconciliationCard />);

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/输入检索词检验 FTS 命中/)).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText(/输入检索词检验 FTS 命中/);
    fireEvent.change(searchInput, { target: { value: 'hexagonal' } });

    const searchBtn = screen.getByTestId('btn-reconciliation-search');
    fireEvent.click(searchBtn);

    await waitFor(() => {
      expect(mockSearchReconciledFts).toHaveBeenCalledWith('hexagonal');
    });

    expect(screen.getByTestId('reconciliation-search-hits-list')).toBeInTheDocument();
    expect(screen.getByText('Project Architecture Decision')).toBeInTheDocument();
    expect(screen.getByText('Known Subagent Issues')).toBeInTheDocument();
  });

  it('switches to write gate tab and displays explicit permission policies', async () => {
    render(<DiskMemoryReconciliationCard />);

    await waitFor(() => {
      expect(screen.getByTestId('tab-write-gate')).toBeInTheDocument();
    });

    // Switch tab
    fireEvent.click(screen.getByTestId('tab-write-gate'));

    await waitFor(() => {
      expect(screen.getByText(/严格读写解耦架构/)).toBeInTheDocument();
    });

    expect(screen.getByText('写入门禁策略管控 (Write Gate Policy Switch)')).toBeInTheDocument();
    expect(screen.getByText('实时写门禁裁决探针 (Live Gate Decision Probe)')).toBeInTheDocument();
  });

  it('probes live write gate permission with session context', async () => {
    render(<DiskMemoryReconciliationCard />);

    await waitFor(() => {
      expect(screen.getByTestId('tab-write-gate')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('tab-write-gate'));

    await waitFor(() => {
      expect(screen.getByTestId('btn-probe-write-gate')).toBeInTheDocument();
    });

    // Fill session override input
    const sessionInput = screen.getByLabelText(/会话作用域/);
    fireEvent.change(sessionInput, { target: { value: 'sess_eval_01' } });

    // Click probe button
    const probeBtn = screen.getByTestId('btn-probe-write-gate');
    fireEvent.click(probeBtn);

    await waitFor(() => {
      expect(mockCheckWriteGate).toHaveBeenCalledWith('sess_eval_01');
    });

    expect(screen.getByTestId('gate-decision-box')).toBeInTheDocument();
    expect(screen.getByText(/写权限通过：允许持久化写入/)).toBeInTheDocument();
  });

  it('updates write gate policy to read_only_session and updates active policy', async () => {
    render(<DiskMemoryReconciliationCard />);

    await waitFor(() => {
      expect(screen.getByTestId('tab-write-gate')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('tab-write-gate'));

    await waitFor(() => {
      expect(screen.getByTestId('set-write-gate-form')).toBeInTheDocument();
    });

    // Select read_only_session
    const select = screen.getByLabelText(/选择目标门禁策略/);
    fireEvent.change(select, { target: { value: 'read_only_session' } });

    // Submit policy change
    const applyBtn = screen.getByTestId('btn-apply-write-policy');
    fireEvent.click(applyBtn);

    await waitFor(() => {
      expect(mockSetWriteGatePolicy).toHaveBeenCalledWith(
        expect.objectContaining({
          policy: 'read_only_session',
        })
      );
    });

    // HUD policy should reflect updated policy
    expect(screen.getByTestId('hud-active-policy')).toHaveTextContent('READ_ONLY_SESSION');
  });

  it('refreshes reconciliation stats when clicking the refresh button', async () => {
    render(<DiskMemoryReconciliationCard />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /刷新/ })).toBeInTheDocument();
    });

    const refreshBtn = screen.getByRole('button', { name: /刷新/ });
    fireEvent.click(refreshBtn);

    await waitFor(() => {
      expect(mockGetReconciliationStats).toHaveBeenCalledTimes(2);
      expect(mockCheckWriteGate).toHaveBeenCalledTimes(2);
    });
  });

  it('gracefully degrades to fallback state on API failure', async () => {
    mockGetReconciliationStats.mockRejectedValue(new Error('Network error'));
    mockCheckWriteGate.mockRejectedValue(new Error('Network error'));

    render(<DiskMemoryReconciliationCard />);

    await waitFor(() => {
      expect(screen.getByText('磁盘文件与 FTS5 双向对账及显式写入门禁套件')).toBeInTheDocument();
    });

    // Fallback counts should be rendered
    expect(screen.getByTestId('hud-total-indexed')).toHaveTextContent('12');
    expect(screen.getByTestId('hud-active-policy')).toHaveTextContent('ENABLED');
  });
});
