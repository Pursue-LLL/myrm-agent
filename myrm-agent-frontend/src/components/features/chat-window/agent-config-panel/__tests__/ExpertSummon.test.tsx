/** @vitest-environment jsdom */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const mockGetTemplates = vi.fn();
const mockInstantiateTemplateWithMetrics = vi.fn();
const mockSetInputMessage = vi.fn();
const mockPush = vi.fn();

const stableT = (key: string, params?: Record<string, unknown>) => {
  if (params?.name) {
    return `${key}:${params.name}`;
  }
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/services/agent', () => ({
  getTemplates: (...args: unknown[]) => mockGetTemplates(...args),
}));

vi.mock('@/services/templateSummon', () => ({
  instantiateTemplateWithMetrics: (...args: unknown[]) => mockInstantiateTemplateWithMetrics(...args),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}));

vi.mock('@/store/useChatStore', () => ({
  default: (selector: (state: { setInputMessage: (message: string) => void }) => unknown) =>
    selector({
      setInputMessage: (message: string) => mockSetInputMessage(message),
    }),
}));

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

describe('FeaturedExpertChips & ExpertSummonPopover', () => {
  beforeEach(() => {
    mockGetTemplates.mockReset();
    mockInstantiateTemplateWithMetrics.mockReset();
    mockSetInputMessage.mockReset();
    mockPush.mockReset();
  });

  it('renders featured squad chips and summons on click', async () => {
    mockGetTemplates.mockResolvedValue([
      {
        id: 'team-arch',
        name: 'Architecture Squad',
        agent_type: 'team',
        description: 'Lead architects and reviewers',
        use_cases: ['Review system refactoring plan'],
      },
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
      fireEvent.click(squadBtn!);
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

    render(<ExpertSummonPopover />);

    const triggerBtn = screen.getByTestId('expert-summon-popover-trigger');
    await act(async () => {
      fireEvent.click(triggerBtn);
    });

    expect(screen.getByTestId('expert-summon-popover-menu')).toBeInTheDocument();
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
    expect(mockPush).toHaveBeenCalledWith('/chat?agentId=agent-qa-456');
  });
});
