import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import MemoryCitationsButton from '../MemoryCitationsButton';
import type { SharedContext } from '@/services/memorySharedContexts';

const memoryApi = vi.hoisted(() => ({
  listSharedContexts: vi.fn(),
}));
const translate = vi.hoisted(() => (key: string) => key);

vi.mock('next-intl', () => ({
  useTranslations: () => translate,
  useLocale: () => 'en',
}));

vi.mock('@/services/memorySharedContexts', () => ({
  listSharedContexts: memoryApi.listSharedContexts,
}));

const sharedContext = (overrides: Partial<SharedContext>): SharedContext => ({
  id: 'customer-a',
  namespace: 'shared:customer-a',
  name: 'Customer A',
  description: '',
  status: 'active',
  policy: {},
  created_at: '2026-04-29T01:00:00Z',
  updated_at: '2026-04-29T01:00:00Z',
  ...overrides,
});

describe('MemoryCitationsButton', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    memoryApi.listSharedContexts.mockResolvedValue({
      items: [sharedContext({})],
      total: 1,
    });
  });

  it('does not render without cited memory ids, references, or sources', () => {
    const { container } = render(<MemoryCitationsButton />);

    expect(container).toBeEmptyDOMElement();
  });

  it('renders unified evidence when only message sources are present', async () => {
    const user = userEvent.setup();
    render(
      <MemoryCitationsButton
        sources={[
          {
            index: 1,
            type: 'conversation_history',
            conversation_id: 'chat-history',
            message_id: 'msg-1',
            title: 'Prior decision',
          },
        ]}
      />,
    );

    await user.click(screen.getByRole('button', { name: /buttonAria/ }));

    expect(screen.getByText('title')).toBeInTheDocument();
    expect(screen.getByText('Prior decision')).toBeInTheDocument();
  });

  it('opens citation sheet and resolves shared context namespace labels', async () => {
    const user = userEvent.setup();
    render(
      <MemoryCitationsButton
        memoryIds={['mem-2']}
        references={[
          {
            id: 'mem-1',
            memoryType: 'semantic',
            content: 'Customer A prefers concise weekly summaries.',
            score: 0.93,
            primaryNamespace: 'shared:customer-a',
            namespaces: ['global', 'shared:customer-a'],
          },
        ]}
      />,
    );

    await user.click(screen.getByRole('button', { name: /buttonAria/ }));

    expect(screen.getByText('title')).toBeInTheDocument();
    expect(screen.getByText('Customer A prefers concise weekly summaries.')).toBeInTheDocument();
    expect(screen.getByText('score')).toBeInTheDocument();
    expect(screen.getByText('mem-2')).toBeInTheDocument();
    await waitFor(() => {
      expect(memoryApi.listSharedContexts).toHaveBeenCalledTimes(1);
    });
    expect(await screen.findByText('Customer A')).toBeInTheDocument();
  });

  it('renders degraded notice when recall degraded and no evidence', () => {
    render(<MemoryCitationsButton degraded />);

    expect(screen.getByText('degradedNotice')).toBeInTheDocument();
  });

  it('renders nothing when recall degraded but evidence exists', () => {
    const { container } = render(
      <MemoryCitationsButton
        degraded
        references={[
          {
            id: 'mem-1',
            content: 'Customer A prefers concise weekly summaries.',
            memoryType: 'semantic',
            score: 0.92,
            primaryNamespace: 'user',
          },
        ]}
      />,
    );

    expect(screen.getByText('button')).toBeInTheDocument();
    expect(container.querySelector('[title="degradedNoticeTitle"]')).toBeNull();
  });
});
