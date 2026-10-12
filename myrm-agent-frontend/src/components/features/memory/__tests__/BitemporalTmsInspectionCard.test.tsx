/** @vitest-environment jsdom */

/**
 * Test suite verifying Item 148 TemporalTruthMaintenanceFilterSuite:
 * 1. Default render of bitemporal TMS card with header, badges, and dual-interval records.
 * 2. Displays active justification links and causal distance on inference tab.
 * 3. Triggers simulated retraction of premise, cascading active support invalidation.
 * 4. Switches to non-destructive retraction tab and verifies physical preservation message.
 * 5. Switches to truth maintenance snapshot tab and renders quad-partition matrix.
 * 6. Handles API errors gracefully via offline simulation fallback.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { BitemporalTmsInspectionCard } from '../command-center/BitemporalTmsInspectionCard';
import type {
  SnapshotResponse,
  TemporalQueryResponse,
  RetractRecordResponse,
} from '@/services/memory/bitemporalTms';

const {
  mockRecordFact,
  mockDeriveInference,
  mockRetractRecord,
  mockQueryActive,
  mockProjectSnapshot,
  mockGetHealth,
} = vi.hoisted(() => ({
  mockRecordFact: vi.fn(),
  mockDeriveInference: vi.fn(),
  mockRetractRecord: vi.fn(),
  mockQueryActive: vi.fn(),
  mockProjectSnapshot: vi.fn(),
  mockGetHealth: vi.fn(),
}));

vi.mock('@/services/memory/bitemporalTms', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    bitemporalTmsApi: {
      recordFact: mockRecordFact,
      deriveInference: mockDeriveInference,
      retractRecord: mockRetractRecord,
      queryActive: mockQueryActive,
      projectSnapshot: mockProjectSnapshot,
      getHealth: mockGetHealth.mockResolvedValue({
        status: 'ok',
        module: 'bitemporal_truth_maintenance',
        version: '1.0.0',
      }),
    },
  };
});

describe('BitemporalTmsInspectionCard (Item 148 P1)', () => {
  const sampleQueryRes: TemporalQueryResponse = {
    total: 2,
    as_of_valid_time: 1500.0,
    as_of_known_time: 1500.0,
    records: [
      {
        evidence_id: 'fact-org-domain',
        content: 'Primary production domain is api.vortexai.internal',
        evidence_type: 'fact',
        bitemporal: {
          valid_interval: { start: 1000.0, end: null },
          known_interval: { start: 1050.0, end: null },
        },
        confidence: 0.98,
        metadata: { source: 'dns_config' },
      },
      {
        evidence_id: 'fact-sre-lead',
        content: 'User is designated principal infrastructure SRE',
        evidence_type: 'fact',
        bitemporal: {
          valid_interval: { start: 1200.0, end: 2400.0 },
          known_interval: { start: 1210.0, end: null },
        },
        confidence: 0.95,
        metadata: { source: 'org_chart' },
      },
    ],
  };

  const sampleSnapshotRes: SnapshotResponse = {
    as_of_valid_time: 1500.0,
    as_of_known_time: 1500.0,
    total_count: 4,
    active_evidences: [
      {
        evidence_id: 'fact-active-1',
        content: 'Cluster active on AWS us-east-1',
        evidence_type: 'fact',
        bitemporal: {
          valid_interval: { start: 1000.0, end: null },
          known_interval: { start: 1000.0, end: null },
        },
        confidence: 1.0,
        metadata: {},
      },
    ],
    retracted_evidences: [
      {
        evidence_id: 'fact-retracted-1',
        content: 'Staging endpoint staging.vortexai.internal',
        evidence_type: 'fact',
        bitemporal: {
          valid_interval: { start: 500.0, end: null },
          known_interval: { start: 500.0, end: 1200.0 },
        },
        confidence: 1.0,
        metadata: {},
      },
    ],
    active_inferences: [
      {
        evidence_id: 'inf-active-1',
        content: 'Traffic routing directed to us-east-1 mesh',
        evidence_type: 'inference',
        bitemporal: {
          valid_interval: { start: 1000.0, end: null },
          known_interval: { start: 1000.0, end: null },
        },
        confidence: 0.95,
        metadata: { causal_distance: '1' },
      },
    ],
    invalidated_inferences: [
      {
        evidence_id: 'inf-invalid-1',
        content: 'Traffic routing directed to legacy staging mesh',
        evidence_type: 'inference',
        bitemporal: {
          valid_interval: { start: 500.0, end: null },
          known_interval: { start: 500.0, end: null },
        },
        confidence: 0.9,
        metadata: { causal_distance: '1' },
      },
    ],
  };

  const sampleRetractRes: RetractRecordResponse = {
    success: true,
    evidence_id: 'fact-clearance',
    retracted_at: 100.0,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockQueryActive.mockResolvedValue(sampleQueryRes);
    mockProjectSnapshot.mockResolvedValue(sampleSnapshotRes);
    mockRetractRecord.mockResolvedValue(sampleRetractRes);
  });

  it('1. renders header, badges, and dual bitemporal intervals by default', async () => {
    render(<BitemporalTmsInspectionCard />);

    expect(screen.getByText('Temporal Truth Maintenance & Bitemporal Filter Suite')).toBeInTheDocument();
    expect(screen.getByText('Item 148 · Semantica TMS')).toBeInTheDocument();
    expect(screen.getByText('Active Support Guard')).toBeInTheDocument();

    await waitFor(() => {
      expect(mockQueryActive).toHaveBeenCalled();
    });

    expect(await screen.findByText('Primary production domain is api.vortexai.internal')).toBeInTheDocument();
    expect(screen.getByText('User is designated principal infrastructure SRE')).toBeInTheDocument();
  });

  it('2. switches to justification cascade tab and demonstrates active inference support', async () => {
    render(<BitemporalTmsInspectionCard />);

    const cascadeTabBtn = screen.getByRole('button', { name: /因果推论与真值维护/ });
    fireEvent.click(cascadeTabBtn);

    await waitFor(() => {
      expect(mockQueryActive).toHaveBeenCalled();
    });

    expect(await screen.findByText(/推论持有完备支撑/)).toBeInTheDocument();
    expect(screen.getByText(/前驱事实有效 · 推论活跃/)).toBeInTheDocument();
  });

  it('3. triggers non-destructive retraction of premise, cascading active support invalidation', async () => {
    render(<BitemporalTmsInspectionCard />);

    const cascadeTabBtn = screen.getByRole('button', { name: /因果推论与真值维护/ });
    fireEvent.click(cascadeTabBtn);

    const retractBtn = await screen.findByRole('button', { name: /模拟撤回前驱事实/ });
    fireEvent.click(retractBtn);

    await waitFor(() => {
      expect(mockRetractRecord).toHaveBeenCalledWith({
        evidence_id: 'fact-clearance',
        retracted_at: 100.0,
      });
    });

    expect(await screen.findByText(/前驱凭据已执行非破坏性撤回/)).toBeInTheDocument();
    expect(screen.getByText(/前驱凭据已撤回 · 推论自动失效/)).toBeInTheDocument();
  });

  it('4. switches to non-destructive retraction tab and verifies physical audit trail', async () => {
    render(<BitemporalTmsInspectionCard />);

    const retractTabBtn = screen.getByRole('button', { name: /非破坏性撤回对比/ });
    fireEvent.click(retractTabBtn);

    await waitFor(() => {
      expect(mockQueryActive).toHaveBeenCalled();
    });

    expect(await screen.findByText('0 物理删除 · 完整审计链')).toBeInTheDocument();
    expect(screen.getByText(/时态穿梭审计/)).toBeInTheDocument();
  });

  it('5. switches to truth maintenance snapshot tab and renders quad-partition matrix', async () => {
    render(<BitemporalTmsInspectionCard />);

    const snapshotTabBtn = screen.getByRole('button', { name: /真值维护快照投影/ });
    fireEvent.click(snapshotTabBtn);

    await waitFor(() => {
      expect(mockProjectSnapshot).toHaveBeenCalled();
    });

    expect(await screen.findByText(/真值维护四分快照矩阵/)).toBeInTheDocument();
    expect(screen.getByText('总实体数: 4')).toBeInTheDocument();
    expect(screen.getByText(/活跃基础事实/)).toBeInTheDocument();
    expect(screen.getByText(/已撤回基础事实/)).toBeInTheDocument();
    expect(screen.getByText(/活跃有效推论/)).toBeInTheDocument();
    expect(screen.getByText(/级联失效推论/)).toBeInTheDocument();
  });

  it('6. handles API errors gracefully via offline simulation fallback', async () => {
    mockQueryActive.mockRejectedValueOnce(new Error('Network error'));
    render(<BitemporalTmsInspectionCard />);

    // Should fall back to mock offline query result without crashing
    expect(await screen.findByText('Primary production domain is api.vortexai.internal')).toBeInTheDocument();
  });
});
