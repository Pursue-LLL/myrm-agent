/** @vitest-environment jsdom */

/**
 * [INPUT]
 * @/services/memory::getCubeMatrixOverview, listCubeRecords, createMemoryCube,
 *                    setAgentMountPolicy, queryCubesFederated, writeCubeMemory
 * ../command-center/MemoryCubeStudioCard::MemoryCubeStudioCard
 *
 * [OUTPUT]
 * Test suite verifying Memory Cube Scoped Isolation Studio Card (Item 124 P0):
 * 1. Default render of header, HUD metrics bar and Active Cubes count
 * 2. Spatial Matrix tab filtering and cube selection
 * 3. Inspecting cube records in the detail pane
 * 4. Mount topology agent policy tuning
 * 5. Write barrier probe testing
 * 6. Federated query execution verification
 *
 * [POS]
 * Unit tests for Item 124.
 * Strict typing applied: No `any` types allowed. Single file < 250 lines.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { MemoryCubeStudioCard } from '../command-center/MemoryCubeStudioCard';
import {
  FALLBACK_CUBE_MATRIX_OVERVIEW,
  FALLBACK_SAMPLE_RECORDS,
} from '../command-center/memCubeFallbacks';

const {
  mockGetCubeMatrixOverview,
  mockListCubeRecords,
  mockCreateMemoryCube,
  mockSetAgentMountPolicy,
  mockQueryCubesFederated,
  mockWriteCubeMemory,
} = vi.hoisted(() => ({
  mockGetCubeMatrixOverview: vi.fn(),
  mockListCubeRecords: vi.fn(),
  mockCreateMemoryCube: vi.fn(),
  mockSetAgentMountPolicy: vi.fn(),
  mockQueryCubesFederated: vi.fn(),
  mockWriteCubeMemory: vi.fn(),
}));

vi.mock('@/services/memory', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    getCubeMatrixOverview: mockGetCubeMatrixOverview,
    listCubeRecords: mockListCubeRecords,
    createMemoryCube: mockCreateMemoryCube,
    setAgentMountPolicy: mockSetAgentMountPolicy,
    queryCubesFederated: mockQueryCubesFederated,
    writeCubeMemory: mockWriteCubeMemory,
  };
});

describe('MemoryCubeStudioCard (Item 124 P0)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetCubeMatrixOverview.mockResolvedValue(FALLBACK_CUBE_MATRIX_OVERVIEW);
    mockListCubeRecords.mockImplementation((cubeId: string) =>
      Promise.resolve(FALLBACK_SAMPLE_RECORDS[cubeId] || [])
    );
    mockCreateMemoryCube.mockImplementation((payload) =>
      Promise.resolve({
        cube_id: 'cube-new-test',
        name: payload.name,
        scope_type: payload.scope_type,
        owner_id: null,
        description: payload.description || '',
        is_read_only: payload.is_read_only || false,
        item_count: 0,
        created_at: 1775604000,
        updated_at: 1775604000,
      })
    );
    mockSetAgentMountPolicy.mockImplementation((agentId: string, payload) =>
      Promise.resolve({
        agent_id: agentId,
        ...payload,
      })
    );
    mockWriteCubeMemory.mockResolvedValue({
      success: true,
      destination_cube_id: 'cube-agent-architect-private',
      record: {
        record_id: 'rec-test-1',
        cube_id: 'cube-agent-architect-private',
        content: 'Test committed note',
        metadata: {},
        created_at: 1775604100,
      },
    });
    mockQueryCubesFederated.mockResolvedValue({
      items: [
        {
          record_id: 'rec-glob-1',
          cube_id: 'cube-global-shared',
          content: 'Rule 1: Always enforce clean architecture and zero any types.',
          metadata: {},
          created_at: 1775600100,
        },
      ],
      total_found: 1,
      queried_cube_ids: ['cube-global-shared'],
      query_duration_ms: 8.5,
    });
  });

  it('renders studio header, telemetry HUD metrics, and initial cubes list', async () => {
    render(<MemoryCubeStudioCard />);

    await waitFor(() => {
      expect(
        screen.getByRole('heading', {
          name: /Memory Cube Scoped Isolation & Dynamic Mounting Studio/i,
        })
      ).toBeInTheDocument();
    });

    // Check HUD telemetry metrics
    expect(screen.getByText('Active Cubes')).toBeInTheDocument();
    expect(screen.getByText('Memory Records')).toBeInTheDocument();
    expect(screen.getByText('Mount Topologies')).toBeInTheDocument();
    expect(screen.getByText('Strict Isolation Active')).toBeInTheDocument();

    // Verify presence of seeded cubes
    expect(screen.getAllByText('Global Core Principles').length).toBeGreaterThan(0);
    expect(screen.getAllByText('OpenPerplexity Workspace').length).toBeGreaterThan(0);
  });

  it('filters memory cubes by scope tab', async () => {
    render(<MemoryCubeStudioCard />);

    await waitFor(() => {
      expect(screen.getAllByText('Global Core Principles').length).toBeGreaterThan(0);
    });

    // Click Workspace filter
    const workspaceFilter = screen.getByRole('button', { name: /^Workspace$/i });
    fireEvent.click(workspaceFilter);

    // Workspace cube stays in list
    expect(screen.getAllByText('OpenPerplexity Workspace').length).toBeGreaterThan(0);

    // Click All filter to restore
    const allFilter = screen.getByRole('button', { name: /^All$/i });
    fireEvent.click(allFilter);
    expect(screen.getAllByText('Global Core Principles').length).toBeGreaterThan(0);
  });

  it('switches active cube and loads corresponding records', async () => {
    render(<MemoryCubeStudioCard />);

    await waitFor(() => {
      expect(screen.getAllByText('Global Core Principles').length).toBeGreaterThan(0);
    });

    // Click Workspace cube
    const workspaceCubeBtns = screen.getAllByText('OpenPerplexity Workspace');
    fireEvent.click(workspaceCubeBtns[0]);

    await waitFor(() => {
      expect(mockListCubeRecords).toHaveBeenCalledWith('cube-proj-open-perplexity');
    });
  });

  it('executes write barrier probe test and renders outcome', async () => {
    render(<MemoryCubeStudioCard />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Dispatch Write Probe/i })).toBeInTheDocument();
    });

    const probeBtn = screen.getByRole('button', { name: /Dispatch Write Probe/i });
    fireEvent.click(probeBtn);

    await waitFor(() => {
      expect(mockWriteCubeMemory).toHaveBeenCalled();
      expect(screen.getByText(/Write Authorized & Committed/i)).toBeInTheDocument();
    });
  });

  it('executes federated query probe test and displays hits', async () => {
    render(<MemoryCubeStudioCard />);

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: /Execute Federated Query/i })
      ).toBeInTheDocument();
    });

    const queryBtn = screen.getByRole('button', { name: /Execute Federated Query/i });
    fireEvent.click(queryBtn);

    await waitFor(() => {
      expect(mockQueryCubesFederated).toHaveBeenCalled();
      expect(screen.getByText(/Found 1 hits/i)).toBeInTheDocument();
    });
  });

  it('toggles strict isolation in mount policy tuner', async () => {
    render(<MemoryCubeStudioCard />);

    await waitFor(() => {
      expect(screen.getByLabelText(/Enforce Strict Cross-Talk Blocking/i)).toBeInTheDocument();
    });

    const checkbox = screen.getByLabelText(/Enforce Strict Cross-Talk Blocking/i);
    fireEvent.click(checkbox);

    await waitFor(() => {
      expect(mockSetAgentMountPolicy).toHaveBeenCalled();
    });
  });
});
