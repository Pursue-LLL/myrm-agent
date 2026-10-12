/** @vitest-environment jsdom */

/**
 * [INPUT]
 * @/services/memory::(getLineageStats, getGraphTopology, traceNodeLineage, triggerReorganizationPass, revertMemoryVersion)
 * ../command-center/MemoryLineageStudioCard::MemoryLineageStudioCard
 *
 * [OUTPUT]
 * Test suite verifying Memory Lineage and Graph Reorganization Studio Card (Item 126 P1):
 * 1. Default render of HUD metrics bar, topology node list, and multi-relational edges
 * 2. Filtering nodes by status (All / Active / Superseded)
 * 3. Triggering automated graph reorganization pass and displaying batch result
 * 4. Tracing a node's white-box lineage DAG trail with evolutionary steps
 * 5. Reverting active state to historical version snapshot
 *
 * [POS]
 * Unit tests for Item 126.
 * Strict typing applied: Zero `any` types. Single file < 250 lines.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { MemoryLineageStudioCard } from '../command-center/MemoryLineageStudioCard';
import {
  FALLBACK_LINEAGE_STATS,
  FALLBACK_TOPOLOGY_GRAPH,
  FALLBACK_LINEAGE_TRAIL,
  FALLBACK_REORGANIZATION_REPORT,
} from '../command-center/memoryLineageFallbacks';

const {
  mockGetLineageStats,
  mockGetGraphTopology,
  mockTraceNodeLineage,
  mockTriggerReorganizationPass,
  mockRevertMemoryVersion,
} = vi.hoisted(() => ({
  mockGetLineageStats: vi.fn(),
  mockGetGraphTopology: vi.fn(),
  mockTraceNodeLineage: vi.fn(),
  mockTriggerReorganizationPass: vi.fn(),
  mockRevertMemoryVersion: vi.fn(),
}));

vi.mock('@/services/memory', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    getLineageStats: mockGetLineageStats,
    getGraphTopology: mockGetGraphTopology,
    traceNodeLineage: mockTraceNodeLineage,
    triggerReorganizationPass: mockTriggerReorganizationPass,
    revertMemoryVersion: mockRevertMemoryVersion,
  };
});

describe('MemoryLineageStudioCard (Item 126 P1)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetLineageStats.mockResolvedValue(FALLBACK_LINEAGE_STATS);
    mockGetGraphTopology.mockResolvedValue(FALLBACK_TOPOLOGY_GRAPH);
    mockTraceNodeLineage.mockResolvedValue(FALLBACK_LINEAGE_TRAIL);
    mockTriggerReorganizationPass.mockResolvedValue(FALLBACK_REORGANIZATION_REPORT);
    mockRevertMemoryVersion.mockResolvedValue({
      reverted_node: FALLBACK_TOPOLOGY_GRAPH.nodes[1],
      restored_active_node: {
        ...FALLBACK_TOPOLOGY_GRAPH.nodes[0],
        node_id: 'mem_pref_coffee_v3',
        status: 'active',
        version: 3,
      },
    });
  });

  it('renders HUD bar with correct metrics and topology columns', async () => {
    render(<MemoryLineageStudioCard />);

    await waitFor(() => {
      expect(mockGetLineageStats).toHaveBeenCalled();
      expect(mockGetGraphTopology).toHaveBeenCalled();
    });

    expect(screen.getByText(/Memory Lineage & Reorganization/i)).toBeInTheDocument();
    expect(screen.getByText(/Active: 4 \/ 5/i)).toBeInTheDocument();
    expect(screen.getByText(/Superseded: 1/i)).toBeInTheDocument();
    expect(screen.getByText(/Edges: 4/i)).toBeInTheDocument();
    expect(screen.getByText(/Depth: v2/i)).toBeInTheDocument();

    // Verify presence of nodes
    expect(screen.getByText('User prefers hot black americano with zero sugar for work mornings.')).toBeInTheDocument();
    expect(screen.getByText('User switched to iced oat latte due to mild stomach discomfort with black coffee.')).toBeInTheDocument();

    // Verify presence of edges
    expect(screen.getByText('supersedes')).toBeInTheDocument();
    expect(screen.getByText('subsumption')).toBeInTheDocument();
  });

  it('filters memory nodes by status', async () => {
    render(<MemoryLineageStudioCard />);

    await waitFor(() => {
      expect(screen.getByText('User prefers hot black americano with zero sugar for work mornings.')).toBeInTheDocument();
    });

    // Filter to Active only
    const activeFilterBtn = screen.getByRole('button', { name: /Active \(3\)/i });
    fireEvent.click(activeFilterBtn);

    // Superseded node should no longer be displayed in node list
    expect(screen.queryByText('User prefers hot black americano with zero sugar for work mornings.')).not.toBeInTheDocument();
    expect(screen.getByText('User switched to iced oat latte due to mild stomach discomfort with black coffee.')).toBeInTheDocument();

    // Filter to Superseded only
    const supersededFilterBtn = screen.getByRole('button', { name: /Superseded \(1\)/i });
    fireEvent.click(supersededFilterBtn);

    expect(screen.getByText('User prefers hot black americano with zero sugar for work mornings.')).toBeInTheDocument();
    expect(screen.queryByText('User switched to iced oat latte due to mild stomach discomfort with black coffee.')).not.toBeInTheDocument();
  });

  it('triggers reorganization pass and displays batch report', async () => {
    render(<MemoryLineageStudioCard />);

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: /Execute graph reorganization pass/i })
      ).toBeInTheDocument();
    });

    const executeBtn = screen.getByRole('button', {
      name: /Execute graph reorganization pass/i,
    });
    fireEvent.click(executeBtn);

    await waitFor(() => {
      expect(mockTriggerReorganizationPass).toHaveBeenCalled();
    });

    expect(screen.getByText(/Batch Execution Succeeded: reorg_demo_98af/i)).toBeInTheDocument();
    expect(screen.getByText('Synthesized Edges')).toBeInTheDocument();
  });

  it('opens white-box lineage trail inspector and executes historical reversion', async () => {
    render(<MemoryLineageStudioCard />);

    await waitFor(() => {
      expect(screen.getAllByRole('button', { name: /^Trace$/i }).length).toBeGreaterThan(0);
    });

    // Click trace on the second node
    const traceButtons = screen.getAllByRole('button', { name: /^Trace$/i });
    fireEvent.click(traceButtons[1]);

    await waitFor(() => {
      expect(mockTraceNodeLineage).toHaveBeenCalledWith('mem_pref_coffee_v2');
      expect(screen.getByRole('region', { name: /White-box Lineage DAG Audit Inspector/i })).toBeInTheDocument();
    });

    expect(screen.getByText(/Lineage Trail Trace: User/i)).toBeInTheDocument();
    expect(screen.getByText('Step #1: v1')).toBeInTheDocument();
    expect(screen.getByText('Step #2: v2')).toBeInTheDocument();

    // Check ancestor rollback card
    expect(screen.getByText('v1 Snapshot')).toBeInTheDocument();
    const revertBtn = screen.getByRole('button', { name: /Revert to this/i });
    fireEvent.click(revertBtn);

    await waitFor(() => {
      expect(mockRevertMemoryVersion).toHaveBeenCalledWith({
        historical_node_id: 'mem_pref_coffee_v1',
        rationale: 'Rollback triggered via WebUI Studio audit inspector',
      });
    });

    expect(screen.getByText(/Successfully restored historical version. New active node: mem_pref_coffee_v3./i)).toBeInTheDocument();
  });
});
