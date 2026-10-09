/** @vitest-environment jsdom */

/**
 * Test suite verifying Item 136 ExperienceCompoundingAndKnowledgeCondensationSuite:
 * 1. Default render of HUD telemetry bar, golden rules catalog, and active experience pool.
 * 2. Triggering semantic condensation calling experienceCompoundingService.condense.
 * 3. Triggering context annealing calling experienceCompoundingService.anneal.
 * 4. Reinforcing experience fragment on adoption calling experienceCompoundingService.reinforce.
 * 5. Seeding new experience fragment calling experienceCompoundingService.addItem.
 * 6. Decondensing golden rule back to fragments calling experienceCompoundingService.decondense.
 * 7. Resilient fallback on network service rejection.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ExperienceCompoundingStudioCard } from '../command-center/ExperienceCompoundingStudioCard';
import {
  mockCompoundingStats,
  mockActiveExperiences,
  mockGoldenRules,
} from '../command-center/experienceCompoundingFallbacks';

const {
  mockGetStats,
  mockListActive,
  mockListRules,
  mockAddItem,
  mockReinforce,
  mockPenalize,
  mockCondense,
  mockDecondense,
  mockAnneal,
} = vi.hoisted(() => ({
  mockGetStats: vi.fn(),
  mockListActive: vi.fn(),
  mockListRules: vi.fn(),
  mockAddItem: vi.fn(),
  mockReinforce: vi.fn(),
  mockPenalize: vi.fn(),
  mockCondense: vi.fn(),
  mockDecondense: vi.fn(),
  mockAnneal: vi.fn(),
}));

vi.mock('@/services/memory/experienceCompounding', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    experienceCompoundingService: {
      getStats: mockGetStats,
      listActive: mockListActive,
      listRules: mockListRules,
      addItem: mockAddItem,
      reinforce: mockReinforce,
      penalize: mockPenalize,
      condense: mockCondense,
      decondense: mockDecondense,
      anneal: mockAnneal,
    },
  };
});

describe('ExperienceCompoundingStudioCard (Item 136 P1)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetStats.mockResolvedValue(mockCompoundingStats);
    mockListActive.mockResolvedValue(mockActiveExperiences);
    mockListRules.mockResolvedValue(mockGoldenRules);
    mockAddItem.mockResolvedValue({
      item_id: 'exp-test-999',
      topic: 'sqlite_wal',
      content: '测试 WAL 模式经验碎片',
      reinforcement_count: 0,
      compounded_weight: 1.0,
      half_life_days: 14.0,
      status: 'active',
      is_pinned: false,
      is_temporary: false,
      hit_count: 1,
      adoption_count: 0,
      tags: ['sqlite'],
      created_at: 1759650000.0,
      updated_at: 1759650000.0,
      last_accessed_at: 1759650000.0,
    });
    mockReinforce.mockResolvedValue({
      item_id: 'exp-1',
      new_weight: 1.85,
      adoption_count: 4,
      status: 'active',
    });
    mockPenalize.mockResolvedValue({
      item_id: 'exp-1',
      new_weight: 0.5,
      half_life_days: 7.0,
      status: 'penalized',
    });
    mockCondense.mockResolvedValue({
      cluster_count: 1,
      rules_generated: ['rule-gen-1'],
      fragments_archived: 2,
    });
    mockDecondense.mockResolvedValue([
      {
        item_id: 'exp-1',
        topic: 'redis_lock',
        content: '原始经验 1',
        status: 'active',
      },
    ]);
    mockAnneal.mockResolvedValue({
      inspected_count: 5,
      active_lease_exempt_count: 2,
      cold_tiered_count: 1,
      deprecations_count: 0,
    });
  });

  it('1. should render HUD bar, golden rules catalog, and active experience pool', async () => {
    render(<ExperienceCompoundingStudioCard />);

    expect(screen.getByText('经验资产复利与自动凝练')).toBeInTheDocument();
    expect(screen.getByText('知识复利飞轮 · 越用越懂我')).toBeInTheDocument();
    expect(screen.getByText('高阶黄金准则库')).toBeInTheDocument();
    expect(screen.getByText('活跃热经验池')).toBeInTheDocument();

    await waitFor(() => {
      expect(mockGetStats).toHaveBeenCalledTimes(1);
      expect(mockListActive).toHaveBeenCalledTimes(1);
      expect(mockListRules).toHaveBeenCalledTimes(1);
    });
  });

  it('2. should trigger semantic condensation and show feedback toast', async () => {
    render(<ExperienceCompoundingStudioCard />);

    const condenseBtn = screen.getByRole('button', { name: /一键语义凝练/i });
    fireEvent.click(condenseBtn);

    await waitFor(() => {
      expect(mockCondense).toHaveBeenCalledTimes(1);
      expect(screen.getByText(/语义凝练完成: 新提炼 1 项黄金准则/i)).toBeInTheDocument();
    });
  });

  it('3. should trigger context annealing and show feedback toast', async () => {
    render(<ExperienceCompoundingStudioCard />);

    const annealBtn = screen.getByRole('button', { name: /时效冷退火/i });
    fireEvent.click(annealBtn);

    await waitFor(() => {
      expect(mockAnneal).toHaveBeenCalledTimes(1);
      expect(screen.getByText(/时效退火完成: 评估 5 项，豁免常驻 2 项/i)).toBeInTheDocument();
    });
  });

  it('4. should reinforce experience fragment upon user adoption', async () => {
    render(<ExperienceCompoundingStudioCard />);

    const reinforceBtns = await screen.findAllByRole('button', { name: /采纳加固/i });
    expect(reinforceBtns.length).toBeGreaterThan(0);
    fireEvent.click(reinforceBtns[0]);

    await waitFor(() => {
      expect(mockReinforce).toHaveBeenCalledWith(
        expect.objectContaining({
          adopted: true,
        })
      );
      expect(screen.getByText(/已加固经验/i)).toBeInTheDocument();
    });
  });

  it('5. should add new experience fragment via input drawer', async () => {
    render(<ExperienceCompoundingStudioCard />);

    const openDrawerBtn = screen.getByRole('button', { name: /录入新经验/i });
    fireEvent.click(openDrawerBtn);

    const topicInput = screen.getByPlaceholderText(/例如: frontend, quality, workflow/i);
    const contentInput = screen.getByPlaceholderText(/输入如：Python 代码严禁使用 Any 类型/i);

    fireEvent.change(topicInput, { target: { value: 'sqlite_wal' } });
    fireEvent.change(contentInput, { target: { value: '测试 WAL 模式经验碎片内容' } });

    const submitBtn = screen.getByRole('button', { name: /提交保存/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockAddItem).toHaveBeenCalledWith(
        expect.objectContaining({
          topic: 'sqlite_wal',
          content: '测试 WAL 模式经验碎片内容',
        })
      );
    });
  });

  it('6. should decondense golden rule back to original fragments', async () => {
    render(<ExperienceCompoundingStudioCard />);

    const decondenseBtns = await screen.findAllByRole('button', { name: /回退解散/i });
    expect(decondenseBtns.length).toBeGreaterThan(0);
    fireEvent.click(decondenseBtns[0]);

    await waitFor(() => {
      expect(mockDecondense).toHaveBeenCalledWith(
        expect.objectContaining({
          rule_id: expect.any(String),
        })
      );
      expect(screen.getByText(/已回退准则/i)).toBeInTheDocument();
    });
  });

  it('7. should gracefully fallback to mock data when API throws error', async () => {
    mockGetStats.mockRejectedValueOnce(new Error('Network offline'));
    mockListActive.mockRejectedValueOnce(new Error('Network offline'));
    mockListRules.mockRejectedValueOnce(new Error('Network offline'));

    render(<ExperienceCompoundingStudioCard />);

    await waitFor(() => {
      expect(screen.getByText('经验资产复利与自动凝练')).toBeInTheDocument();
    });
  });

  it('8. should penalize experience fragment upon contradiction', async () => {
    render(<ExperienceCompoundingStudioCard />);

    const penalizeBtns = await screen.findAllByRole('button', { name: /纠偏降权/i });
    expect(penalizeBtns.length).toBeGreaterThan(0);
    fireEvent.click(penalizeBtns[0]);

    await waitFor(() => {
      expect(mockPenalize).toHaveBeenCalledWith(
        expect.objectContaining({
          item_id: expect.any(String),
          severity: 0.5,
        })
      );
      expect(screen.getByText(/已纠偏降权/i)).toBeInTheDocument();
    });
  });
});
