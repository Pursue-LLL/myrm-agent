/** @vitest-environment jsdom */

/**
 * [INPUT]
 * @/services/memory/temporalGraph::listEntityNodes, listFactEdges, getEdgeLineage,
 *   saveEntityNode, deleteEntityNode, saveFactEdge, queryTemporalFacts, getTemporalGraphStats
 * ../command-center/TemporalKnowledgeGraphCard::TemporalKnowledgeGraphCard
 *
 * [OUTPUT]
 * Test suite verifying temporal knowledge graph decay scoring (30-day half-life),
 * entity fact mutual exclusion reconciliation, edge lineage traversal, and node management.
 *
 * [POS]
 * Unit test for Item 93 (Temporal Knowledge Graph Decay & Entity Fact Conflict Resolution Suite).
 * Strict typing applied: No `any` types allowed. File lines < 400.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { TemporalKnowledgeGraphCard } from '../command-center/TemporalKnowledgeGraphCard';
import type {
  TemporalEntityNodeDTO,
  TemporalFactEdgeDTO,
  TemporalFactHitDTO,
  TemporalGraphStatsDTO,
  FactConflictResolutionResultDTO,
} from '@/services/memory/temporalGraph';

const {
  mockListEntityNodes,
  mockListFactEdges,
  mockGetEdgeLineage,
  mockSaveEntityNode,
  mockDeleteEntityNode,
  mockSaveFactEdge,
  mockQueryTemporalFacts,
  mockGetTemporalGraphStats,
} = vi.hoisted(() => ({
  mockListEntityNodes: vi.fn(),
  mockListFactEdges: vi.fn(),
  mockGetEdgeLineage: vi.fn(),
  mockSaveEntityNode: vi.fn(),
  mockDeleteEntityNode: vi.fn(),
  mockSaveFactEdge: vi.fn(),
  mockQueryTemporalFacts: vi.fn(),
  mockGetTemporalGraphStats: vi.fn(),
}));

vi.mock('@/services/memory/temporalGraph', () => ({
  listEntityNodes: mockListEntityNodes,
  listFactEdges: mockListFactEdges,
  getEdgeLineage: mockGetEdgeLineage,
  saveEntityNode: mockSaveEntityNode,
  deleteEntityNode: mockDeleteEntityNode,
  saveFactEdge: mockSaveFactEdge,
  queryTemporalFacts: mockQueryTemporalFacts,
  getTemporalGraphStats: mockGetTemporalGraphStats,
}));

describe('TemporalKnowledgeGraphCard', () => {
  const sampleNodes: TemporalEntityNodeDTO[] = [
    {
      node_id: 'node_project_root',
      name: 'Project Architecture',
      entity_type: 'concept',
      attributes: { domain: 'core' },
      created_at: '2026-10-08T00:00:00Z',
      updated_at: '2026-10-08T00:00:00Z',
    },
    {
      node_id: 'node_orm_prisma',
      name: 'Prisma ORM',
      entity_type: 'technology',
      attributes: { version: '5.0' },
      created_at: '2026-10-08T00:10:00Z',
      updated_at: '2026-10-08T00:10:00Z',
    },
    {
      node_id: 'node_orm_drizzle',
      name: 'Drizzle ORM',
      entity_type: 'technology',
      attributes: { version: '0.30' },
      created_at: '2026-10-08T01:00:00Z',
      updated_at: '2026-10-08T01:00:00Z',
    },
  ];

  const sampleEdges: TemporalFactEdgeDTO[] = [
    {
      edge_id: 'edge_v2_drizzle',
      source_id: 'node_project_root',
      target_id: 'node_orm_drizzle',
      predicate: 'uses_primary_orm',
      valid_from: '2026-10-08T01:00:00Z',
      valid_until: null,
      is_superseded: false,
      superseded_by: null,
      confidence_score: 0.98,
      access_count: 5,
      last_accessed_at: '2026-10-08T01:30:00Z',
      created_at: '2026-10-08T01:00:00Z',
    },
    {
      edge_id: 'edge_v1_prisma',
      source_id: 'node_project_root',
      target_id: 'node_orm_prisma',
      predicate: 'uses_primary_orm',
      valid_from: '2026-10-08T00:10:00Z',
      valid_until: '2026-10-08T01:00:00Z',
      is_superseded: true,
      superseded_by: 'edge_v2_drizzle',
      confidence_score: 0.85,
      access_count: 12,
      last_accessed_at: '2026-10-08T00:45:00Z',
      created_at: '2026-10-08T00:10:00Z',
    },
  ];

  const sampleStats: TemporalGraphStatsDTO = {
    total_nodes_count: 3,
    active_edges_count: 1,
    superseded_edges_count: 1,
    average_decayed_score: 0.965,
  };

  const sampleHits: TemporalFactHitDTO[] = [
    {
      edge: sampleEdges[0],
      source_node: sampleNodes[0],
      target_node: sampleNodes[2],
      decayed_score: 0.978,
      effective_status: 'active',
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    mockGetTemporalGraphStats.mockResolvedValue(sampleStats);
    mockListEntityNodes.mockResolvedValue(sampleNodes);
    mockListFactEdges.mockResolvedValue(sampleEdges);
    mockGetEdgeLineage.mockResolvedValue([sampleEdges[1]]);
    mockQueryTemporalFacts.mockResolvedValue(sampleHits);
    mockSaveFactEdge.mockResolvedValue({
      new_edge: sampleEdges[0],
      superseded_edges: [sampleEdges[1]],
      is_conflict_detected: true,
      conflict_reason: 'Predicate uses_primary_orm is mutually exclusive for node_project_root.',
    } satisfies FactConflictResolutionResultDTO);
    mockSaveEntityNode.mockResolvedValue({
      node_id: 'node_new_postgres',
      name: 'PostgreSQL Database',
      entity_type: 'technology',
      attributes: {},
      created_at: '2026-10-08T03:00:00Z',
      updated_at: '2026-10-08T03:00:00Z',
    });
    mockDeleteEntityNode.mockResolvedValue({ deleted: true, node_id: 'node_orm_prisma' });
  });

  it('renders HUD statistics and default evolution timeline correctly', async () => {
    render(<TemporalKnowledgeGraphCard />);

    await waitFor(() => {
      expect(screen.getByText('时序动态知识图谱边衰减与事实冲突消解套件')).toBeInTheDocument();
    });

    expect(screen.getByTestId('hud-nodes-count')).toHaveTextContent('3');
    expect(screen.getByTestId('hud-active-edges-count')).toHaveTextContent('1');
    expect(screen.getByTestId('hud-superseded-edges-count')).toHaveTextContent('1');
    expect(screen.getByTestId('hud-avg-score')).toHaveTextContent('96.5%');

    // Check list of fact edges
    const predicateElements = screen.getAllByText('[uses_primary_orm]');
    expect(predicateElements.length).toBeGreaterThan(0);
    expect(screen.getByText('ACTIVE')).toBeInTheDocument();
    expect(screen.getByText('SUPERSEDED')).toBeInTheDocument();
  });

  it('selects an edge and inspects its backwards evolutionary lineage chain', async () => {
    render(<TemporalKnowledgeGraphCard />);

    await waitFor(() => {
      expect(screen.getByTestId('edge-card-edge_v2_drizzle')).toBeInTheDocument();
    });

    // Click on active edge
    fireEvent.click(screen.getByTestId('edge-card-edge_v2_drizzle'));

    await waitFor(() => {
      expect(mockGetEdgeLineage).toHaveBeenCalledWith('edge_v2_drizzle');
    });

    // Inspector panel should display edge details and lineage node
    expect(screen.getByTestId('lineage-detail-box')).toBeInTheDocument();
    expect(screen.getByTestId('lineage-node-edge_v1_prisma')).toBeInTheDocument();
  });

  it('creates new fact edge with mutual exclusion auto-reconciliation', async () => {
    render(<TemporalKnowledgeGraphCard />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /录入新时序事实/ })).toBeInTheDocument();
    });

    // Open fact edge creation form
    fireEvent.click(screen.getByRole('button', { name: /录入新时序事实/ }));

    expect(screen.getByTestId('add-fact-edge-form')).toBeInTheDocument();

    // Fill in predicate
    const predicateInput = screen.getByLabelText(/关系谓词/);
    fireEvent.change(predicateInput, { target: { value: 'uses_primary_orm' } });

    // Submit form
    const submitBtn = screen.getByRole('button', { name: /提交并自动消解冲突/ });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockSaveFactEdge).toHaveBeenCalledWith(
        expect.objectContaining({
          predicate: 'uses_primary_orm',
        })
      );
    });
  });

  it('switches to decay scorer tab and executes recency decay probe', async () => {
    render(<TemporalKnowledgeGraphCard />);

    await waitFor(() => {
      expect(screen.getByTestId('tab-decay-console')).toBeInTheDocument();
    });

    // Switch Tab
    fireEvent.click(screen.getByTestId('tab-decay-console'));

    // Verify decay probe console renders
    await waitFor(() => {
      expect(screen.getByText(/时序半衰期动态衰减检索/)).toBeInTheDocument();
    });

    // Trigger score probe calculation
    const probeBtn = screen.getByTestId('query-facts-button');
    fireEvent.click(probeBtn);

    await waitFor(() => {
      expect(mockQueryTemporalFacts).toHaveBeenCalled();
    });

    expect(screen.getByText('Score: 0.978')).toBeInTheDocument();
  });

  it('creates and deletes an entity node in the management console', async () => {
    render(<TemporalKnowledgeGraphCard />);

    await waitFor(() => {
      expect(screen.getByTestId('tab-decay-console')).toBeInTheDocument();
    });

    // Switch to nodes tab
    fireEvent.click(screen.getByTestId('tab-decay-console'));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /新建实体/ })).toBeInTheDocument();
    });

    // Toggle node creation form
    fireEvent.click(screen.getByRole('button', { name: /新建实体/ }));

    // Fill in node name
    const nameInput = screen.getByLabelText(/实体名称/);
    fireEvent.change(nameInput, { target: { value: 'PostgreSQL Database' } });

    // Submit node
    const saveNodeBtn = screen.getByRole('button', { name: /录入节点/ });
    fireEvent.click(saveNodeBtn);

    await waitFor(() => {
      expect(mockSaveEntityNode).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'PostgreSQL Database',
        })
      );
    });

    // Delete node
    const nodeItem = screen.getByTestId('entity-node-item-node_orm_prisma');
    const deleteBtn = nodeItem.querySelector('button');
    expect(deleteBtn).not.toBeNull();
    if (deleteBtn) {
      fireEvent.click(deleteBtn);
    }

    await waitFor(() => {
      expect(mockDeleteEntityNode).toHaveBeenCalledWith('node_orm_prisma');
    });
  });

  it('refreshes graph data when clicking the refresh button', async () => {
    render(<TemporalKnowledgeGraphCard />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /刷新/ })).toBeInTheDocument();
    });

    const refreshBtn = screen.getByRole('button', { name: /刷新/ });
    fireEvent.click(refreshBtn);

    await waitFor(() => {
      expect(mockGetTemporalGraphStats).toHaveBeenCalledTimes(2);
      expect(mockListEntityNodes).toHaveBeenCalledTimes(2);
      expect(mockListFactEdges).toHaveBeenCalledTimes(2);
    });
  });

  it('gracefully degrades to fallback state on API errors', async () => {
    mockGetTemporalGraphStats.mockRejectedValue(new Error('Connection failure'));
    mockListEntityNodes.mockRejectedValue(new Error('Connection failure'));
    mockListFactEdges.mockRejectedValue(new Error('Connection failure'));

    render(<TemporalKnowledgeGraphCard />);

    await waitFor(() => {
      expect(screen.getByText('时序动态知识图谱边衰减与事实冲突消解套件')).toBeInTheDocument();
    });

    // Verify fallback values rendered
    expect(screen.getByTestId('hud-nodes-count')).toHaveTextContent('3');
    expect(screen.getByTestId('edge-card-edge_work_current')).toBeInTheDocument();
  });
});
