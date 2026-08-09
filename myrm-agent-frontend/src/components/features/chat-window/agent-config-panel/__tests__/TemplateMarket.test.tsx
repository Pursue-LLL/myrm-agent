/** @vitest-environment jsdom */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const mockGetTemplates = vi.fn();
const mockInstantiateTemplateWithMetrics = vi.fn();
const mockSetInputMessage = vi.fn();
const mockPush = vi.fn();

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/lib/backend-health', () => ({
  ensureLocalBackendReady: vi.fn().mockResolvedValue(true),
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

vi.mock('@/components/agent/agent-icons', () => ({
  resolveLucideIcon: () => null,
}));

import TemplateMarket from '../TemplateMarket';

describe('TemplateMarket', () => {
  beforeEach(() => {
    mockGetTemplates.mockReset();
    mockInstantiateTemplateWithMetrics.mockReset();
    mockSetInputMessage.mockReset();
    mockPush.mockReset();
  });

  it('supports keyword search over team use cases', async () => {
    mockGetTemplates.mockResolvedValue([
      {
        id: 'team-cloudq',
        name: 'CloudQ Team',
        description: 'Cloud incident experts',
        avatar_url: '',
        agent_type: 'team',
        members: [{ role: 'lead', name: 'CloudQ', description: 'Incident commander' }],
        use_cases: ['Diagnose cloud outage', 'Review migration risks'],
      },
      {
        id: 'individual-writer',
        name: 'Writer Agent',
        description: 'Writing expert',
        avatar_url: '',
        agent_type: 'normal',
      },
    ]);
    mockInstantiateTemplateWithMetrics.mockResolvedValue({ id: 'team-cloudq-instance' });

    render(<TemplateMarket />);

    expect(await screen.findByText('CloudQ Team')).toBeInTheDocument();
    expect(screen.getByText('Writer Agent')).toBeInTheDocument();

    const searchInput = screen.getByPlaceholderText('searchMarketplace');
    fireEvent.change(searchInput, { target: { value: 'migration risks' } });

    expect(await screen.findByText('CloudQ Team')).toBeInTheDocument();
    expect(screen.queryByText('Writer Agent')).not.toBeInTheDocument();
  });

  it('instantiates from use_case chip and prefills input message', async () => {
    mockGetTemplates.mockResolvedValue([
      {
        id: 'team-cloudq',
        name: 'CloudQ Team',
        description: 'Cloud incident experts',
        avatar_url: '',
        agent_type: 'team',
        members: [{ role: 'lead', name: 'CloudQ', description: 'Incident commander' }],
        use_cases: ['Diagnose cloud outage'],
      },
    ]);
    mockInstantiateTemplateWithMetrics.mockResolvedValue({ id: 'team-cloudq-instance' });
    const onInstantiated = vi.fn();

    render(<TemplateMarket onInstantiated={onInstantiated} />);

    const useCaseChip = await screen.findByRole('button', { name: 'Diagnose cloud outage' });
    await act(async () => {
      fireEvent.click(useCaseChip);
    });

    expect(mockInstantiateTemplateWithMetrics).toHaveBeenCalledWith(
      expect.objectContaining({
        templateId: 'team-cloudq',
        surface: 'template_market',
        trigger: 'use_case_chip',
      }),
    );
    expect(mockSetInputMessage).toHaveBeenCalledWith('Diagnose cloud outage');
    expect(onInstantiated).toHaveBeenCalledWith('team-cloudq-instance');
  });

  it('supports keyboard summon on team card', async () => {
    mockGetTemplates.mockResolvedValue([
      {
        id: 'team-cloudq',
        name: 'CloudQ Team',
        description: 'Cloud incident experts',
        avatar_url: '',
        agent_type: 'team',
        members: [{ role: 'lead', name: 'CloudQ', description: 'Incident commander' }],
        use_cases: ['Diagnose cloud outage'],
      },
    ]);
    mockInstantiateTemplateWithMetrics.mockResolvedValue({ id: 'team-cloudq-instance' });

    render(<TemplateMarket />);

    const teamCard = await screen.findByRole('button', { name: /CloudQ Team/ });
    await act(async () => {
      fireEvent.keyDown(teamCard, { key: 'Enter' });
    });

    expect(mockInstantiateTemplateWithMetrics).toHaveBeenCalledWith(
      expect.objectContaining({
        templateId: 'team-cloudq',
        trigger: 'template_card',
      }),
    );
  });
});
