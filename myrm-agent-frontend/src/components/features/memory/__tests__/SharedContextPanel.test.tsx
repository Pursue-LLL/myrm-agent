import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import SharedContextPanel from '../SharedContextPanel';
import type {
  SharedContext,
  SharedContextBinding,
  SharedContextHistoryMessage,
  SharedContextWriteProposal,
} from '@/services/memorySharedContexts';

const memoryApi = vi.hoisted(() => ({
  getSharedContextMemoryHealth: vi.fn(),
  listSharedContexts: vi.fn(),
  createSharedContext: vi.fn(),
  updateSharedContext: vi.fn(),
  archiveSharedContext: vi.fn(),
  listSharedContextBindings: vi.fn(),
  createSharedContextBinding: vi.fn(),
  deleteSharedContextBinding: vi.fn(),
  listSharedContextWriteProposals: vi.fn(),
  createSharedContextWriteProposal: vi.fn(),
  updateSharedContextWriteProposal: vi.fn(),
  approveSharedContextWriteProposal: vi.fn(),
  rejectSharedContextWriteProposal: vi.fn(),
  searchSharedContextHistory: vi.fn(),
  createSharedContextProposalFromHistory: vi.fn(),
}));

const agentApi = vi.hoisted(() => ({
  listAgents: vi.fn(),
}));

const channelApi = vi.hoisted(() => ({
  listChannelInstances: vi.fn(),
}));

const cronApi = vi.hoisted(() => ({
  listCronJobs: vi.fn(),
}));

const toastMock = vi.hoisted(() => vi.fn());
const translate = vi.hoisted(() => (key: string) => key);

vi.mock('next-intl', () => ({
  useTranslations: () => translate,
  useLocale: () => 'en',
}));

vi.mock('@/services/memorySharedContexts', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/memorySharedContexts')>()),
  listSharedContexts: memoryApi.listSharedContexts,
  createSharedContext: memoryApi.createSharedContext,
  updateSharedContext: memoryApi.updateSharedContext,
  archiveSharedContext: memoryApi.archiveSharedContext,
  listSharedContextBindings: memoryApi.listSharedContextBindings,
  createSharedContextBinding: memoryApi.createSharedContextBinding,
  deleteSharedContextBinding: memoryApi.deleteSharedContextBinding,
  listSharedContextWriteProposals: memoryApi.listSharedContextWriteProposals,
  createSharedContextWriteProposal: memoryApi.createSharedContextWriteProposal,
  updateSharedContextWriteProposal: memoryApi.updateSharedContextWriteProposal,
  approveSharedContextWriteProposal: memoryApi.approveSharedContextWriteProposal,
  rejectSharedContextWriteProposal: memoryApi.rejectSharedContextWriteProposal,
  searchSharedContextHistory: memoryApi.searchSharedContextHistory,
  createSharedContextProposalFromHistory: memoryApi.createSharedContextProposalFromHistory,
}));

vi.mock('@/services/memory-health', () => ({
  getSharedContextMemoryHealth: memoryApi.getSharedContextMemoryHealth,
}));

vi.mock('@/services/agent', () => ({
  listAgents: agentApi.listAgents,
}));

vi.mock('@/services/channels', () => ({
  listChannelInstances: channelApi.listChannelInstances,
}));

vi.mock('@/services/cron', () => ({
  listCronJobs: cronApi.listCronJobs,
}));

vi.mock('@/hooks/useToast', () => ({
  toast: toastMock,
}));

const sharedContext = (overrides: Partial<SharedContext>): SharedContext => ({
  id: 'customer-a',
  namespace: 'shared:customer-a',
  name: 'Customer A',
  description: 'Customer support context',
  status: 'active',
  policy: {},
  created_at: '2026-04-29T01:00:00Z',
  updated_at: '2026-04-29T01:00:00Z',
  ...overrides,
});

const binding = (overrides: Partial<SharedContextBinding>): SharedContextBinding => ({
  id: 'binding-1',
  context_id: 'customer-a',
  target_type: 'agent',
  target_id: 'agent-1',
  created_at: '2026-04-29T01:05:00Z',
  ...overrides,
});

const proposal = (overrides: Partial<SharedContextWriteProposal>): SharedContextWriteProposal => ({
  id: 'proposal-1',
  context_id: 'customer-a',
  memory_type: 'semantic',
  content: 'Customer A prefers concise weekly summaries.',
  metadata: {},
  source_type: 'manual',
  status: 'pending',
  created_at: '2026-04-29T01:10:00Z',
  resolved_at: null,
  ...overrides,
});

const historyHit = (overrides: Partial<SharedContextHistoryMessage>): SharedContextHistoryMessage => ({
  message_id: 'message-1',
  chat_id: 'chat-1',
  role: 'assistant',
  content: 'Customer A asked us to include incident trend charts.',
  snippet: 'incident trend charts',
  chat_title: 'Customer A weekly planning',
  sent_at: '2026-04-29T01:15:00Z',
  ...overrides,
});

describe('SharedContextPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    memoryApi.getSharedContextMemoryHealth.mockResolvedValue({
      ready: true,
      status: 'ready',
      model: 'text-embedding-3-small',
      api_base_configured: false,
      api_key_configured: true,
      probed: false,
      reason: 'probe_skipped',
      retryable: false,
      checked_at: '2026-04-30T00:00:00Z',
      vector_dimension: null,
    });
    memoryApi.listSharedContexts.mockResolvedValue({ items: [sharedContext({})], total: 1 });
    memoryApi.listSharedContextBindings.mockResolvedValue({ items: [], total: 0 });
    memoryApi.listSharedContextWriteProposals.mockResolvedValue({ items: [], total: 0 });
    memoryApi.createSharedContext.mockImplementation(async (body: { name: string; description?: string }) =>
      sharedContext({
        id: 'new-context',
        namespace: 'shared:new-context',
        name: body.name,
        description: body.description ?? '',
      }),
    );
    memoryApi.updateSharedContext.mockImplementation(
      async (contextId: string, body: { policy?: Record<string, unknown> }) =>
        sharedContext({
          id: contextId,
          policy: body.policy ?? {},
        }),
    );
    memoryApi.archiveSharedContext.mockResolvedValue(sharedContext({ status: 'archived' }));
    memoryApi.createSharedContextBinding.mockResolvedValue(binding({}));
    memoryApi.deleteSharedContextBinding.mockResolvedValue(undefined);
    memoryApi.createSharedContextWriteProposal.mockResolvedValue(proposal({}));
    memoryApi.updateSharedContextWriteProposal.mockResolvedValue(proposal({ content: 'Updated proposal content' }));
    memoryApi.approveSharedContextWriteProposal.mockResolvedValue(proposal({ status: 'approved' }));
    memoryApi.rejectSharedContextWriteProposal.mockResolvedValue(proposal({ status: 'rejected' }));
    memoryApi.searchSharedContextHistory.mockResolvedValue({
      context_id: 'customer-a',
      query: 'incident',
      items: [historyHit({})],
      total: 1,
    });
    memoryApi.createSharedContextProposalFromHistory.mockResolvedValue(
      proposal({ id: 'proposal-from-history', source_type: 'history_message', source_id: 'message-1' }),
    );
    agentApi.listAgents.mockResolvedValue({ items: [{ id: 'agent-1', name: 'Writer Agent' }] });
    channelApi.listChannelInstances.mockResolvedValue([]);
    cronApi.listCronJobs.mockResolvedValue({ items: [] });
  });

  it('creates a shared context and selects it for management', async () => {
    const user = userEvent.setup();
    render(<SharedContextPanel />);

    expect(await screen.findAllByText('Customer A')).not.toHaveLength(0);
    await user.type(screen.getByPlaceholderText('create.namePlaceholder'), 'Launch Plan');
    await user.type(screen.getByPlaceholderText('create.descriptionPlaceholder'), 'Go-to-market memory pack');
    await user.click(screen.getByRole('button', { name: /create\.submit/ }));

    await waitFor(() => {
      expect(memoryApi.createSharedContext).toHaveBeenCalledWith({
        name: 'Launch Plan',
        description: 'Go-to-market memory pack',
      });
    });
  });

  it('shows Shared Context memory health and supports a live probe', async () => {
    memoryApi.getSharedContextMemoryHealth
      .mockResolvedValueOnce({
        ready: false,
        status: 'not_configured',
        model: 'text-embedding-3-small',
        api_base_configured: false,
        api_key_configured: false,
        probed: false,
        reason: 'placeholder_embedding_api_key',
        retryable: false,
        checked_at: '2026-04-30T00:00:00Z',
        vector_dimension: null,
      })
      .mockResolvedValueOnce({
        ready: true,
        status: 'ready',
        model: 'text-embedding-3-small',
        api_base_configured: false,
        api_key_configured: true,
        probed: true,
        reason: null,
        retryable: false,
        checked_at: '2026-04-30T00:00:01Z',
        vector_dimension: 1536,
      });

    const user = userEvent.setup();
    render(<SharedContextPanel />);

    expect(await screen.findByText('reason.placeholder_embedding_api_key')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /actions\.probe/ }));

    await waitFor(() => {
      expect(memoryApi.getSharedContextMemoryHealth).toHaveBeenLastCalledWith(true);
    });
    expect(await screen.findByText('reason.ready')).toBeInTheDocument();
  });

  it('binds an agent target from the Memory Center', async () => {
    memoryApi.listSharedContextBindings.mockResolvedValue({ items: [], total: 0 });
    memoryApi.createSharedContextBinding.mockResolvedValue(binding({}));

    const user = userEvent.setup();
    render(<SharedContextPanel />);

    expect(await screen.findAllByText('Customer A')).not.toHaveLength(0);
    const bindingSection = screen.getByText('bindings.title').closest('section');
    expect(bindingSection).not.toBeNull();
    const targetSelects = within(bindingSection as HTMLElement).getAllByRole('combobox');
    await user.selectOptions(targetSelects[1], 'agent-1');
    await user.click(within(bindingSection as HTMLElement).getByRole('button', { name: /bindings\.bind/ }));

    await waitFor(() => {
      expect(memoryApi.createSharedContextBinding).toHaveBeenCalledWith('customer-a', {
        target_type: 'agent',
        target_id: 'agent-1',
      });
    });
  });

  it('edits, approves and promotes governed write proposals', async () => {
    memoryApi.listSharedContextWriteProposals.mockResolvedValue({
      items: [proposal({})],
      total: 1,
    });

    const user = userEvent.setup();
    render(<SharedContextPanel />);

    expect(await screen.findByText('Customer A prefers concise weekly summaries.')).toBeInTheDocument();

    await user.click(screen.getAllByRole('button', { name: 'edit' })[0]);
    const editBox = screen.getByDisplayValue('Customer A prefers concise weekly summaries.');
    await user.clear(editBox);
    await user.type(editBox, 'Updated proposal content');
    await user.click(screen.getByRole('button', { name: 'actions.saveProposal' }));

    await waitFor(() => {
      expect(memoryApi.updateSharedContextWriteProposal).toHaveBeenCalledWith('proposal-1', {
        content: 'Updated proposal content',
      });
    });

    const proposalSection = screen.getByText('proposals.title').closest('section');
    expect(proposalSection).not.toBeNull();
    await user.click(within(proposalSection as HTMLElement).getByRole('button', { name: 'actions.approveProposal' }));
    await waitFor(() => {
      expect(memoryApi.approveSharedContextWriteProposal).toHaveBeenCalledWith('proposal-1');
    });

    await user.type(screen.getByPlaceholderText('history.searchPlaceholder'), 'incident');
    await user.click(screen.getByRole('button', { name: /history\.search/ }));
    expect(await screen.findByText('Customer A asked us to include incident trend charts.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /history\.promote/ }));
    await waitFor(() => {
      expect(memoryApi.createSharedContextProposalFromHistory).toHaveBeenCalledWith('customer-a', {
        message_id: 'message-1',
        memory_type: 'semantic',
      });
    });
  }, 15000);

  it('shows goal completion proposal tag in inbox', async () => {
    memoryApi.listSharedContextWriteProposals.mockResolvedValue({
      items: [proposal({ source_type: 'goal_completion', source_id: 'goal-1' })],
      total: 1,
    });

    render(<SharedContextPanel />);

    expect(await screen.findByText('proposals.goalCompletionTag')).toBeInTheDocument();
  });

  it('toggles goal completion auto-archive policy', async () => {
    const user = userEvent.setup();
    render(<SharedContextPanel />);

    expect(await screen.findByText('policy.goalCompletionAutoApprove')).toBeInTheDocument();
    const switches = screen.getAllByRole('switch');
    const goalSwitch = switches[switches.length - 1];
    await user.click(goalSwitch);

    await waitFor(() => {
      expect(memoryApi.updateSharedContext).toHaveBeenCalledWith('customer-a', {
        policy: { goal_completion_auto_approve: false },
      });
    });
  });

  it('rejects pending governed write proposals', async () => {
    memoryApi.listSharedContextWriteProposals.mockResolvedValue({
      items: [proposal({})],
      total: 1,
    });

    const user = userEvent.setup();
    render(<SharedContextPanel />);

    expect(await screen.findByText('Customer A prefers concise weekly summaries.')).toBeInTheDocument();
    const proposalSection = screen.getByText('proposals.title').closest('section');
    expect(proposalSection).not.toBeNull();
    await user.click(within(proposalSection as HTMLElement).getByRole('button', { name: 'actions.rejectProposal' }));

    await waitFor(() => {
      expect(memoryApi.rejectSharedContextWriteProposal).toHaveBeenCalledWith('proposal-1');
    });
  });

  it('keeps archived shared contexts readable but blocks new writes', async () => {
    const archivedContext = sharedContext({ status: 'archived' });
    memoryApi.listSharedContexts.mockResolvedValue({
      items: [archivedContext],
      total: 1,
    });
    memoryApi.listSharedContexts.mockResolvedValueOnce({
      items: [archivedContext],
      total: 1,
    });
    memoryApi.listSharedContextWriteProposals.mockResolvedValue({ items: [proposal({})], total: 1 });

    const user = userEvent.setup();
    render(<SharedContextPanel />);

    expect(await screen.findByText('archivedNotice')).toBeInTheDocument();
    expect(await screen.findByText('Customer A prefers concise weekly summaries.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /bindings\.bind/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: /proposals\.create/ })).toBeDisabled();

    await user.type(screen.getByPlaceholderText('history.searchPlaceholder'), 'incident');
    await user.click(screen.getByRole('button', { name: /history\.search/ }));
    expect(await screen.findByText('Customer A asked us to include incident trend charts.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /history\.promote/ })).toBeDisabled();
  }, 15000);
});
