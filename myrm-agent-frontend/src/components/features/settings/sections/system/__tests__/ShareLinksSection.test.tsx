/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const mockToast = vi.fn();
const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
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

import ShareLinksSection from '../ShareLinksSection';

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

const shareRecord = {
  id: 'rec-1',
  artifact_id: 'art-1',
  artifact_name: 'report.html',
  artifact_type: 'html',
  password_protected: false,
  created_at: 1786500000,
  expires_at: 1787200000,
};

describe('ShareLinksSection', () => {
  beforeEach(() => {
    mockToast.mockClear();
    vi.restoreAllMocks();
  });

  it('renders empty state when there are no active share links', async () => {
    const fetchMock = mockFetchRoutes([{ method: 'GET', url: '/api/v1/files/artifacts/shares', body: [] }]);
    vi.stubGlobal('fetch', fetchMock);

    render(<ShareLinksSection />);

    await waitFor(() => expect(screen.getByTestId('shares-empty')).toBeInTheDocument());
  });

  it('renders share records in a table', async () => {
    const fetchMock = mockFetchRoutes([
      { method: 'GET', url: '/api/v1/files/artifacts/shares', body: [shareRecord] },
    ]);
    vi.stubGlobal('fetch', fetchMock);

    render(<ShareLinksSection />);

    await waitFor(() => expect(screen.getByTestId('shares-table')).toBeInTheDocument());
    expect(screen.getByText('report.html')).toBeInTheDocument();
    expect(screen.getByText('html')).toBeInTheDocument();
  });

  it('revokes a share link and removes it from the list', async () => {
    const fetchMock = mockFetchRoutes([
      { method: 'GET', url: '/api/v1/files/artifacts/shares', body: [shareRecord] },
      { method: 'DELETE', url: '/api/v1/files/artifacts/shares/rec-1', status: 204 },
    ]);
    vi.stubGlobal('fetch', fetchMock);

    render(<ShareLinksSection />);
    await waitFor(() => expect(screen.getByTestId('shares-table')).toBeInTheDocument());

    await userEvent.click(screen.getByRole('button', { name: /revoke/i }));

    await waitFor(() => expect(screen.getByTestId('shares-empty')).toBeInTheDocument());
    expect(mockToast).toHaveBeenCalledWith('success', 'revokeSuccess');
  });

  it('shows an error state when loading fails', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: false,
      status: 500,
      json: async () => ({ detail: 'boom' }),
    }));
    vi.stubGlobal('fetch', fetchMock);

    render(<ShareLinksSection />);

    await waitFor(() => expect(screen.getByText('loadError')).toBeInTheDocument());
  });
});
