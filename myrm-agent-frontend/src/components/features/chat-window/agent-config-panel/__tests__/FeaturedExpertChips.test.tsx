/** @vitest-environment jsdom */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { toast } from 'sonner';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import useChatStore from '@/store/useChatStore';
import { deferred } from '@/test-utils/deferred';
import { settle } from '@/test-utils/fakeClock';

import { FeaturedExpertChips } from '../FeaturedExpertChips';

const mocks = vi.hoisted(() => ({
  router: { push: vi.fn() },
  loadTemplates: vi.fn(),
  summon: vi.fn(),
}));

// Interpolation values are part of the output, so the name in the success toast can be asserted.
const translate = (key: string, params?: Record<string, unknown>) =>
  params ? `${key}:${JSON.stringify(params)}` : key;

vi.mock('next-intl', () => ({ useTranslations: () => translate }));
vi.mock('next/navigation', () => ({ useRouter: () => mocks.router }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/services/featuredTemplates', () => ({
  peekFeaturedTemplates: () => null,
  loadFeaturedTemplates: () => mocks.loadTemplates(),
}));
vi.mock('@/services/templateSummon', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/templateSummon')>()),
  instantiateTemplateWithMetrics: (...args: unknown[]) => mocks.summon(...args),
}));

const TEAM = {
  id: 'team-arch',
  name: 'Architecture Squad',
  agent_type: 'team',
  description: 'Lead architects and reviewers',
  use_cases: ['Review system refactoring plan'],
};
const EXPERT = { id: 'agent-db', name: 'DB Tuning Expert', agent_type: 'individual', is_pareto_preset: true };

const chip = (name: string) => screen.getByRole('button', { name: new RegExp(name) });

async function mountWith(templates: unknown[], onSummoned?: (agentId: string) => void) {
  mocks.loadTemplates.mockResolvedValue(templates);
  const view = render(<FeaturedExpertChips onSummoned={onSummoned} />);
  await settle();
  return view;
}

describe('FeaturedExpertChips', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.summon.mockReset();
    mocks.loadTemplates.mockReset();
    localStorage.clear();
    useChatStore.setState({ messages: [], inputMessage: '' });
  });

  it('labels teams and experts apart and uses the description, or else the name, as the tooltip', async () => {
    await mountWith([TEAM, EXPERT]);

    expect(chip('Architecture Squad')).toHaveTextContent('teamBadge');
    expect(chip('Architecture Squad')).toHaveAttribute('title', 'Lead architects and reviewers');
    expect(chip('DB Tuning Expert')).toHaveTextContent('expertBadge');
    expect(chip('DB Tuning Expert')).toHaveAttribute('title', 'DB Tuning Expert');
  });

  it('renders nothing when the service has no featured template to offer', async () => {
    const { container } = await mountWith([]);

    expect(container).toBeEmptyDOMElement();
  });

  describe('summoning', () => {
    it('welcomes the new team, reports it, prefills its first example and opens its chat', async () => {
      const onSummoned = vi.fn();
      mocks.summon.mockResolvedValue({ id: 'agent-new-123' });
      await mountWith([TEAM, EXPERT], onSummoned);

      fireEvent.click(chip('Architecture Squad'));
      await settle();

      expect(mocks.summon).toHaveBeenCalledWith({
        templateId: 'team-arch',
        surface: 'flow_pad_inline',
        trigger: 'use_case_chip',
        templateKind: 'team',
        fromSearch: false,
        usedUseCase: false,
      });
      expect(toast.success).toHaveBeenCalledWith('summonSuccess:{"name":"Architecture Squad"}');
      expect(useChatStore.getState().inputMessage).toBe('Review system refactoring plan');
      expect(onSummoned).toHaveBeenCalledWith('agent-new-123');
      expect(mocks.router.push).toHaveBeenCalledWith('/chat?agentId=agent-new-123');
    });

    it('summons an individual expert without example scenarios and leaves the composer empty', async () => {
      mocks.summon.mockResolvedValue({ id: 'agent-new-456' });
      await mountWith([TEAM, EXPERT]);

      fireEvent.click(chip('DB Tuning Expert'));
      await settle();

      expect(mocks.summon).toHaveBeenCalledWith(
        expect.objectContaining({ templateId: 'agent-db', templateKind: 'individual' }),
      );
      expect(useChatStore.getState().inputMessage).toBe('');
      expect(mocks.router.push).toHaveBeenCalledWith('/chat?agentId=agent-new-456');
    });

    it('locks every chip while one summon is in flight, and shows progress on the chosen one', async () => {
      const inFlight = deferred<{ id: string }>();
      mocks.summon.mockReturnValue(inFlight.promise);
      await mountWith([TEAM, EXPERT]);

      fireEvent.click(chip('Architecture Squad'));

      expect(chip('Architecture Squad')).toBeDisabled();
      expect(chip('DB Tuning Expert')).toBeDisabled();
      expect(chip('Architecture Squad').querySelector('.animate-spin')).not.toBeNull();
      expect(chip('DB Tuning Expert').querySelector('.animate-spin')).toBeNull();
      fireEvent.click(chip('DB Tuning Expert'));
      expect(mocks.summon).toHaveBeenCalledTimes(1);

      await act(async () => {
        inFlight.resolve({ id: 'agent-new-123' });
      });

      expect(chip('Architecture Squad')).toBeEnabled();
      expect(chip('Architecture Squad').querySelector('.animate-spin')).toBeNull();
    });

    it.each<[string, Error, string]>([
      ['the reason the service gave', new Error('Quota exceeded'), 'Quota exceeded'],
      ['a generic message when the failure carries no reason', new Error('   '), 'summonFailed'],
    ])('tells the viewer %s, and stays on the page', async (_label, failure, shown) => {
      const onSummoned = vi.fn();
      mocks.summon.mockRejectedValue(failure);
      await mountWith([TEAM, EXPERT], onSummoned);

      fireEvent.click(chip('Architecture Squad'));
      await settle();

      expect(toast.error).toHaveBeenCalledWith(shown);
      expect(toast.success).not.toHaveBeenCalled();
      expect(mocks.router.push).not.toHaveBeenCalled();
      expect(onSummoned).not.toHaveBeenCalled();
      expect(useChatStore.getState().inputMessage).toBe('');
      expect(chip('Architecture Squad')).toBeEnabled();
    });
  });
});
