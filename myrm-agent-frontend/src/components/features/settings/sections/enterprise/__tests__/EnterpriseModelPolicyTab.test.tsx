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
    warning: (...args: unknown[]) => mockToast('warning', ...args),
  },
}));

vi.mock('@/lib/cp-base-url', () => ({
  resolveCpBaseUrl: () => 'https://cp.example.com',
}));

vi.mock('@/lib/utils/authHeaders', () => ({
  getAuthHeaders: () => ({ Authorization: 'Bearer test-token' }),
}));

import EnterpriseModelPolicyTab from '../EnterpriseModelPolicyTab';

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

const POLICY_ENTRIES = [
  {
    id: 'p-1',
    pattern: 'openai/*',
    description: 'OpenAI models',
    created_by: 'owner-1',
    created_at: 1,
  },
];

function baseRoutes(patterns: unknown[] = POLICY_ENTRIES): Route[] {
  return [
    {
      method: 'GET',
      url: '/api/enterprise/org/me',
      body: { id: 'org-1', name: 'Acme', owner_user_id: 'owner-1', sso_domain: null, archive_retention_days: 30 },
    },
    {
      method: 'GET',
      url: '/api/enterprise/org/org-1/model-policy',
      body: { patterns },
    },
  ];
}

beforeEach(() => {
  mockToast.mockClear();
  vi.stubGlobal('fetch', vi.fn());
});

describe('EnterpriseModelPolicyTab', () => {
  it('loads org via /me and renders existing patterns', async () => {
    const fetchMock = mockFetchRoutes(baseRoutes());
    vi.stubGlobal('fetch', fetchMock);

    render(<EnterpriseModelPolicyTab />);
    await waitFor(() => {
      expect(screen.getByText(/^modelPolicy\.title/)).toBeInTheDocument();
    });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/enterprise/org/me'),
      expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer test-token' }) }),
    );
    expect(screen.getByText('openai/*')).toBeInTheDocument();
    expect(screen.getByText('OpenAI models')).toBeInTheDocument();
  });

  it('adds a pattern via POST and re-fetches the list', async () => {
    const fetchMock = mockFetchRoutes([
      ...baseRoutes(),
      {
        method: 'POST',
        url: '/api/enterprise/org/org-1/model-policy',
        body: { fanout: { synced: 1, skipped: 0, failed: 0 } },
      },
    ]);
    vi.stubGlobal('fetch', fetchMock);

    render(<EnterpriseModelPolicyTab />);
    await waitFor(() => {
      expect(screen.getByText(/^modelPolicy\.title/)).toBeInTheDocument();
    });

    await userEvent.type(
      screen.getByPlaceholderText('e.g. openai/*, deepseek/*, claude/*'),
      'anthropic/*',
    );
    await userEvent.click(screen.getByText(/^modelPolicy\.add/));

    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith('success', 'modelPolicy.added');
    });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/enterprise/org/org-1/model-policy'),
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('warns when fanout partially failed', async () => {
    const fetchMock = mockFetchRoutes([
      ...baseRoutes(),
      {
        method: 'POST',
        url: '/api/enterprise/org/org-1/model-policy',
        body: { fanout: { synced: 0, skipped: 0, failed: 2 } },
      },
    ]);
    vi.stubGlobal('fetch', fetchMock);

    render(<EnterpriseModelPolicyTab />);
    await waitFor(() => {
      expect(screen.getByText(/^modelPolicy\.title/)).toBeInTheDocument();
    });

    await userEvent.type(
      screen.getByPlaceholderText('e.g. openai/*, deepseek/*, claude/*'),
      'anthropic/*',
    );
    await userEvent.click(screen.getByText(/^modelPolicy\.add/));

    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith('warning', 'modelPolicy.fanoutPartial');
    });
  });

  it('removes a pattern via DELETE', async () => {
    const fetchMock = mockFetchRoutes([
      ...baseRoutes(),
      {
        method: 'DELETE',
        url: '/api/enterprise/org/org-1/model-policy/p-1',
        body: { fanout: { synced: 1, skipped: 0, failed: 0 } },
      },
    ]);
    vi.stubGlobal('fetch', fetchMock);

    render(<EnterpriseModelPolicyTab />);
    await waitFor(() => {
      expect(screen.getByText('openai/*')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByTitle('Remove pattern'));
    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith('success', 'modelPolicy.removed');
    });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/enterprise/org/org-1/model-policy/p-1'),
      expect.objectContaining({ method: 'DELETE' }),
    );
  });

  it('shows noOrg when /me fails', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: false,
      status: 401,
      json: async () => ({ detail: 'Unauthorized' }),
      text: async () => 'Unauthorized',
    })) as ReturnType<typeof vi.fn>;
    vi.stubGlobal('fetch', fetchMock);

    render(<EnterpriseModelPolicyTab />);
    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith('error', 'modelPolicy.loadFailed');
    });
  });
});
