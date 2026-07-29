/** @vitest-environment jsdom */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const mockGetTemplates = vi.fn();
const mockInstantiateTemplate = vi.fn();
const mockSetInputMessage = vi.fn();
const mockPush = vi.fn();

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('@/lib/backend-health', () => ({
  ensureLocalBackendReady: vi.fn().mockResolvedValue(true),
}));

vi.mock('@/services/agent', () => ({
  getTemplates: (...args: unknown[]) => mockGetTemplates(...args),
  instantiateTemplate: (...args: unknown[]) => mockInstantiateTemplate(...args),
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
  },
}));

vi.mock('@/components/agent/agent-icons', () => ({
  resolveLucideIcon: () => null,
}));

import TemplateMarket from '../TemplateMarket';

describe('TemplateMarket', () => {
  beforeEach(() => {
    mockGetTemplates.mockReset();
    mockInstantiateTemplate.mockReset();
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
    mockInstantiateTemplate.mockResolvedValue({ id: 'team-cloudq-instance' });

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
    mockInstantiateTemplate.mockResolvedValue({ id: 'team-cloudq-instance' });
    const onInstantiated = vi.fn();

    render(<TemplateMarket onInstantiated={onInstantiated} />);

    const useCaseChip = await screen.findByRole('button', { name: 'Diagnose cloud outage' });
    await act(async () => {
      fireEvent.click(useCaseChip);
    });

    expect(mockInstantiateTemplate).toHaveBeenCalledWith('team-cloudq');
    expect(mockSetInputMessage).toHaveBeenCalledWith('Diagnose cloud outage');
    expect(onInstantiated).toHaveBeenCalledWith('team-cloudq-instance');
  });
});
