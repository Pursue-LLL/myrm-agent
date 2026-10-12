/** @vitest-environment jsdom */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { GraphRRFRetrievalCard } from '../command-center/GraphRRFRetrievalCard';

const {
  mockSearchDualChannelRRF,
  mockTraverseKnowledgeGraph,
  mockCreateEntityNode,
} = vi.hoisted(() => ({
  mockSearchDualChannelRRF: vi.fn(),
  mockTraverseKnowledgeGraph: vi.fn(),
  mockCreateEntityNode: vi.fn(),
}));

vi.mock('@/services/memory/graphRrf', () => ({
  searchDualChannelRRF: mockSearchDualChannelRRF,
  traverseKnowledgeGraph: mockTraverseKnowledgeGraph,
  createEntityNode: mockCreateEntityNode,
}));

describe('GraphRRFRetrievalCard', () => {
  const mockSearchResult = {
    query: 'Titan authorization architecture',
    total_hits: 2,
    results: [
      {
        memory_id: 'mem_auth_spec',
        content: 'OAuth2 token validation guidelines designed by Alice.',
        fused_score: 0.0325,
        vector_rank: 1,
        graph_rank: 1,
        hit_sources: ['vector', 'graph'],
        explanation: {
          vector_rrf: 0.016393,
          graph_rrf: 0.016129,
        },
      },
      {
        memory_id: 'mem_titan_plan',
        content: 'Project Titan roadmap for distributed authorization.',
        fused_score: 0.0161,
        vector_rank: null,
        graph_rank: 2,
        hit_sources: ['graph'],
        explanation: {
          graph_rrf: 0.016129,
        },
      },
    ],
  };

  const mockTraverseResult = {
    nodes: [
      {
        id: 'person:alice',
        name: 'Alice',
        entity_type: 'PERSON',
        properties: {},
        created_at: 1728300000,
      },
      {
        id: 'project:titan',
        name: 'Project Titan',
        entity_type: 'PROJECT',
        properties: {},
        created_at: 1728300000,
      },
    ],
    edges: [
      {
        id: 'edge:alice-leads-titan',
        source_id: 'person:alice',
        target_id: 'project:titan',
        relation_type: 'leads',
        weight: 1.0,
        properties: {},
        created_at: 1728300000,
      },
    ],
    paths: [
      {
        source_id: 'person:alice',
        target_id: 'project:titan',
        relation_type: 'leads',
        depth: 1,
      },
    ],
    associated_memory_ids: ['mem_auth_spec', 'mem_titan_plan'],
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders GraphRRFRetrievalCard with initial inputs and badges', () => {
    render(<GraphRRFRetrievalCard />);

    expect(
      screen.getByText(/知识图谱与语义向量双路检索 RRF 融合引擎/i),
    ).toBeInTheDocument();
    expect(screen.getByText('gbrain 架构演进')).toBeInTheDocument();
    expect(screen.getByText('RRF 倒数排名融合')).toBeInTheDocument();
    expect(
      screen.getByDisplayValue('Titan authorization architecture'),
    ).toBeInTheDocument();
    expect(screen.getByDisplayValue('Alice, Project Titan')).toBeInTheDocument();
  });

  it('triggers dual-channel hybrid RRF search and displays ranked results with hit sources', async () => {
    mockSearchDualChannelRRF.mockResolvedValueOnce(mockSearchResult);

    render(<GraphRRFRetrievalCard />);

    const searchButton = screen.getByRole('button', { name: /双通道 RRF 混合检索/i });
    fireEvent.click(searchButton);

    await waitFor(() => {
      expect(mockSearchDualChannelRRF).toHaveBeenCalledTimes(1);
      expect(mockSearchDualChannelRRF).toHaveBeenCalledWith({
        query: 'Titan authorization architecture',
        seed_entity_names: ['Alice', 'Project Titan'],
        top_k: 5,
      });
      expect(
        screen.getByText(/双通道 RRF 检索完成：共融合召回 2 条记忆项/),
      ).toBeInTheDocument();
    });

    expect(
      screen.getByText(/OAuth2 token validation guidelines designed by Alice/),
    ).toBeInTheDocument();
    expect(screen.getByText('0.0325')).toBeInTheDocument();
    expect(screen.getByText(/向量排名: #1/)).toBeInTheDocument();
  });

  it('triggers BFS graph traversal and displays multi-hop paths', async () => {
    mockTraverseKnowledgeGraph.mockResolvedValueOnce(mockTraverseResult);

    render(<GraphRRFRetrievalCard />);

    const traverseButton = screen.getByRole('button', { name: /拓扑关系展开 \(BFS\)/i });
    fireEvent.click(traverseButton);

    await waitFor(() => {
      expect(mockTraverseKnowledgeGraph).toHaveBeenCalledWith({
        seed_entity_ids: ['Alice', 'Project Titan'],
        max_hops: 2,
      });
      expect(
        screen.getByText(/BFS 拓扑遍历完成：触达 2 个节点，发现 1 条多跳路径/),
      ).toBeInTheDocument();
    });

    expect(screen.getByText('Alice')).toBeInTheDocument();
    expect(screen.getByText('Project Titan')).toBeInTheDocument();
    expect(screen.getByText('leads')).toBeInTheDocument();
    expect(screen.getByText(/深度 1/)).toBeInTheDocument();
  });

  it('submits quick entity creation and displays confirmation notification', async () => {
    mockCreateEntityNode.mockResolvedValueOnce({
      id: 'module:crypto',
      name: 'Crypto Kernel',
      entity_type: 'MODULE',
      properties: {},
      created_at: 1728300000,
    });

    render(<GraphRRFRetrievalCard />);

    const idInput = screen.getByPlaceholderText(/实体 ID \(例如 person:alice\)/i);
    const nameInput = screen.getByPlaceholderText(/实体名称 \(例如 Alice\)/i);
    fireEvent.change(idInput, { target: { value: 'module:crypto' } });
    fireEvent.change(nameInput, { target: { value: 'Crypto Kernel' } });

    const submitBtn = screen.getByRole('button', { name: /注册节点/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockCreateEntityNode).toHaveBeenCalledWith({
        id: 'module:crypto',
        name: 'Crypto Kernel',
        entity_type: 'CONCEPT',
      });
      expect(
        screen.getByText(/实体节点 \[Crypto Kernel\] \(module:crypto\) 创建成功/),
      ).toBeInTheDocument();
    });
  });
});
