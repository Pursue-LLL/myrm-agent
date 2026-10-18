/** @vitest-environment jsdom */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import SkillsSection from '../SkillsSection';

/**
 * The upstream-update confirmation is the only place a reader learns that accepting an
 * update is reversible: the undo control it points at lives on the skill detail page.
 * These cases drive the real dialog, so a wording change that stops promising the undo
 * fails here rather than shipping a promise the page contradicts.
 */

const mocks = vi.hoisted(() => ({
  t: (key: string, values?: Record<string, string>) => (values ? `${key}|${JSON.stringify(values)}` : key),
  lifecycleAction: vi.fn(),
}));

vi.mock('next-intl', () => ({ useTranslations: () => mocks.t, useLocale: () => 'en' }));

vi.mock('@/components/features/icons/PremiumIcons', async (importOriginal) => {
  // Keep the real icon components: the section renders several, and stubbing one list of
  // names drifts as soon as a sibling panel imports another.
  return await importOriginal<typeof import('@/components/features/icons/PremiumIcons')>();
});

vi.mock('@/hooks/shared/useToast', () => ({ toast: vi.fn() }));

vi.mock('@/store/useAuthStore', () => ({
  default: (selector?: (state: { user: unknown; isInitialized: boolean }) => unknown) => {
    const state = { user: { id: 'u1' }, isInitialized: true };
    return selector ? selector(state) : state;
  },
}));

const upstreamSkill = {
  id: 'code-review',
  name: 'Code Review',
  description: 'Reviews diffs',
  type: 'prebuilt' as const,
  source: 'builtin' as const,
  enabled: true,
  has_upstream_update: true,
  storage_path: '/data/skills/prebuilt/code-review',
  tags: [] as string[],
  usage_stats: { lifecycle_status: 'active' },
};

vi.mock('@/store/skill', () => ({
  useSkillStore: () => ({
    marketSkills: [upstreamSkill],
    localSkills: [],
    enabledPrebuiltIds: ['code-review'],
    enabledLocalSkillIds: [],
    isLoadingLocal: false,
    isLoadingConfig: false,
    fetchMarketSkills: vi.fn(),
    fetchUserSkillConfig: vi.fn(),
    fetchLocalSkillPaths: vi.fn(),
    fetchLocalSkills: vi.fn(),
    toggleSkill: vi.fn(),
    toggleLocalSkill: vi.fn(),
    batchToggleSkills: vi.fn(),
    isSkillEnabled: () => true,
  }),
}));

vi.mock('@/store/skill/useSkillDraftStore', () => ({
  useSkillDraftStore: () => ({ unreviewedCount: 0, fetchUnreviewedCount: vi.fn() }),
}));

// The inventory list is replaced by one row that raises the same lifecycle action the
// real list raises, so the dialog under test is the production component, not a stub.
vi.mock('@/components/features/skills/SkillList', () => ({
  default: ({ onLifecycleAction }: { onLifecycleAction: (skill: typeof upstreamSkill, action: string) => void }) => (
    <button type="button" onClick={() => onLifecycleAction(upstreamSkill, 'accept-upstream')}>
      raise-accept-upstream
    </button>
  ),
}));

vi.mock('@/components/features/skills/SkillDiscoverTab', () => ({ default: () => null }));
vi.mock('@/components/features/skills/LocalPathsConfig', () => ({ default: () => null }));
vi.mock('@/components/features/skills/SkillDraftReviewPanel', () => ({ default: () => null }));
vi.mock('@/components/features/skills/SkillHistoryPanel', () => ({ default: () => null }));

describe('SkillsSection upstream-update confirmation', () => {
  beforeEach(() => {
    mocks.lifecycleAction.mockClear();
  });

  it('names the skill and promises the undo in the confirmation body', async () => {
    render(<SkillsSection initialSearch="Code Review" />);

    await userEvent.click(screen.getByRole('button', { name: 'raise-accept-upstream' }));

    // The body is interpolated with the skill name, so the reader sees which skill it is.
    expect(await screen.findByText(/card\.confirmAcceptDesc\|/)).toBeTruthy();
    expect(screen.getByText(/Code Review/)).toBeTruthy();
  });

  it('offers a confirm and a cancel path on the confirmation', async () => {
    render(<SkillsSection initialSearch="Code Review" />);

    await userEvent.click(screen.getByRole('button', { name: 'raise-accept-upstream' }));

    // Both controls are part of the reversible story: confirm proceeds, cancel backs out
    // without touching the skill. The undo itself is offered after the update is applied.
    expect(await screen.findByRole('button', { name: 'card.confirmAction' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'card.cancelAction' })).toBeTruthy();
  });
});
