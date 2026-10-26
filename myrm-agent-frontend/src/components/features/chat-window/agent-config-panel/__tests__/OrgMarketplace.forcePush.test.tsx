/** @vitest-environment jsdom */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { toast } from 'sonner';

import { confirmAction } from '@/lib/app-dialog';
import { getMyOrg, listMembers } from '@/services/enterprise-org';
import { forcePushUpdate, listMarketplaceEntries, type MarketplaceEntry } from '@/services/marketplace';
import OrgMarketplace from '../OrgMarketplace';

const stableT = (key: string, values?: Record<string, string | number>) =>
  values ? `${key}:${Object.values(values).join('|')}` : key;
vi.mock('next-intl', () => ({ useTranslations: () => stableT }));
const router = { push: vi.fn() };
vi.mock('next/navigation', () => ({ useRouter: () => router }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/lib/app-dialog', () => ({ confirmAction: vi.fn() }));
vi.mock('@/lib/deploy-mode', () => ({ isSandbox: () => true }));
vi.mock('@/store/useAuthStore', () => ({
  default: (select: (state: { user: { id: string } }) => unknown) => select({ user: { id: 'admin-1' } }),
}));
vi.mock('@/services/enterprise-org', () => ({ getMyOrg: vi.fn(), listMembers: vi.fn() }));
vi.mock('@/services/marketplace', () => ({
  forcePushUpdate: vi.fn(),
  importMarketplaceAgent: vi.fn(),
  installFromMarketplace: vi.fn(),
  listMarketplaceEntries: vi.fn(),
}));

const entry: MarketplaceEntry = {
  id: 'entry-1',
  org_id: 'org-1',
  publisher_user_id: 'admin-1',
  name: 'Sales bot',
  description: 'Answers pricing questions',
  avatar: null,
  tags: [],
  status: 'published',
  latest_version: 3,
  install_count: 4,
  created_at: 1,
  updated_at: 2,
  is_installed: true,
};

const settle = () =>
  act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });

describe('OrgMarketplace force push', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getMyOrg).mockResolvedValue({ id: 'org-1' } as Awaited<ReturnType<typeof getMyOrg>>);
    vi.mocked(listMembers).mockResolvedValue([{ user_id: 'admin-1', role: 'admin' }] as Awaited<
      ReturnType<typeof listMembers>
    >);
    vi.mocked(listMarketplaceEntries).mockResolvedValue([entry]);
    vi.mocked(forcePushUpdate).mockResolvedValue({
      version: 3,
      synced: 4,
      skipped: 0,
      failed: 0,
      total: 4,
    } as Awaited<ReturnType<typeof forcePushUpdate>>);
  });

  it('overwrites installed copies only after an admin confirms, naming the agent and version', async () => {
    vi.mocked(confirmAction).mockResolvedValue(true);
    render(<OrgMarketplace />);

    fireEvent.click(await screen.findByRole('button', { name: /forcePush$/ }));

    await waitFor(() => expect(forcePushUpdate).toHaveBeenCalledExactlyOnceWith('entry-1'));
    expect(confirmAction).toHaveBeenCalledExactlyOnceWith({
      variant: 'warning',
      description: 'forcePushConfirm:Sales bot|3',
      confirmText: 'forcePush',
    });
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('forcePushSuccess', expect.anything()));
  });

  it('pushes nothing when the admin declines', async () => {
    vi.mocked(confirmAction).mockResolvedValue(false);
    render(<OrgMarketplace />);

    fireEvent.click(await screen.findByRole('button', { name: /forcePush$/ }));
    await waitFor(() => expect(confirmAction).toHaveBeenCalledTimes(1));
    await settle();

    expect(forcePushUpdate).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: /forcePush$/ })).toBeEnabled();
  });
});
