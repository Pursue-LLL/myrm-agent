/** @vitest-environment jsdom */

/**
 * [INPUT]
 * @/services/memory/gitOkf::getOkfDisclosureSummary, getOkfConceptDetail, loadOkfBundle,
 *   validateOkfBundle, searchOkfConcepts
 * ../command-center/GitNativeKnowledgeBundleCard::GitNativeKnowledgeBundleCard
 *
 * [OUTPUT]
 * Test suite verifying Git-native OKF v0.2 knowledge bundle loading, two-phase progressive
 * disclosure, memory rot prevention (stale_after), human-agent trust balance, and BM25 search.
 *
 * [POS]
 * Unit test for Item 95 (Git-Native Project Knowledge Bundle & Memory Rot Prevention Suite).
 * Strict typing applied: No `any` types allowed. File lines < 400.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { GitNativeKnowledgeBundleCard } from '../command-center/GitNativeKnowledgeBundleCard';
import type {
  OKFDisclosureSummaryDTO,
  OKFConceptDetailDTO,
  OKFValidationReportDTO,
  OKFSearchResultDTO,
  LoadBundleResponseDTO,
} from '@/services/memory/gitOkf';

const {
  mockGetOkfDisclosureSummary,
  mockGetOkfConceptDetail,
  mockLoadOkfBundle,
  mockValidateOkfBundle,
  mockSearchOkfConcepts,
} = vi.hoisted(() => ({
  mockGetOkfDisclosureSummary: vi.fn(),
  mockGetOkfConceptDetail: vi.fn(),
  mockLoadOkfBundle: vi.fn(),
  mockValidateOkfBundle: vi.fn(),
  mockSearchOkfConcepts: vi.fn(),
}));

vi.mock('@/services/memory/gitOkf', () => ({
  getOkfDisclosureSummary: mockGetOkfDisclosureSummary,
  getOkfConceptDetail: mockGetOkfConceptDetail,
  loadOkfBundle: mockLoadOkfBundle,
  validateOkfBundle: mockValidateOkfBundle,
  searchOkfConcepts: mockSearchOkfConcepts,
}));

describe('GitNativeKnowledgeBundleCard', () => {
  const sampleSummary: OKFDisclosureSummaryDTO = {
    bundle_path: '.myrm/knowledge',
    total_concepts: 3,
    stale_count: 1,
    concepts: [
      {
        id: 'conventions/auth_flow',
        title: 'Authentication & Session Token Flow',
        description: 'Mandatory session verification using Bearer tokens for all protected RPC calls.',
        governance: 'constraint',
        status: 'stable',
        is_stale: false,
        code_refs: ['src/services/auth/', 'src/middleware/auth.ts'],
      },
      {
        id: 'architecture/hexagonal_memory',
        title: 'Decoupled Hexagonal Memory Layers',
        description: 'Strict separation between harness engine, server business facades, and frontend UI cards.',
        governance: 'context',
        status: 'stable',
        is_stale: false,
        code_refs: ['src/components/features/memory/'],
      },
      {
        id: 'standards/legacy_node16',
        title: 'Legacy Node 16 Runtime Constraints',
        description: 'Historical build target before upgrading to Node 22 ESM runtime.',
        governance: 'hold',
        status: 'deprecated',
        is_stale: true,
        code_refs: ['package.json'],
      },
    ],
  };

  const sampleDetail: OKFConceptDetailDTO = {
    id: 'conventions/auth_flow',
    path: 'conventions/auth_flow.md',
    type: 'convention',
    title: 'Authentication & Session Token Flow',
    description: 'Mandatory session verification using Bearer tokens for all protected RPC calls.',
    governance: 'constraint',
    status: 'stable',
    stale_after: '2027-01-01',
    code_refs: ['src/services/auth/', 'src/middleware/auth.ts'],
    tags: ['security', 'auth', 'tokens'],
    body: '## Rule Details\n\n1. All requests must carry an Authorization header.\n2. In memory sessions, tokens expire after 24 hours of inactivity.',
    is_stale: false,
  };

  const sampleReport: OKFValidationReportDTO = {
    bundle_path: '.myrm/knowledge',
    declared_version: '0.2',
    concept_count: 3,
    errors: [],
    warnings: ['standards/legacy_node16: concept is stale (stale_after 2026-01-01 <= today)'],
    gate_findings: [],
    stale_count: 1,
    superseded_trust_count: 0,
    is_conformant: true,
    gate_passed: true,
  };

  const sampleSearchResults: OKFSearchResultDTO[] = [
    {
      concept_id: 'conventions/auth_flow',
      title: 'Authentication & Session Token Flow',
      type: 'convention',
      description: 'Matched query in authentication standards.',
      governance: 'constraint',
      score: 2.145,
      matched_fields: ['title', 'description'],
      tags: ['security'],
      code_refs: ['src/services/auth/'],
      is_stale: false,
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    mockGetOkfDisclosureSummary.mockResolvedValue(sampleSummary);
    mockGetOkfConceptDetail.mockResolvedValue(sampleDetail);
    mockValidateOkfBundle.mockResolvedValue(sampleReport);
    mockSearchOkfConcepts.mockResolvedValue(sampleSearchResults);
    mockLoadOkfBundle.mockResolvedValue({
      bundle_path: '/workspace/.myrm/knowledge',
      loaded_concepts_count: 3,
      is_success: true,
    } satisfies LoadBundleResponseDTO);
  });

  it('renders HUD statistics and default concept browser correctly', async () => {
    render(<GitNativeKnowledgeBundleCard />);

    await waitFor(() => {
      expect(screen.getByText('Git 原生项目知识库与记忆防腐烂门禁套件')).toBeInTheDocument();
    });

    expect(screen.getByTestId('hud-total-concepts')).toHaveTextContent('3');
    expect(screen.getByTestId('hud-stale-concepts')).toHaveTextContent('1');
    expect(screen.getByTestId('hud-gate-status')).toHaveTextContent('PASSED');
    expect(screen.getByTestId('hud-superseded-trust')).toHaveTextContent('0');

    // Check list of concept cards
    expect(screen.getByTestId('concept-card-conventions/auth_flow')).toBeInTheDocument();
    expect(screen.getByText('Decoupled Hexagonal Memory Layers')).toBeInTheDocument();
    expect(screen.getByText('Legacy Node 16 Runtime Constraints')).toBeInTheDocument();
    expect(screen.getByText('STALE 过期')).toBeInTheDocument();
  });

  it('mounts and loads a new knowledge bundle directory', async () => {
    render(<GitNativeKnowledgeBundleCard />);

    await waitFor(() => {
      expect(screen.getByTestId('load-bundle-form')).toBeInTheDocument();
    });

    const pathInput = screen.getByLabelText(/知识包目录路径/);
    fireEvent.change(pathInput, { target: { value: 'docs/architecture/knowledge' } });

    const loadBtn = screen.getByTestId('btn-load-bundle');
    fireEvent.click(loadBtn);

    await waitFor(() => {
      expect(mockLoadOkfBundle).toHaveBeenCalledWith({
        bundle_path: 'docs/architecture/knowledge',
      });
    });

    await waitFor(() => {
      expect(screen.getByText(/已成功挂载 OKF 知识包/)).toBeInTheDocument();
    });
  });

  it('filters concepts by governance level dropdown', async () => {
    render(<GitNativeKnowledgeBundleCard />);

    await waitFor(() => {
      expect(screen.getByLabelText(/按治理层级筛选/)).toBeInTheDocument();
    });

    const filterSelect = screen.getByLabelText(/按治理层级筛选/);
    fireEvent.change(filterSelect, { target: { value: 'constraint' } });

    // Should only show constraint concept
    expect(screen.getByTestId('concept-card-conventions/auth_flow')).toBeInTheDocument();
    expect(screen.queryByText('Decoupled Hexagonal Memory Layers')).not.toBeInTheDocument();
    expect(screen.queryByText('Legacy Node 16 Runtime Constraints')).not.toBeInTheDocument();
  });

  it('selects a concept card and inspects phase-two details and markdown body', async () => {
    render(<GitNativeKnowledgeBundleCard />);

    await waitFor(() => {
      expect(screen.getByTestId('concept-card-conventions/auth_flow')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('concept-card-conventions/auth_flow'));

    await waitFor(() => {
      expect(mockGetOkfConceptDetail).toHaveBeenCalledWith('conventions/auth_flow');
    });

    expect(screen.getByTestId('concept-detail-box')).toBeInTheDocument();
    expect(screen.getByTestId('concept-body-content')).toHaveTextContent(
      'All requests must carry an Authorization header.'
    );
  });

  it('switches to memory rot audit tab and displays conformance report', async () => {
    render(<GitNativeKnowledgeBundleCard />);

    await waitFor(() => {
      expect(screen.getByTestId('tab-rot-audit')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('tab-rot-audit'));

    await waitFor(() => {
      expect(screen.getByText(/防腐烂显式保质期与人机防篡改信任天平/)).toBeInTheDocument();
    });

    expect(screen.getByTestId('metric-concept-count')).toHaveTextContent('3 篇');
    expect(screen.getByTestId('metric-stale-count')).toHaveTextContent('1 篇');
    expect(screen.getByTestId('metric-superseded-trust')).toHaveTextContent('0 项');
    expect(screen.getByTestId('badge-gate-passed')).toHaveTextContent('门禁通过 (PASSED)');
  });

  it('re-executes memory rot and anti-tamper audit check', async () => {
    render(<GitNativeKnowledgeBundleCard />);

    await waitFor(() => {
      expect(screen.getByTestId('tab-rot-audit')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('tab-rot-audit'));

    await waitFor(() => {
      expect(screen.getByTestId('btn-validate-okf-bundle')).toBeInTheDocument();
    });

    const validateBtn = screen.getByTestId('btn-validate-okf-bundle');
    fireEvent.click(validateBtn);

    await waitFor(() => {
      expect(mockValidateOkfBundle).toHaveBeenCalled();
    });
  });

  it('executes in-memory BM25 lexical search and displays ranked hits', async () => {
    render(<GitNativeKnowledgeBundleCard />);

    await waitFor(() => {
      expect(screen.getByTestId('tab-rot-audit')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('tab-rot-audit'));

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/检索规范、代码约定或架构决议/)).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText(/检索规范、代码约定或架构决议/);
    fireEvent.change(searchInput, { target: { value: 'auth token' } });

    const searchBtn = screen.getByTestId('btn-trigger-okf-search');
    fireEvent.click(searchBtn);

    await waitFor(() => {
      expect(mockSearchOkfConcepts).toHaveBeenCalledWith(
        expect.objectContaining({
          query: 'auth token',
        })
      );
    });

    expect(screen.getByTestId('okf-search-results-list')).toBeInTheDocument();
    expect(screen.getByTestId('okf-hit-conventions/auth_flow')).toBeInTheDocument();
  });

  it('refreshes bundle status when clicking the refresh button', async () => {
    render(<GitNativeKnowledgeBundleCard />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /刷新/ })).toBeInTheDocument();
    });

    const refreshBtn = screen.getByRole('button', { name: /刷新/ });
    fireEvent.click(refreshBtn);

    await waitFor(() => {
      expect(mockGetOkfDisclosureSummary).toHaveBeenCalledTimes(2);
      expect(mockValidateOkfBundle).toHaveBeenCalledTimes(2);
    });
  });

  it('gracefully degrades to fallback state on API failure', async () => {
    mockGetOkfDisclosureSummary.mockRejectedValue(new Error('Network error'));
    mockValidateOkfBundle.mockRejectedValue(new Error('Network error'));

    render(<GitNativeKnowledgeBundleCard />);

    await waitFor(() => {
      expect(screen.getByText('Git 原生项目知识库与记忆防腐烂门禁套件')).toBeInTheDocument();
    });

    expect(screen.getByTestId('hud-total-concepts')).toHaveTextContent('3');
    expect(screen.getByTestId('hud-stale-concepts')).toHaveTextContent('1');
  });
});
