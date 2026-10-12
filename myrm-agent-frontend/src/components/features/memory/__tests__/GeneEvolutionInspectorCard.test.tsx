/** @vitest-environment jsdom */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { GeneEvolutionInspectorCard } from '../command-center/GeneEvolutionInspectorCard';

const {
  mockListExperienceGenes,
  mockGetExperienceGeneStats,
  mockQueryGeneMutationAdvice,
  mockPenalizeExperienceGene,
  mockExtractCausalGenes,
} = vi.hoisted(() => ({
  mockListExperienceGenes: vi.fn(),
  mockGetExperienceGeneStats: vi.fn(),
  mockQueryGeneMutationAdvice: vi.fn(),
  mockPenalizeExperienceGene: vi.fn(),
  mockExtractCausalGenes: vi.fn(),
}));

vi.mock('@/services/memory/experienceGene', () => ({
  listExperienceGenes: mockListExperienceGenes,
  getExperienceGeneStats: mockGetExperienceGeneStats,
  queryGeneMutationAdvice: mockQueryGeneMutationAdvice,
  penalizeExperienceGene: mockPenalizeExperienceGene,
  extractCausalGenes: mockExtractCausalGenes,
}));

describe('GeneEvolutionInspectorCard', () => {
  const mockStats = {
    total_genes: 8,
    avg_confidence: 0.88,
    total_proof_count: 24,
  };

  const mockGenes = [
    {
      gene_id: 'gene_kernel_001',
      trigger_signals: ['kernel_panic', 'deadlock'],
      hypotheses_refuted: ['reboot_machine', 'disable_watchdog'],
      proven_resolution: 'Tune spinlock timeout in driver probe sequence',
      polarity: 'positive',
      confidence_score: 0.92,
      proof_count: 5,
      provenance_session_id: 'sess-01',
      tags: ['kernel', 'driver'],
      created_at: 1728300000,
      updated_at: 1728300500,
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    mockGetExperienceGeneStats.mockResolvedValue(mockStats);
    mockListExperienceGenes.mockResolvedValue(mockGenes);
  });

  it('renders stats HUD and gene list correctly on load', async () => {
    render(<GeneEvolutionInspectorCard />);

    expect(screen.getByText('因果经验基因合成器与达尔文演化账本')).toBeInTheDocument();
    expect(screen.getByText('EvoX 达尔文自进化')).toBeInTheDocument();

    expect(await screen.findByText('8 条')).toBeInTheDocument();
    expect(screen.getByText('88%')).toBeInTheDocument();
    expect(screen.getByText('24 次')).toBeInTheDocument();

    expect(screen.getByText('gene_kernel_001')).toBeInTheDocument();
    expect(screen.getByText('证明 5 次')).toBeInTheDocument();
  });

  it('queries planning advice and displays dead-ends and resolution', async () => {
    mockQueryGeneMutationAdvice.mockResolvedValueOnce({
      total_matched: 1,
      advices: [
        {
          gene_id: 'gene_kernel_001',
          matched_signals: ['kernel_panic'],
          refuted_paths: ['reboot_machine'],
          recommended_resolution: 'Tune spinlock timeout',
          confidence: 0.92,
          polarity: 'positive',
        },
      ],
    });

    render(<GeneEvolutionInspectorCard />);

    const searchBtn = screen.getByRole('button', { name: /探针匹配/ });
    fireEvent.click(searchBtn);

    await waitFor(() => {
      expect(mockQueryGeneMutationAdvice).toHaveBeenCalledTimes(1);
    });

    expect(await screen.findByText('规划期命中经验基因建议 (1)')).toBeInTheDocument();
    expect(screen.getByText('reboot_machine')).toBeInTheDocument();
    expect(screen.getByText('验证解决路径:')).toBeInTheDocument();
    expect(screen.getAllByText(/Tune spinlock timeout/).length).toBeGreaterThanOrEqual(1);
  });


  it('penalizes ineffective gene and triggers reload', async () => {
    mockPenalizeExperienceGene.mockResolvedValueOnce({
      gene_id: 'gene_kernel_001',
      confidence_score: 0.72,
    });

    render(<GeneEvolutionInspectorCard />);

    const penalizeBtn = await screen.findByRole('button', { name: /惩罚降权/ });
    fireEvent.click(penalizeBtn);

    await waitFor(() => {
      expect(mockPenalizeExperienceGene).toHaveBeenCalledWith({
        gene_id: 'gene_kernel_001',
        penalty: 0.2,
      });
    });

    expect(await screen.findByText(/已对基因 gene_kernel_001 扣减置信度/)).toBeInTheDocument();
  });

  it('synthesizes causal gene from simulated trace', async () => {
    mockExtractCausalGenes.mockResolvedValueOnce({
      status: 'success',
      gene: {
        gene_id: 'gene_sim_123',
        proof_count: 1,
      },
      reinforced: false,
    });

    render(<GeneEvolutionInspectorCard />);

    const extractBtn = screen.getByRole('button', { name: /一键提取基因/ });
    fireEvent.click(extractBtn);

    await waitFor(() => {
      expect(mockExtractCausalGenes).toHaveBeenCalledTimes(1);
    });

    expect(await screen.findByText(/成功合成因果经验基因: gene_sim_123/)).toBeInTheDocument();
  });
});
