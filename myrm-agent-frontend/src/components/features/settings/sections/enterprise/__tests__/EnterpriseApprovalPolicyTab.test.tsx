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

import EnterpriseApprovalPolicyTab from '../EnterpriseApprovalPolicyTab';

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

const POLICY_STATE = {
  ignoreAllowlistForModels: ['claude-opus*'],
  forceAutoReviewForModels: [],
  disableYolo: false,
  disableAllowAlways: false,
};

function baseRoutes(state: unknown = POLICY_STATE): Route[] {
  return [
    {
      method: 'GET',
      url: '/api/enterprise/org/me',
      body: { id: 'org-1', name: 'Acme', owner_user_id: 'owner-1', sso_domain: null, archive_retention_days: 30 },
    },
    {
      method: 'GET',
      url: '/api/enterprise/org/org-1/approval-policy',
      body: state,
    },
  ];
}

beforeEach(() => {
  mockToast.mockClear();
  vi.stubGlobal('fetch', vi.fn());
});

describe('EnterpriseApprovalPolicyTab', () => {
  it('loads org via /me and renders the saved policy state', async () => {
    const fetchMock = mockFetchRoutes(baseRoutes());
    vi.stubGlobal('fetch', fetchMock);

    render(<EnterpriseApprovalPolicyTab />);
    await waitFor(() => {
      expect(screen.getByText(/^approvalPolicy\.title/)).toBeInTheDocument();
    });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/enterprise/org/me'),
      expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer test-token' }) }),
    );
    expect(screen.getByText(/claude-opus\*/)).toBeInTheDocument();
  });

  it('saves the policy via PUT and toasts success', async () => {
    const fetchMock = mockFetchRoutes([
      ...baseRoutes(),
      {
        method: 'PUT',
        url: '/api/enterprise/org/org-1/approval-policy',
        body: { ...POLICY_STATE, fanout: { synced: 1, skipped: 0, failed: 0 } },
      },
    ]);
    vi.stubGlobal('fetch', fetchMock);

    render(<EnterpriseApprovalPolicyTab />);
    await waitFor(() => {
      expect(screen.getByText(/^approvalPolicy\.title/)).toBeInTheDocument();
    });

    await userEvent.click(screen.getByText(/^approvalPolicy\.save/));

    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith('success', 'approvalPolicy.saved');
    });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/enterprise/org/org-1/approval-policy'),
      expect.objectContaining({ method: 'PUT' }),
    );
  });

  it('warns when fanout partially failed', async () => {
    const fetchMock = mockFetchRoutes([
      ...baseRoutes(),
      {
        method: 'PUT',
        url: '/api/enterprise/org/org-1/approval-policy',
        body: { ...POLICY_STATE, fanout: { synced: 0, skipped: 0, failed: 1 } },
      },
    ]);
    vi.stubGlobal('fetch', fetchMock);

    render(<EnterpriseApprovalPolicyTab />);
    await waitFor(() => {
      expect(screen.getByText(/^approvalPolicy\.title/)).toBeInTheDocument();
    });

    await userEvent.click(screen.getByText(/^approvalPolicy\.save/));

    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith('warning', 'approvalPolicy.fanoutPartial');
    });
  });

  it('adds a pattern to the ignore allowlist before saving', async () => {
    const fetchMock = mockFetchRoutes([
      ...baseRoutes(),
      {
        method: 'PUT',
        url: '/api/enterprise/org/org-1/approval-policy',
        body: { ...POLICY_STATE, fanout: { synced: 1, skipped: 0, failed: 0 } },
      },
    ]);
    vi.stubGlobal('fetch', fetchMock);

    render(<EnterpriseApprovalPolicyTab />);
    await waitFor(() => {
      expect(screen.getByText(/^approvalPolicy\.title/)).toBeInTheDocument();
    });

    await userEvent.type(screen.getAllByPlaceholderText('e.g. claude-opus*')[0], 'deepseek-r1*');
    await userEvent.click(screen.getAllByText(/^approvalPolicy\.addPattern/)[0]);

    expect(screen.getByText(/deepseek-r1\*/)).toBeInTheDocument();
  });

  it('shows loadFailed toast when /me fails', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: false,
      status: 401,
      json: async () => ({ detail: 'Unauthorized' }),
      text: async () => 'Unauthorized',
    })) as ReturnType<typeof vi.fn>;
    vi.stubGlobal('fetch', fetchMock);

    render(<EnterpriseApprovalPolicyTab />);
    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith('error', 'approvalPolicy.loadFailed');
    });
  });
});
