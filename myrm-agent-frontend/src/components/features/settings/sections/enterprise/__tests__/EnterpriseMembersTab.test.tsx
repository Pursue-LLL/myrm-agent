/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mockToast = vi.fn();
const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('sonner', () => ({
  toast: {
    success: (...args: unknown[]) => mockToast('success', ...args),
    error: (...args: unknown[]) => mockToast('error', ...args),
  },
}));

vi.mock('@/lib/api', () => ({
  getApiUrl: (path: string) => path,
}));

const { authUserState } = vi.hoisted(() => ({
  authUserState: { user: { id: 'owner-1' } as { id: string } | null },
}));

vi.mock('@/store/useAuthStore', () => ({
  default: (selector?: (s: { user: { id: string } | null }) => unknown) =>
    selector ? selector(authUserState) : authUserState,
}));

vi.mock('../OrgMcpAdminPanel', () => ({
  default: () => <div data-testid="org-mcp-panel" />,
}));

vi.mock('../TunnelAdminPanel', () => ({
  default: () => <div data-testid="tunnel-panel" />,
}));

import EnterpriseMembersTab from '../EnterpriseMembersTab';

interface Route {
  method: string;
  url: string;
  status?: number;
  body?: unknown;
}

function mockFetchRoutes(routes: Route[]) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? 'GET';
    const route = routes.find((r) => r.method === method && url.endsWith(r.url));
    if (!route) {
      throw new Error(`Unexpected fetch: ${method} ${url}`);
    }
    return {
      ok: route.status ? route.status < 400 : true,
      status: route.status ?? 200,
      json: async () => route.body ?? {},
      text: async () => (route.body ? JSON.stringify(route.body) : ''),
    } as Response;
  });
}

interface MemberInput {
  user_id: string;
  role: string;
  oauth_bound?: boolean | null;
  email?: string | null;
}

function membersRoutes(members: MemberInput[], withUnlinkRoute = false): Route[] {
  const routes: Route[] = [
    {
      method: 'GET',
      url: '/api/enterprise/org/me',
      body: { id: 'org-1', name: 'Acme', owner_user_id: 'owner-1', sso_domain: null, archive_retention_days: 30 },
    },
    {
      method: 'GET',
      url: '/api/enterprise/org/org-1/members',
      body: members.map((m) => ({
        user_id: m.user_id,
        role: m.role,
        idp_groups: null,
        joined_at: 1,
        oauth_bound: m.oauth_bound ?? null,
        email: m.email ?? null,
        display_name: null,
      })),
    },
    {
      method: 'GET',
      url: '/api/enterprise/org/org-1/handoff-logs',
      body: [],
    },
  ];
  if (withUnlinkRoute) {
    routes.push({
      method: 'POST',
      url: '/api/enterprise/org/org-1/members/member-2/unlink-oauth',
      body: {},
    });
  }
  routes.push({
    method: 'POST',
    url: '/api/enterprise/org/org-1/offboarding/member-2',
    body: { id: 'log-1' },
  });
  routes.push({
    method: 'POST',
    url: '/api/enterprise/org/org-1/transfer/member-2',
    body: { id: 'log-2' },
  });
  return routes;
}

const ADMIN_MEMBERS: MemberInput[] = [
  { user_id: 'owner-1', role: 'owner', oauth_bound: true, email: 'owner-1@acme.com' },
  { user_id: 'member-2', role: 'member', oauth_bound: true, email: 'member-2@acme.com' },
];

beforeEach(() => {
  mockToast.mockClear();
  authUserState.user = { id: 'owner-1' };
  vi.stubGlobal('fetch', vi.fn());
});

describe('EnterpriseMembersTab', () => {
  it('renders the unlink button for a bound non-owner member', async () => {
    vi.stubGlobal('fetch', mockFetchRoutes(membersRoutes(ADMIN_MEMBERS)));
    render(<EnterpriseMembersTab />);

    await waitFor(() => {
      expect(screen.getByText(/^members/)).toBeInTheDocument();
    });
    expect(screen.getAllByTitle('unlinkOauth')).toHaveLength(1);
    // Members are identifiable by email and the SSO binding is visible.
    expect(screen.getByText('member-2@acme.com')).toBeInTheDocument();
    expect(screen.getAllByText('ssoBound')).toHaveLength(2);
  });

  it('hides the unlink button for unbound or self members', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetchRoutes(
        membersRoutes([
          { user_id: 'owner-1', role: 'owner', oauth_bound: true },
          { user_id: 'member-2', role: 'member', oauth_bound: false },
        ]),
      ),
    );
    render(<EnterpriseMembersTab />);

    await waitFor(() => {
      expect(screen.getByText(/^members/)).toBeInTheDocument();
    });
    expect(screen.queryAllByTitle('unlinkOauth')).toHaveLength(0);
  });

  it('unlinks OAuth after confirmation and toasts success', async () => {
    const fetchMock = mockFetchRoutes(membersRoutes(ADMIN_MEMBERS, true));
    vi.stubGlobal('fetch', fetchMock);

    render(<EnterpriseMembersTab />);
    await waitFor(() => {
      expect(screen.getAllByTitle('unlinkOauth')).toHaveLength(1);
    });

    await userEvent.click(screen.getAllByTitle('unlinkOauth')[0]);
    expect(screen.getByText('unlinkOauthDesc')).toBeInTheDocument();

    await userEvent.click(screen.getByText('unlinkOauthConfirm'));
    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith('success', 'unlinkSuccess');
    });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/enterprise/org/org-1/members/member-2/unlink-oauth'),
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('offboards a member picked from the member dropdown', async () => {
    const fetchMock = mockFetchRoutes(membersRoutes(ADMIN_MEMBERS));
    vi.stubGlobal('fetch', fetchMock);

    render(<EnterpriseMembersTab />);
    await waitFor(() => {
      expect(screen.getAllByTitle('unlinkOauth')).toHaveLength(1);
    });

    await userEvent.click(screen.getByText('offboardUser'));
    const confirmBtn = screen.getByText('confirmOffboard') as HTMLButtonElement;
    expect(confirmBtn.disabled).toBe(true);

    await userEvent.click(screen.getByRole('combobox'));
    await userEvent.click(await screen.findByRole('option', { name: 'member-2@acme.com' }));
    expect(confirmBtn.disabled).toBe(false);
    await userEvent.click(confirmBtn);

    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith('success', 'offboardSuccess');
    });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/enterprise/org/org-1/offboarding/member-2'),
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('transfers a volume between members picked from dropdowns', async () => {
    const fetchMock = mockFetchRoutes(membersRoutes(ADMIN_MEMBERS));
    vi.stubGlobal('fetch', fetchMock);

    render(<EnterpriseMembersTab />);
    await waitFor(() => {
      expect(screen.getAllByTitle('unlinkOauth')).toHaveLength(1);
    });

    await userEvent.click(screen.getByText('transferVolume'));
    let dropdowns = screen.getAllByRole('combobox');
    expect(dropdowns).toHaveLength(2);
    const confirmBtn = screen.getByText('confirmTransfer') as HTMLButtonElement;
    expect(confirmBtn.disabled).toBe(true);

    // source 只含可 offboard 成员（非 owner）；target 含全部成员（可转给 owner）
    await userEvent.click(dropdowns[0]);
    await userEvent.click(await screen.findByRole('option', { name: 'member-2@acme.com' }));
    expect(confirmBtn.disabled).toBe(true); // 目标未选仍禁用

    dropdowns = screen.getAllByRole('combobox');
    await userEvent.click(dropdowns[1]);
    await userEvent.click(await screen.findByRole('option', { name: 'member-2@acme.com' }));
    expect(confirmBtn.disabled).toBe(true); // 自转（source==target）禁用

    dropdowns = screen.getAllByRole('combobox');
    await userEvent.click(dropdowns[1]);
    await userEvent.click(await screen.findByRole('option', { name: 'owner-1@acme.com' }));
    expect(confirmBtn.disabled).toBe(false);
    await userEvent.click(confirmBtn);

    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith('success', 'transferSuccess');
    });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/enterprise/org/org-1/transfer/member-2'),
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('"target_user_id":"owner-1"'),
      }),
    );
  });

  it('removes a member only after confirmation', async () => {
    const fetchMock = mockFetchRoutes(membersRoutes(ADMIN_MEMBERS));
    vi.stubGlobal('fetch', fetchMock);

    render(<EnterpriseMembersTab />);
    await waitFor(() => {
      expect(screen.getAllByTitle('removeMember')).toHaveLength(1);
    });

    await userEvent.click(screen.getAllByTitle('removeMember')[0]);
    expect(screen.getByText('removeMemberDesc')).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalledWith(
      expect.stringContaining('/api/enterprise/org/org-1/members/member-2'),
      expect.objectContaining({ method: 'DELETE' }),
    );

    await userEvent.click(screen.getByText('confirmRemove'));
    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith('success', 'memberRemoved');
    });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/enterprise/org/org-1/members/member-2'),
      expect.objectContaining({ method: 'DELETE' }),
    );
  });

  it('hides management actions for non-admin members', async () => {
    vi.stubGlobal('fetch', mockFetchRoutes(membersRoutes(ADMIN_MEMBERS)));
    authUserState.user = { id: 'member-2' };
    render(<EnterpriseMembersTab />);

    await waitFor(() => {
      expect(screen.getByText(/^members/)).toBeInTheDocument();
    });
    expect(screen.queryByText('addMember')).not.toBeInTheDocument();
    expect(screen.queryByText('offboardUser')).not.toBeInTheDocument();
    expect(screen.queryByText('transferVolume')).not.toBeInTheDocument();
    expect(screen.queryAllByTitle('removeMember')).toHaveLength(0);
    expect(screen.queryAllByTitle('unlinkOauth')).toHaveLength(0);
  });
});
