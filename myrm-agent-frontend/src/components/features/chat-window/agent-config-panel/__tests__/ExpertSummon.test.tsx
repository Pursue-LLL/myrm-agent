/** @vitest-environment jsdom */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { hydrateRoot } from 'react-dom/client';
import { renderToString } from 'react-dom/server';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { expectNonNull } from '@/test-utils/expectDefined';

const mockGetTemplates = vi.fn();
const mockInstantiateTemplateWithMetrics = vi.fn();
const mockSetInputMessage = vi.fn();
const mockPush = vi.fn();
const chatState = vi.hoisted(() => ({ messages: [] as unknown[], inputMessage: '' }));

const stableT = (key: string, params?: Record<string, unknown>) => {
  if (params?.name) {
    return `${key}:${params.name}`;
  }
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/services/agentTemplates', () => ({
  getTemplates: (...args: unknown[]) => mockGetTemplates(...args),
}));

vi.mock('@/services/templateSummon', () => ({
  instantiateTemplateWithMetrics: (...args: unknown[]) => mockInstantiateTemplateWithMetrics(...args),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}));

vi.mock('@/store/useChatStore', () => {
  const useChatStore = (selector: (state: typeof chatState) => unknown) => selector(chatState);
  useChatStore.getState = () => ({
    inputMessage: chatState.inputMessage,
    setInputMessage: (message: string) => mockSetInputMessage(message),
  });
  return { default: useChatStore };
});

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
    promise: vi.fn(),
    loading: vi.fn(),
    dismiss: vi.fn(),
    message: vi.fn(),
  },
}));

import { FeaturedExpertChips } from '../FeaturedExpertChips';
import { ExpertSummonPopover } from '../ExpertSummonPopover';
import { invalidateFeaturedTemplates } from '@/services/featuredTemplates';

const TEAM_TEMPLATE = {
  id: 'team-arch',
  name: 'Architecture Squad',
  agent_type: 'team',
  description: 'Lead architects and reviewers',
  use_cases: ['Review system refactoring plan'],
};

describe('FeaturedExpertChips & ExpertSummonPopover', () => {
  beforeEach(() => {
    mockGetTemplates.mockReset();
    mockInstantiateTemplateWithMetrics.mockReset();
    mockSetInputMessage.mockReset();
    mockPush.mockReset();
    chatState.messages = [];
    chatState.inputMessage = '';
    localStorage.clear();
    invalidateFeaturedTemplates();
  });

  it('renders featured squad chips and summons on click', async () => {
    mockGetTemplates.mockResolvedValue([
      TEAM_TEMPLATE,
      {
        id: 'agent-db',
        name: 'DB Tuning Expert',
        agent_type: 'individual',
        is_pareto_preset: true,
        use_cases: ['Analyze slow queries'],
      },
    ]);

    mockInstantiateTemplateWithMetrics.mockResolvedValue({ id: 'agent-new-123' });

    await act(async () => {
      render(<FeaturedExpertChips />);
    });

    expect(screen.getByTestId('featured-expert-chips')).toBeInTheDocument();
    expect(screen.getByText('Architecture Squad')).toBeInTheDocument();
    expect(screen.getByText('DB Tuning Expert')).toBeInTheDocument();

    const squadBtn = screen.getByText('Architecture Squad').closest('button');
    expect(squadBtn).not.toBeNull();

    await act(async () => {
      expectNonNull(squadBtn, 'squadBtn');
      fireEvent.click(squadBtn);
    });

    expect(mockInstantiateTemplateWithMetrics).toHaveBeenCalledWith(
      expect.objectContaining({
        templateId: 'team-arch',
        surface: 'flow_pad_inline',
        trigger: 'use_case_chip',
      }),
    );
    expect(mockSetInputMessage).toHaveBeenCalledWith('Review system refactoring plan');
    expect(mockPush).toHaveBeenCalledWith('/chat?agentId=agent-new-123');
  });

  it('never replaces text the viewer already typed when a chip is summoned', async () => {
    chatState.inputMessage = 'my own draft';
    mockGetTemplates.mockResolvedValue([TEAM_TEMPLATE]);
    mockInstantiateTemplateWithMetrics.mockResolvedValue({ id: 'agent-new-123' });

    await act(async () => {
      render(<FeaturedExpertChips />);
    });
    await act(async () => {
      fireEvent.click(screen.getByText('Architecture Squad'));
    });

    expect(mockSetInputMessage).not.toHaveBeenCalled();
    expect(mockPush).toHaveBeenCalledWith('/chat?agentId=agent-new-123');
  });

  it('keeps the strip a single swipeable row at every width: icon-only title, bounded names, edge fade', async () => {
    mockGetTemplates.mockResolvedValue([
      { id: 'team-arch', name: 'Architecture Squad', agent_type: 'team', use_cases: [] },
    ]);

    await act(async () => {
      render(<FeaturedExpertChips />);
    });

    // The title stays in the DOM for assistive tech and the tooltip; only its icon is drawn.
    expect(screen.getByText('featuredTitle')).toHaveClass('sr-only');
    expect(screen.getByText('Architecture Squad')).toHaveClass('truncate', 'max-w-[8rem]', 'sm:max-w-[10rem]');

    // Wrapping would make the height depend on the chip names, and the placeholder could no longer be the same box.
    const strip = screen.getByTestId('featured-expert-chips').querySelector('.scroll-fade-x');
    expectNonNull(strip, 'strip');
    expect(strip).toHaveClass('overflow-x-auto');
    expect(strip.className).not.toContain('flex-wrap');
    expect(strip).toHaveAttribute('data-fade-end');
  });

  it('only appears in an empty conversation and does not even ask for templates elsewhere', async () => {
    chatState.messages = [{ role: 'user' }];
    mockGetTemplates.mockResolvedValue([TEAM_TEMPLATE]);

    await act(async () => {
      render(<FeaturedExpertChips />);
    });

    expect(screen.queryByTestId('featured-expert-chips')).toBeNull();
    expect(screen.queryByTestId('featured-expert-chips-skeleton')).toBeNull();
    expect(mockGetTemplates).not.toHaveBeenCalled();
  });

  it('holds the strip place with a placeholder until the templates arrive', async () => {
    let resolveTemplates: (templates: unknown[]) => void = () => {};
    mockGetTemplates.mockReturnValue(
      new Promise((resolve) => {
        resolveTemplates = resolve;
      }),
    );

    await act(async () => {
      render(<FeaturedExpertChips />);
    });

    expect(screen.getByTestId('featured-expert-chips-skeleton')).toHaveAttribute('aria-hidden', 'true');
    expect(screen.queryByTestId('featured-expert-chips')).toBeNull();

    await act(async () => {
      resolveTemplates([TEAM_TEMPLATE]);
    });

    expect(screen.getByTestId('featured-expert-chips')).toBeInTheDocument();
    expect(screen.queryByTestId('featured-expert-chips-skeleton')).toBeNull();
  });

  it('renders nothing, not a stuck placeholder, when the templates cannot be loaded', async () => {
    mockGetTemplates.mockRejectedValue(new Error('offline'));

    await act(async () => {
      render(<FeaturedExpertChips />);
    });

    expect(screen.queryByTestId('featured-expert-chips')).toBeNull();
    expect(screen.queryByTestId('featured-expert-chips-skeleton')).toBeNull();
  });

  it('asks for the templates once for concurrent and repeated mounts inside the cache window', async () => {
    mockGetTemplates.mockResolvedValue([TEAM_TEMPLATE]);

    let first!: ReturnType<typeof render>;
    await act(async () => {
      first = render(
        <>
          <FeaturedExpertChips />
          <FeaturedExpertChips />
        </>,
      );
    });
    expect(mockGetTemplates).toHaveBeenCalledTimes(1);

    first.unmount();
    await act(async () => {
      render(<FeaturedExpertChips />);
    });

    // A cached answer renders the chips directly, with no placeholder in between.
    expect(screen.getByTestId('featured-expert-chips')).toBeInTheDocument();
    expect(mockGetTemplates).toHaveBeenCalledTimes(1);
  });

  it('stays closed after the viewer dismisses it, also on the next mount', async () => {
    mockGetTemplates.mockResolvedValue([TEAM_TEMPLATE]);

    let first!: ReturnType<typeof render>;
    await act(async () => {
      first = render(<FeaturedExpertChips />);
    });
    await act(async () => {
      fireEvent.click(screen.getByLabelText('featuredDismiss'));
    });

    expect(screen.queryByTestId('featured-expert-chips')).toBeNull();
    expect(localStorage.getItem('myrm.proactive.dismissed.featured-experts')).toBe('forever');

    first.unmount();
    await act(async () => {
      render(<FeaturedExpertChips />);
    });
    expect(screen.queryByTestId('featured-expert-chips')).toBeNull();
    expect(screen.queryByTestId('featured-expert-chips-skeleton')).toBeNull();
  });

  it('does not request templates while hydrating a strip the viewer already dismissed', async () => {
    localStorage.setItem('myrm.proactive.dismissed.featured-experts', 'forever');
    mockGetTemplates.mockResolvedValue([TEAM_TEMPLATE]);

    // The server cannot read storage, so its HTML (and the hydration pass) still holds the placeholder.
    const container = document.createElement('div');
    document.body.appendChild(container);
    container.innerHTML = renderToString(<FeaturedExpertChips />);
    expect(container.querySelector('[data-testid="featured-expert-chips-skeleton"]')).not.toBeNull();

    let root!: ReturnType<typeof hydrateRoot>;
    await act(async () => {
      root = hydrateRoot(container, <FeaturedExpertChips />);
    });

    expect(container.querySelector('[data-testid="featured-expert-chips-skeleton"]')).toBeNull();
    expect(mockGetTemplates).not.toHaveBeenCalled();

    act(() => root.unmount());
    container.remove();
  });

  it('opens expert summon popover and searches templates', async () => {
    mockGetTemplates.mockResolvedValue([
      {
        id: 'team-qa',
        name: 'QA Audit Squad',
        agent_type: 'team',
        description: 'End-to-end testing and quality control',
        use_cases: ['Verify checkout flow'],
      },
    ]);

    mockInstantiateTemplateWithMetrics.mockResolvedValue({ id: 'agent-qa-456' });

    const { container } = render(<ExpertSummonPopover />);

    const triggerBtn = screen.getByTestId('expert-summon-popover-trigger');
    await act(async () => {
      fireEvent.click(triggerBtn);
    });

    const menu = screen.getByTestId('expert-summon-popover-menu');
    expect(menu).toBeInTheDocument();
    // The toolbar scroller clips inline popups, so the menu must be portaled out of it.
    expect(container).not.toContainElement(menu);
    expect(screen.getByPlaceholderText('searchPlaceholder')).toHaveFocus();
    expect(await screen.findByText('QA Audit Squad')).toBeInTheDocument();

    const summonBtn = screen.getByRole('button', { name: /summonButton/i });
    await act(async () => {
      fireEvent.click(summonBtn);
    });

    expect(mockInstantiateTemplateWithMetrics).toHaveBeenCalledWith(
      expect.objectContaining({
        templateId: 'team-qa',
        surface: 'flow_pad_inline',
      }),
    );
    expect(mockSetInputMessage).toHaveBeenCalledWith('Verify checkout flow');
    expect(mockPush).toHaveBeenCalledWith('/chat?agentId=agent-qa-456');
  });

  it('keeps a draft in place when a template is summoned from the popover', async () => {
    chatState.inputMessage = 'my own draft';
    mockGetTemplates.mockResolvedValue([TEAM_TEMPLATE]);
    mockInstantiateTemplateWithMetrics.mockResolvedValue({ id: 'agent-new-123' });

    render(<ExpertSummonPopover />);
    await act(async () => {
      fireEvent.click(screen.getByTestId('expert-summon-popover-trigger'));
    });
    await act(async () => {
      fireEvent.click(await screen.findByText('Review system refactoring plan'));
    });

    expect(mockSetInputMessage).not.toHaveBeenCalled();
    expect(mockPush).toHaveBeenCalledWith('/chat?agentId=agent-new-123');
  });
});
