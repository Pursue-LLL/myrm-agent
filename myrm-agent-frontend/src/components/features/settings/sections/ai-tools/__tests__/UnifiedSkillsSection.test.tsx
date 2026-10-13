/** @vitest-environment jsdom */
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import UnifiedSkillsSection from '../UnifiedSkillsSection';

const mocks = vi.hoisted(() => ({ params: new URLSearchParams(), t: (key: string) => key }));

vi.mock('next-intl', () => ({ useTranslations: () => mocks.t }));
vi.mock('next/navigation', () => ({ useSearchParams: () => mocks.params }));
vi.mock('@/hooks/settings/useSettingsSubTabUrl', () => ({
  useSettingsSubTabUrl: () => ({ handleTabChange: vi.fn() }),
  defaultSubTabResolver: () => () => null,
}));
vi.mock('@/components/features/icons/PremiumIcons', () => ({ IconGlow: () => null }));
vi.mock('@/components/features/skills/PendingEvolutionsDashboard', () => ({ PendingEvolutionsDashboard: () => null }));
vi.mock('@/components/features/skills/EvolutionRejectionDashboard', () => ({ EvolutionRejectionDashboard: () => null }));
vi.mock('../CompoundingChecklistSection', () => ({ default: () => null }));
vi.mock('../WorkflowTemplateLibrarySection', () => ({ default: () => null }));
vi.mock('../SkillsSection', () => ({
  default: ({ initialSearch }: { initialSearch?: string }) => (
    <div data-testid="skill-inventory" data-initial-search={initialSearch ?? ''} />
  ),
}));

describe('UnifiedSkillsSection skill deep link', () => {
  beforeEach(() => {
    mocks.params = new URLSearchParams();
  });

  it('hands the skill name from the health panel link to the inventory as its initial search', () => {
    mocks.params = new URLSearchParams(`search=${encodeURIComponent('weekly report & more')}`);

    render(<UnifiedSkillsSection />);

    expect(screen.getByTestId('skill-inventory').getAttribute('data-initial-search')).toBe('weekly report & more');
  });

  it('opens the inventory without a search when the URL carries none', () => {
    render(<UnifiedSkillsSection />);

    expect(screen.getByTestId('skill-inventory').getAttribute('data-initial-search')).toBe('');
  });
});
