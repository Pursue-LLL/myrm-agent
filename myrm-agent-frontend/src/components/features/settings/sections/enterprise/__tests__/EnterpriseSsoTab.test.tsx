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

vi.mock('@/lib/cp-base-url', () => ({
  resolveCpBaseUrl: () => 'https://cp.example.com',
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

import EnterpriseSsoTab from '../EnterpriseSsoTab';

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

function orgRoutes(
  withConfig = true,
  memberRole = 'owner',
  ssoDomain: string | null = null,
  allowedGroups: string[] = ['engineering', 'finance'],
): Route[] {
  return [
    {
      method: 'GET',
      url: '/api/enterprise/org/me',
      body: { id: 'org-1', name: 'Acme', owner_user_id: 'owner-1', sso_domain: ssoDomain, archive_retention_days: 30 },
    },
    {
      method: 'GET',
      url: '/api/enterprise/org/org-1/sso',
      status: withConfig ? 200 : 404,
      body: withConfig
        ? {
            org_id: 'org-1',
            issuer_url: 'https://login.acme.com',
            client_id: 'myrm-client',
            client_secret_masked: 'abc12345',
            auto_provision: true,
            allowed_groups: allowedGroups,
            enabled: true,
            updated_at: 1,
          }
        : {},
    },
    {
      method: 'GET',
      url: '/api/enterprise/org/org-1/members',
      body: [{ user_id: 'owner-1', role: memberRole, idp_groups: null, joined_at: 1 }],
    },
  ];
}

beforeEach(() => {
  mockToast.mockClear();
  vi.stubGlobal('fetch', vi.fn());
});

describe('EnterpriseSsoTab', () => {
  it('renders the SSO form with preloaded config values', async () => {
    vi.stubGlobal('fetch', mockFetchRoutes(orgRoutes(true)));
    render(<EnterpriseSsoTab />);

    await waitFor(() => {
      expect(screen.getByLabelText('issuerLabel')).toBeInTheDocument();
    });
    expect(screen.getByLabelText('issuerLabel')).toHaveValue('https://login.acme.com');
    expect(screen.getByLabelText('clientIdLabel')).toHaveValue('myrm-client');
    expect(screen.getByLabelText('groupsLabel')).toHaveValue('engineering, finance');
    expect(screen.getByText('groupsHint')).toBeInTheDocument();
  });

  it('shows domain-restricted hints only when no group whitelist is set', async () => {
    vi.stubGlobal('fetch', mockFetchRoutes(orgRoutes(true, 'owner', 'acme.com', [])));
    render(<EnterpriseSsoTab />);

    await waitFor(() => {
      expect(screen.getByText('groupsHintDomain')).toBeInTheDocument();
    });
    expect(screen.getByText('autoProvisionHintDomain')).toBeInTheDocument();
  });

  it('keeps group-whitelist hints when groups are set even with an sso_domain', async () => {
    vi.stubGlobal('fetch', mockFetchRoutes(orgRoutes(true, 'owner', 'acme.com', ['engineering'])));
    render(<EnterpriseSsoTab />);

    await waitFor(() => {
      expect(screen.getByText('groupsHint')).toBeInTheDocument();
    });
    expect(screen.queryByText('groupsHintDomain')).not.toBeInTheDocument();
  });

  it('shows the sign-in link when SSO is configured and enabled', async () => {
    vi.stubGlobal('fetch', mockFetchRoutes(orgRoutes(true)));
    render(<EnterpriseSsoTab />);

    await waitFor(() => {
      expect(screen.getByText('loginLink')).toBeInTheDocument();
    });
    const link = screen.getByText('https://cp.example.com/api/auth/oauth/oidc/authorize?org=org-1');
    expect(link).toBeInTheDocument();
  });

  it('shows notConfigured hint when no SSO config exists', async () => {
    vi.stubGlobal('fetch', mockFetchRoutes(orgRoutes(false)));
    render(<EnterpriseSsoTab />);

    await waitFor(() => {
      expect(screen.getByText('notConfigured')).toBeInTheDocument();
    });
  });

  it('hides the form for non-admin members', async () => {
    vi.stubGlobal('fetch', mockFetchRoutes(orgRoutes(true, 'member')));
    render(<EnterpriseSsoTab />);

    await waitFor(() => {
      expect(screen.getByText('adminOnly')).toBeInTheDocument();
    });
    expect(screen.queryByLabelText('issuerLabel')).not.toBeInTheDocument();
  });

  it('saves the config via PUT and toasts success', async () => {
    const fetchMock = mockFetchRoutes([
      ...orgRoutes(true),
      {
        method: 'PUT',
        url: '/api/enterprise/org/org-1/sso',
        body: {
          org_id: 'org-1',
          issuer_url: 'https://login.acme.com',
          client_id: 'myrm-client',
          client_secret_masked: 'abc12345',
          auto_provision: true,
          allowed_groups: ['engineering', 'finance'],
          enabled: true,
          updated_at: 2,
        },
      },
    ]);
    vi.stubGlobal('fetch', fetchMock);

    render(<EnterpriseSsoTab />);
    await waitFor(() => {
      expect(screen.getByLabelText('issuerLabel')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByText('save'));
    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith('success', 'saved');
    });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/enterprise/org/org-1/sso'),
      expect.objectContaining({ method: 'PUT' }),
    );
  });

  it('saves the SSO email domain via PUT and toasts success', async () => {
    const fetchMock = mockFetchRoutes([
      ...orgRoutes(true, 'owner', 'acme.com', []),
      {
        method: 'PUT',
        url: '/api/enterprise/org/org-1',
        body: {
          id: 'org-1',
          name: 'Acme',
          owner_user_id: 'owner-1',
          sso_domain: 'corp.example.com',
          archive_retention_days: 30,
        },
      },
    ]);
    vi.stubGlobal('fetch', fetchMock);

    render(<EnterpriseSsoTab />);
    await waitFor(() => {
      expect(screen.getByLabelText('ssoDomainLabel')).toBeInTheDocument();
    });
    expect(screen.getByLabelText('ssoDomainLabel')).toHaveValue('acme.com');

    await userEvent.clear(screen.getByLabelText('ssoDomainLabel'));
    await userEvent.type(screen.getByLabelText('ssoDomainLabel'), 'corp.example.com');
    await userEvent.click(screen.getByText('saveDomain'));

    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith('success', 'ssoDomainSaved');
    });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/enterprise/org/org-1'),
      expect.objectContaining({ method: 'PUT' }),
    );
    expect(screen.getByLabelText('ssoDomainLabel')).toHaveValue('corp.example.com');
  });

  it('removes the config via DELETE and toasts success', async () => {
    const fetchMock = mockFetchRoutes([
      ...orgRoutes(true),
      { method: 'DELETE', url: '/api/enterprise/org/org-1/sso', body: {} },
    ]);
    vi.stubGlobal('fetch', fetchMock);

    render(<EnterpriseSsoTab />);
    await waitFor(() => {
      expect(screen.getByText('remove')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByText('remove'));
    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith('success', 'deleted');
    });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/enterprise/org/org-1/sso'),
      expect.objectContaining({ method: 'DELETE' }),
    );
  });
});
