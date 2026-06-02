import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SharedContextTargetBinding } from '../SharedContextTargetBinding';
import type { SharedContext, SharedContextBinding, SharedContextListResponse } from '@/services/memorySharedContexts';

const memoryApi = vi.hoisted(() => ({
  listSharedContexts: vi.fn(),
  listSharedContextBindingsForTarget: vi.fn(),
  createSharedContextBinding: vi.fn(),
  deleteSharedContextBinding: vi.fn(),
}));

const toastMock = vi.hoisted(() => vi.fn());
const translate = vi.hoisted(() => (key: string) => key);

vi.mock('next-intl', () => ({
  useTranslations: () => translate,
}));

vi.mock('@/services/memorySharedContexts', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/memorySharedContexts')>()),
  listSharedContexts: memoryApi.listSharedContexts,
  listSharedContextBindingsForTarget: memoryApi.listSharedContextBindingsForTarget,
  createSharedContextBinding: memoryApi.createSharedContextBinding,
  deleteSharedContextBinding: memoryApi.deleteSharedContextBinding,
}));

vi.mock('@/hooks/useToast', () => ({
  toast: toastMock,
}));

const sharedContext = (overrides: Partial<SharedContext>): SharedContext => ({
  id: 'customer-a',
  namespace: 'shared:customer-a',
  name: 'Customer A',
  description: 'Customer support operating context',
  status: 'active',
  policy: {},
  created_at: '2026-04-29T01:00:00Z',
  updated_at: '2026-04-29T01:00:00Z',
  ...overrides,
});

const binding = (overrides: Partial<SharedContextBinding>): SharedContextBinding => ({
  id: 'bind-1',
  context_id: 'customer-a',
  target_type: 'agent',
  target_id: 'agent-1',
  created_at: '2026-04-29T01:05:00Z',
  ...overrides,
});

const listResponse = (items: SharedContext[]): SharedContextListResponse => ({
  items,
  total: items.length,
});

describe('SharedContextTargetBinding', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    memoryApi.listSharedContexts.mockResolvedValue(listResponse([]));
    memoryApi.listSharedContextBindingsForTarget.mockResolvedValue({ items: [], total: 0 });
  });

  it('loads bound shared contexts for a runtime target', async () => {
    memoryApi.listSharedContexts.mockResolvedValue(
      listResponse([
        sharedContext({}),
        sharedContext({ id: 'ops', namespace: 'shared:ops', name: 'Ops', description: '' }),
      ]),
    );
    memoryApi.listSharedContextBindingsForTarget.mockResolvedValue({
      items: [binding({})],
      total: 1,
    });

    render(<SharedContextTargetBinding targetType="agent" targetId="agent-1" targetLabel="Writer Agent" />);

    expect(memoryApi.listSharedContexts).toHaveBeenCalledTimes(1);
    expect(memoryApi.listSharedContextBindingsForTarget).toHaveBeenCalledWith('agent', 'agent-1');
    expect(await screen.findByText('Customer A')).toBeInTheDocument();
    expect(screen.getByText('Customer support operating context')).toBeInTheDocument();
  });

  it('binds the selected context and removes it from available choices', async () => {
    const customerA = sharedContext({});
    const ops = sharedContext({ id: 'ops', namespace: 'shared:ops', name: 'Ops', description: 'Ops playbook' });
    memoryApi.listSharedContexts.mockResolvedValue(listResponse([customerA, ops]));
    memoryApi.createSharedContextBinding.mockResolvedValue(binding({ id: 'bind-ops', context_id: 'ops' }));

    const user = userEvent.setup();
    render(<SharedContextTargetBinding targetType="agent" targetId="agent-1" />);

    const select = await screen.findByRole('combobox');
    await waitFor(() => {
      expect(select).not.toBeDisabled();
      expect(screen.getByRole('option', { name: 'Ops' })).toBeInTheDocument();
    });
    await user.selectOptions(select, 'ops');
    await user.click(screen.getByRole('button', { name: /bind/ }));

    await waitFor(() => {
      expect(memoryApi.createSharedContextBinding).toHaveBeenCalledWith('ops', {
        target_type: 'agent',
        target_id: 'agent-1',
      });
    });
    expect(await screen.findByText('Ops')).toBeInTheDocument();
    expect(within(select).queryByRole('option', { name: 'Ops' })).not.toBeInTheDocument();
  });

  it('unbinds a bound context without touching other bindings', async () => {
    memoryApi.listSharedContexts.mockResolvedValue(
      listResponse([
        sharedContext({}),
        sharedContext({ id: 'ops', namespace: 'shared:ops', name: 'Ops', description: 'Ops playbook' }),
      ]),
    );
    memoryApi.listSharedContextBindingsForTarget.mockResolvedValue({
      items: [binding({}), binding({ id: 'bind-ops', context_id: 'ops' })],
      total: 2,
    });

    const user = userEvent.setup();
    render(<SharedContextTargetBinding targetType="agent" targetId="agent-1" />);

    expect(await screen.findByText('Customer A')).toBeInTheDocument();
    expect(screen.getByText('Ops')).toBeInTheDocument();

    const unbindButtons = screen.getAllByRole('button', { name: /unbind/ });
    await user.click(unbindButtons[0]);

    await waitFor(() => {
      expect(memoryApi.deleteSharedContextBinding).toHaveBeenCalledWith('customer-a', 'bind-1');
    });
    expect(screen.queryByText('Customer support operating context')).not.toBeInTheDocument();
    expect(screen.getByText('Ops')).toBeInTheDocument();
  });

  it('shows the unavailable state instead of loading when target is missing', () => {
    render(<SharedContextTargetBinding targetType="agent" targetId={null} targetLabel="Writer Agent" />);

    expect(screen.getByText('noTarget')).toBeInTheDocument();
    expect(memoryApi.listSharedContexts).not.toHaveBeenCalled();
    expect(memoryApi.listSharedContextBindingsForTarget).not.toHaveBeenCalled();
  });
});
