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
  BACKEND_BASE_URL: { toString: () => '' },
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
  share_path: '/api/v1/public/artifact-share/abc.def',
  share_url: null,
};

const protectedRecord = {
  ...shareRecord,
  id: 'rec-2',
  artifact_name: 'secret.pdf',
  artifact_type: 'pdf',
  password_protected: true,
  share_path: '/api/v1/public/artifact-share/secret.def',
};

const legacyProtectedRecord = {
  ...protectedRecord,
  id: 'rec-4',
  artifact_name: 'legacy.pdf',
  // Pre-R2 rows for password shares have no persisted path (token cannot be
  // rebuilt) and fall back to the protected hint.
  share_path: null,
};

const absoluteShareRecord = {
  ...shareRecord,
  id: 'rec-3',
  artifact_name: 'hosted.html',
  share_url: 'https://myrm-x.example.com/api/v1/public/artifact-share/xyz.uvw',
};

describe('ShareLinksSection', () => {
  beforeEach(() => {
    mockToast.mockClear();
    vi.restoreAllMocks();
    vi.stubGlobal('navigator', {
      ...navigator,
      clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
  });

  it('renders empty state when there are no active share links', async () => {
    const fetchMock = mockFetchRoutes([{ method: 'GET', url: '/files/artifacts/shares', body: [] }]);
    vi.stubGlobal('fetch', fetchMock);

    render(<ShareLinksSection />);

    await waitFor(() => expect(screen.getByTestId('shares-empty')).toBeInTheDocument());
  });

  it('renders share records in a table', async () => {
    const fetchMock = mockFetchRoutes([
      { method: 'GET', url: '/files/artifacts/shares', body: [shareRecord] },
    ]);
    vi.stubGlobal('fetch', fetchMock);

    render(<ShareLinksSection />);

    await waitFor(() => expect(screen.getByTestId('shares-table')).toBeInTheDocument());
    expect(screen.getByText('report.html')).toBeInTheDocument();
    expect(screen.getByText('type.html')).toBeInTheDocument();
    expect(screen.getByText('copy')).toBeInTheDocument();
  });

  it('copies the share link for unprotected records', async () => {
    const clipboardSpy = vi
      .spyOn(navigator.clipboard, 'writeText')
      .mockImplementation(async () => undefined);
    vi.stubGlobal('location', { origin: 'http://localhost:3000' });
    const fetchMock = mockFetchRoutes([
      { method: 'GET', url: '/files/artifacts/shares', body: [shareRecord] },
    ]);
    vi.stubGlobal('fetch', fetchMock);

    render(<ShareLinksSection />);
    await waitFor(() => expect(screen.getByTestId('shares-table')).toBeInTheDocument());

    await userEvent.click(screen.getByRole('button', { name: /copyLabel/ }));

    await waitFor(() =>
      expect(clipboardSpy).toHaveBeenCalledWith(
        'http://localhost:3000/api/v1/public/artifact-share/abc.def',
      ),
    );
    expect(screen.getByText('copied')).toBeInTheDocument();
  });

  it('opens the share link in a new tab for unprotected records', async () => {
    const openSpy = vi.fn();
    vi.stubGlobal('location', { origin: 'http://localhost:3000' });
    vi.stubGlobal('open', openSpy);
    const fetchMock = mockFetchRoutes([
      { method: 'GET', url: '/files/artifacts/shares', body: [shareRecord] },
    ]);
    vi.stubGlobal('fetch', fetchMock);

    render(<ShareLinksSection />);
    await waitFor(() => expect(screen.getByTestId('shares-table')).toBeInTheDocument());

    await userEvent.click(screen.getByRole('button', { name: /openLabel/ }));

    expect(openSpy).toHaveBeenCalledWith(
      'http://localhost:3000/api/v1/public/artifact-share/abc.def',
      '_blank',
      'noopener,noreferrer',
    );
  });

  it('prefers the server-provided absolute share_url when copying', async () => {
    const clipboardSpy = vi
      .spyOn(navigator.clipboard, 'writeText')
      .mockImplementation(async () => undefined);
    vi.stubGlobal('location', { origin: 'http://localhost:3000' });
    const fetchMock = mockFetchRoutes([
      { method: 'GET', url: '/files/artifacts/shares', body: [absoluteShareRecord] },
    ]);
    vi.stubGlobal('fetch', fetchMock);

    render(<ShareLinksSection />);
    await waitFor(() => expect(screen.getByTestId('shares-table')).toBeInTheDocument());

    await userEvent.click(screen.getByRole('button', { name: /copyLabel/ }));

    await waitFor(() =>
      expect(clipboardSpy).toHaveBeenCalledWith(
        'https://myrm-x.example.com/api/v1/public/artifact-share/xyz.uvw',
      ),
    );
  });

  it('prefers the server-provided absolute share_url when opening', async () => {
    const openSpy = vi.fn();
    vi.stubGlobal('location', { origin: 'http://localhost:3000' });
    vi.stubGlobal('open', openSpy);
    const fetchMock = mockFetchRoutes([
      { method: 'GET', url: '/files/artifacts/shares', body: [absoluteShareRecord] },
    ]);
    vi.stubGlobal('fetch', fetchMock);

    render(<ShareLinksSection />);
    await waitFor(() => expect(screen.getByTestId('shares-table')).toBeInTheDocument());

    await userEvent.click(screen.getByRole('button', { name: /openLabel/ }));

    expect(openSpy).toHaveBeenCalledWith(
      'https://myrm-x.example.com/api/v1/public/artifact-share/xyz.uvw',
      '_blank',
      'noopener,noreferrer',
    );
  });

  it('renders copy/open buttons for password-protected records with a persisted path', async () => {
    const fetchMock = mockFetchRoutes([
      {
        method: 'GET',
        url: '/files/artifacts/shares',
        body: [shareRecord, protectedRecord],
      },
    ]);
    vi.stubGlobal('location', { origin: 'http://localhost:3000' });
    vi.stubGlobal('fetch', fetchMock);

    render(<ShareLinksSection />);

    await waitFor(() => expect(screen.getByTestId('shares-table')).toBeInTheDocument());
    expect(screen.queryByText('linkProtected')).not.toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /copyLabel/ })).toHaveLength(2);
    expect(screen.getAllByRole('button', { name: /openLabel/ })).toHaveLength(2);
  });

  it('shows a protected hint instead of copy buttons for password records without a path', async () => {
    // Legacy rows created before R2 have no persisted share_path for password
    // shares; the GUI degrades to a hint instead of a dead link.
    const fetchMock = mockFetchRoutes([
      {
        method: 'GET',
        url: '/files/artifacts/shares',
        body: [legacyProtectedRecord],
      },
    ]);
    vi.stubGlobal('fetch', fetchMock);

    render(<ShareLinksSection />);

    await waitFor(() => expect(screen.getByTestId('shares-table')).toBeInTheDocument());
    expect(screen.getByText('linkProtected')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /copyLabel/ })).not.toBeInTheDocument();
  });

  it('opens the impact preview dialog and revokes a share link on confirm', async () => {
    const fetchMock = mockFetchRoutes([
      { method: 'GET', url: '/files/artifacts/shares', body: [shareRecord] },
      { method: 'DELETE', url: '/files/artifacts/shares/rec-1', status: 204 },
    ]);
    vi.stubGlobal('fetch', fetchMock);

    render(<ShareLinksSection />);
    await waitFor(() => expect(screen.getByTestId('shares-table')).toBeInTheDocument());

    await userEvent.click(screen.getByRole('button', { name: /revokeLabel/ }));

    // Impact preview dialog shows the link details before any destructive call.
    expect(screen.getByText('confirm.title')).toBeInTheDocument();
    expect(screen.getAllByText('report.html').length).toBeGreaterThanOrEqual(2);
    expect(fetchMock).not.toHaveBeenCalledWith(
      expect.stringContaining('/shares/rec-1'),
      expect.objectContaining({ method: 'DELETE' }),
    );

    await userEvent.click(screen.getByRole('button', { name: /confirm.revoke/ }));

    await waitFor(() => expect(screen.getByTestId('shares-empty')).toBeInTheDocument());
    expect(mockToast).toHaveBeenCalledWith('success', 'revokeSuccess');
  });

  it('does not revoke when the dialog is dismissed', async () => {
    const fetchMock = mockFetchRoutes([
      { method: 'GET', url: '/files/artifacts/shares', body: [shareRecord] },
    ]);
    vi.stubGlobal('fetch', fetchMock);

    render(<ShareLinksSection />);
    await waitFor(() => expect(screen.getByTestId('shares-table')).toBeInTheDocument());

    await userEvent.click(screen.getByRole('button', { name: /revokeLabel/ }));
    await userEvent.click(screen.getByRole('button', { name: /confirm.cancel/ }));

    expect(fetchMock).not.toHaveBeenCalledWith(
      expect.stringContaining('/shares/rec-1'),
      expect.objectContaining({ method: 'DELETE' }),
    );
    expect(screen.getByTestId('shares-table')).toBeInTheDocument();
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
