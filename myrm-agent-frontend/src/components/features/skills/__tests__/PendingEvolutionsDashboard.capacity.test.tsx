/** @vitest-environment jsdom */

import type React from 'react';
import { act, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockListSkillGrowthCases = vi.hoisted(() => vi.fn());
const mockGetSkillGrowthSummary = vi.hoisted(() => vi.fn());
const mockFetchLocalSkills = vi.hoisted(() => vi.fn());
const mockFetchUserSkillConfig = vi.hoisted(() => vi.fn());

vi.mock('@/services/skill/growth', () => ({
  listSkillGrowthCases: mockListSkillGrowthCases,
  getSkillGrowthSummary: mockGetSkillGrowthSummary,
  approveSkillGrowthCase: vi.fn(),
  rejectSkillGrowthCase: vi.fn(),
  reviseSkillGrowthCase: vi.fn(),
}));

vi.mock('@/store/useAuthStore', () => ({
  default: () => ({ user: { id: 'user-1' } }),
}));

let mockLocalSkills: Array<{ id: string; name: string }> = [];

vi.mock('@/store/skill', () => ({
  useSkillStore: () => ({
    localSkills: mockLocalSkills,
    fetchLocalSkills: mockFetchLocalSkills,
    fetchUserSkillConfig: mockFetchUserSkillConfig,
  }),
}));

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(),
}));

import { PendingEvolutionsDashboard } from '../PendingEvolutionsDashboard';

describe('PendingEvolutionsDashboard Capacity Guard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListSkillGrowthCases.mockResolvedValue({ items: [], total: 0 });
    mockGetSkillGrowthSummary.mockResolvedValue({ total: 0, pendingReview: 0, autoApplied: 0, blocked: 0 });
  });

  it('renders normal capacity badge when skills are within safe budget (<80%)', async () => {
    mockLocalSkills = Array.from({ length: 10 }, (_, i) => ({ id: `skill-${i}`, name: `Skill ${i}` }));

    await act(async () => {
      render(<PendingEvolutionsDashboard />);
    });

    expect(screen.getByText(/容量池:/)).toBeInTheDocument();
    expect(screen.getByText('10/50 (20%)')).toBeInTheDocument();
    expect(screen.queryByText(/接近容量安全阈值/)).not.toBeInTheDocument();
  });

  it('renders amber warning banner when skills hit soft limit (80%-99%)', async () => {
    mockLocalSkills = Array.from({ length: 42 }, (_, i) => ({ id: `skill-${i}`, name: `Skill ${i}` }));

    await act(async () => {
      render(<PendingEvolutionsDashboard />);
    });

    expect(screen.getAllByText('42/50 (84%)').length).toBe(2);
    expect(screen.getByText(/技能池接近容量安全阈值 \(80%\)/)).toBeInTheDocument();
  });

  it('renders rose alert banner when skills hit hard limit (100%)', async () => {
    mockLocalSkills = Array.from({ length: 50 }, (_, i) => ({ id: `skill-${i}`, name: `Skill ${i}` }));

    await act(async () => {
      render(<PendingEvolutionsDashboard />);
    });

    expect(screen.getAllByText('50/50 (100%)').length).toBe(2);
    expect(screen.getByText(/技能自进化已触碰硬限熔断 \(100%\)/)).toBeInTheDocument();
  });
});
