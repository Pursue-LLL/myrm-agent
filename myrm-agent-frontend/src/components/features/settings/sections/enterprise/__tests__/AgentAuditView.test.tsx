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

vi.mock('@/lib/utils/authHeaders', () => ({
  getAuthHeaders: () => ({ Authorization: 'Bearer test-token' }),
}));

import AgentAuditView from '../AgentAuditView';

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

function auditRoutes(failedSandboxes: string[] = []): Route[] {
  return [
    {
      method: 'GET',
      url: '/api/enterprise/org/me',
      body: { id: 'org-1', name: 'Acme', owner_user_id: 'owner-1', sso_domain: null, archive_retention_days: 30 },
    },
    {
      method: 'GET',
      url: '/api/enterprise/org/org-1/agent-audit/events',
      body: {
        total: 3,
        scanned_sandboxes: 2,
        failed_sandboxes: failedSandboxes,
        events: [
          {
            seq: 1,
            ts: 1755000000,
            type: 'tool_call_start',
            sid: 'session-abc',
            data: { tool_name: 'web_search', tool_call_id: 'call-1', message_id: 'msg-1' },
          },
          {
            seq: 2,
            ts: 1755000001,
            type: 'tool_call_finish',
            sid: 'session-abc',
            data: { tool_name: 'web_search', tool_call_id: 'call-1', duration_ms: 120 },
          },
          {
            seq: 3,
            ts: 1755000002,
            type: 'security_audit',
            sid: 'session-abc',
            data: {
              count: 1,
              decisions: [
                {
                  tool_call_id: 'call-1',
                  decision: 'ALLOW',
                  reason: 'benign fetch',
                  tainted: false,
                  ts: 1755000003,
                },
              ],
            },
          },
        ],
      },
    },
  ];
}

beforeEach(() => {
  mockToast.mockClear();
  vi.stubGlobal('fetch', vi.fn());
});

describe('AgentAuditView', () => {
  it('loads org and renders agent audit KPIs and event stream', async () => {
    const fetchMock = mockFetchRoutes(auditRoutes());
    vi.stubGlobal('fetch', fetchMock);

    render(<AgentAuditView />);
    await waitFor(() => {
      expect(screen.getByText(/^agentTitle/)).toBeInTheDocument();
    });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/enterprise/org/me'),
      expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer test-token' }) }),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/enterprise/org/org-1/agent-audit/events'),
      expect.anything(),
    );

    expect(screen.getAllByText('3').length).toBeGreaterThan(0);
    expect(screen.getAllByText('web_search').length).toBeGreaterThan(0);
    expect(screen.getAllByText(/^toneTool/).length).toBeGreaterThan(0);
  });

  it('shows a warning banner when sandboxes failed to scan', async () => {
    vi.stubGlobal('fetch', mockFetchRoutes(auditRoutes(['sandbox-9'])));
    render(<AgentAuditView />);

    await waitFor(() => {
      expect(screen.getByText(/^agentFailedSandboxes/)).toBeInTheDocument();
    });
    expect(screen.getByText('sandbox-9')).toBeInTheDocument();
  });

  it('expands an event to reveal security decisions', async () => {
    vi.stubGlobal('fetch', mockFetchRoutes(auditRoutes()));
    render(<AgentAuditView />);

    await waitFor(() => {
      expect(screen.getAllByText('web_search').length).toBeGreaterThan(0);
    });

    const securityRow = screen.getByText('security audit').closest('button');
    expect(securityRow).not.toBeNull();
    await userEvent.click(securityRow as HTMLButtonElement);

    expect(screen.getByText(/^agentSecurityDecisions/)).toBeInTheDocument();
    expect(screen.getByText('ALLOW')).toBeInTheDocument();
    expect(screen.getByText('benign fetch')).toBeInTheDocument();
  });

  it('renders empty state when there are no events', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetchRoutes([
        {
          method: 'GET',
          url: '/api/enterprise/org/me',
          body: { id: 'org-1', name: 'Acme', owner_user_id: 'owner-1', sso_domain: null, archive_retention_days: 30 },
        },
        {
          method: 'GET',
          url: '/api/enterprise/org/org-1/agent-audit/events',
          body: { total: 0, scanned_sandboxes: 1, failed_sandboxes: [], events: [] },
        },
      ]),
    );
    render(<AgentAuditView />);

    await waitFor(() => {
      expect(screen.getByText(/^agentNoEvents/)).toBeInTheDocument();
    });
  });
});
