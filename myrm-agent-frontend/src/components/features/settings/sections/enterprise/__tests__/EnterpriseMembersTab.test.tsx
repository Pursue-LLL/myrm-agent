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

vi.mock('@/store/useAuthStore', () => {
  const mockState = { user: { id: 'owner-1' } };
  return {
    default: (selector?: (s: { user: { id: string } | null }) => unknown) =>
      selector ? selector(mockState) : mockState,
  };
});

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
  return routes;
}

const ADMIN_MEMBERS: MemberInput[] = [
  { user_id: 'owner-1', role: 'owner', oauth_bound: true },
  { user_id: 'member-2', role: 'member', oauth_bound: true },
];

beforeEach(() => {
  mockToast.mockClear();
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
});
