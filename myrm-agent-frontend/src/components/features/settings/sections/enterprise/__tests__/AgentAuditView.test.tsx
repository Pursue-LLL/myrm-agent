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
    const path = url.split('?')[0];
    const route = routes.find((r) => r.method === method && path.endsWith(r.url));
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

const ORG_BODY = { id: 'org-1', name: 'Acme', owner_user_id: 'owner-1', sso_domain: null, archive_retention_days: 30 };

function okResponse(body: unknown) {
  return {
    ok: true,
    status: 200,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as Response;
}

function auditRoutes(failedSandboxes: string[] = []): Route[] {
  return [
    {
      method: 'GET',
      url: '/api/enterprise/org/me',
      body: ORG_BODY,
    },
    {
      method: 'GET',
      url: '/api/enterprise/org/org-1/agent-audit/events',
      body: {
        total: 5,
        tool_call_total: 2,
        security_event_total: 1,
        security_deny_total: 1,
        scanned_sandboxes: 2,
        failed_sandboxes: failedSandboxes,
        events: [
          {
            seq: 1,
            ts: 1755000000,
            type: 'tool_start',
            sid: 'session-abc',
            sandbox_id: 'sandbox-1',
            user_id: 'user-12345678901234567890',
            user_display: 'alice@acme.com',
            data: { tool_name: 'web_search', tool_call_id: 'call-1', message_id: 'msg-1' },
          },
          {
            seq: 2,
            ts: 1755000001,
            type: 'tool_end',
            sid: 'session-abc',
            sandbox_id: 'sandbox-1',
            user_id: 'user-12345678901234567890',
            user_display: 'alice@acme.com',
            data: { tool_name: 'web_search', tool_call_id: 'call-1', duration_ms: 120 },
          },
          {
            seq: 3,
            ts: 1755000002,
            type: 'security_audit',
            sid: 'session-abc',
            sandbox_id: 'sandbox-1',
            user_id: 'user-12345678901234567890',
            user_display: 'alice@acme.com',
            data: {
              count: 2,
              decisions: [
                {
                  tool_call_id: 'call-1',
                  decision: 'ALLOW',
                  reason: 'benign fetch',
                  tainted: false,
                  ts: 1755000003,
                },
                {
                  tool_call_id: 'call-2',
                  decision: 'DENY',
                  reason: 'blocked by policy',
                  tainted: true,
                  ts: 1755000004,
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
    // agentTitle is rendered by the skeleton shell too; wait for a marker that
    // only exists once the audit data has rendered (KPI section) so the
    // subsequent data assertions cannot race the async load under heavy load.
    await waitFor(() => {
      expect(screen.getByText('agentTotalEvents')).toBeInTheDocument();
    });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/enterprise/org/me'),
      expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer test-token' }) }),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/enterprise/org/org-1/agent-audit/events'),
      expect.anything(),
    );

    expect(screen.getAllByText('5').length).toBeGreaterThan(0);
    expect(screen.getAllByText('2').length).toBeGreaterThan(0);
    expect(screen.getAllByText('1').length).toBeGreaterThan(0);
    expect(screen.getByText('agentSecurityBlocks')).toBeInTheDocument();
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

  it('classifies tool_failure as error and approval-type events as approval', async () => {
    const routes: Route[] = [
      { method: 'GET', url: '/api/enterprise/org/me', body: ORG_BODY },
      {
        method: 'GET',
        url: '/api/enterprise/org/org-1/agent-audit/events',
        body: {
          total: 2,
          tool_call_total: 0,
          security_event_total: 0,
          scanned_sandboxes: 1,
          failed_sandboxes: [],
          events: [
            {
              seq: 10,
              ts: 1755000000,
              type: 'tool_failure',
              sid: 'session-abc',
              sandbox_id: 'sandbox-1',
              user_id: 'user-1',
              data: { tool_name: 'bash', error: 'command not found' },
            },
            {
              seq: 11,
              ts: 1755000001,
              type: 'tool_approval_request',
              sid: 'session-abc',
              sandbox_id: 'sandbox-1',
              user_id: 'user-1',
              data: { tool_name: 'bash', tool_call_id: 'call-2' },
            },
            {
              seq: 12,
              ts: 1755000002,
              type: 'desktop_control_approval_request',
              sid: 'session-abc',
              sandbox_id: 'sandbox-1',
              user_id: 'user-1',
              data: { tool_name: 'desktop_control' },
            },
          ],
        },
      },
    ];
    vi.stubGlobal('fetch', mockFetchRoutes(routes));
    render(<AgentAuditView />);

    await waitFor(() => {
      expect(screen.getByText(/^toneError/)).toBeInTheDocument();
    });
    expect(screen.getAllByText(/^toneApproval/)).toHaveLength(2);
  });

  it('renders member badges and the total hint for aggregated events', async () => {
    vi.stubGlobal('fetch', mockFetchRoutes(auditRoutes()));
    render(<AgentAuditView />);

    await waitFor(() => {
      expect(screen.getAllByText('web_search').length).toBeGreaterThan(0);
    });

    // 邮箱徽标（alice@acme.com），tooltip 含完整 user_id
    expect(screen.getAllByText('alice@acme.com').length).toBeGreaterThan(0);
    // 徽标 tooltip 带完整身份
    expect(screen.getAllByTitle('alice@acme.com (user-12345678901234567890)').length).toBe(3);
    // total 提示文案
    expect(screen.getByText('agentShowingLatest')).toBeInTheDocument();
  });

  it('expands an event to reveal security decisions', async () => {
    vi.stubGlobal('fetch', mockFetchRoutes(auditRoutes()));
    render(<AgentAuditView />);

    await waitFor(() => {
      expect(screen.getAllByText('web_search').length).toBeGreaterThan(0);
    });

    const securityRow = screen.getByText('eventTypes.securityAudit').closest('button');
    expect(securityRow).not.toBeNull();
    await userEvent.click(securityRow as HTMLButtonElement);

    expect(screen.getByText(/^agentSecurityDecisions/)).toBeInTheDocument();
    expect(screen.getByText('ALLOW')).toBeInTheDocument();
    expect(screen.getByText('benign fetch')).toBeInTheDocument();
    // DENY decisions (BLOCK/DENY/REDACT/LEAK) must render highlighted red.
    const denyText = screen.getByText('DENY');
    expect(denyText).toBeInTheDocument();
    expect(screen.getByText('blocked by policy')).toBeInTheDocument();
    const denyCard = denyText.closest('div.rounded-md');
    expect(denyCard?.className).toContain('border-rose-500/25');
    expect(denyCard?.className).toContain('bg-rose-500/5');
  });

  it('renders empty state when there are no events', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetchRoutes([
        {
          method: 'GET',
          url: '/api/enterprise/org/me',
          body: ORG_BODY,
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

  it('shows an error when the organization lookup fails', async () => {
    const fetchMock = vi.fn(async () => {
      return { ok: false, status: 500, json: async () => ({}), text: async () => '' } as Response;
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<AgentAuditView />);

    await waitFor(() => {
      expect(screen.getByText(/^agentOrgLoadFailed/)).toBeInTheDocument();
    });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/enterprise/org/me'),
      expect.anything(),
    );
  });

  it('shows an error banner when the agent audit request fails', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input).split('?')[0];
      if (path.endsWith('/api/enterprise/org/me')) {
        return okResponse(ORG_BODY);
      }
      return {
        ok: false,
        status: 500,
        json: async () => ({ detail: 'boom' }),
        text: async () => 'boom',
      } as Response;
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<AgentAuditView />);

    await waitFor(() => {
      expect(screen.getByText(/^agentLoadFailed/)).toBeInTheDocument();
    });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/agent-audit/events'),
      expect.anything(),
    );
  });

  it('refetches with the new window when the time range changes', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const path = url.split('?')[0];
      if (path.endsWith('/api/enterprise/org/me')) {
        return okResponse(ORG_BODY);
      }
      if (path.endsWith('/agent-audit/events')) {
        const hours = new URL(url).searchParams.get('hours');
        return okResponse({
          total: hours === '168' ? 5 : 2,
          scanned_sandboxes: 1,
          failed_sandboxes: [],
          events: [],
        });
      }
      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<AgentAuditView />);
    await waitFor(() => {
      expect(screen.getAllByText('2').length).toBeGreaterThan(0);
    });

    await userEvent.click(screen.getByRole('combobox'));
    await userEvent.click(await screen.findByRole('option', { name: '7d' }));

    await waitFor(() => {
      expect(screen.getAllByText('5').length).toBeGreaterThan(0);
    });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('hours=168'),
      expect.anything(),
    );
  });

  it('ignores a stale response when the time range changes quickly', async () => {
    const pending168h: { resolve: ((body: unknown) => void) | null } = { resolve: null };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const path = url.split('?')[0];
      if (path.endsWith('/api/enterprise/org/me')) {
        return okResponse(ORG_BODY);
      }
      if (path.endsWith('/agent-audit/events')) {
        const hours = new URL(url).searchParams.get('hours');
        if (hours === '24') {
          return okResponse({ total: 2, scanned_sandboxes: 1, failed_sandboxes: [], events: [] });
        }
        if (hours === '720') {
          return okResponse({ total: 99, scanned_sandboxes: 1, failed_sandboxes: [], events: [] });
        }
        return new Promise<Response>((resolve) => {
          pending168h.resolve = (body: unknown) => resolve(okResponse(body));
        });
      }
      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<AgentAuditView />);
    await waitFor(() => {
      expect(screen.getAllByText('2').length).toBeGreaterThan(0);
    });

    await userEvent.click(screen.getByRole('combobox'));
    await userEvent.click(await screen.findByRole('option', { name: '7d' }));
    await waitFor(() => {
      expect(pending168h.resolve).not.toBeNull();
    });

    await userEvent.click(screen.getByRole('combobox'));
    await userEvent.click(await screen.findByRole('option', { name: '30d' }));
    await waitFor(() => {
      expect(screen.getAllByText('99').length).toBeGreaterThan(0);
    });

    pending168h.resolve?.({ total: 5, scanned_sandboxes: 1, failed_sandboxes: [], events: [] });
    await new Promise((r) => setTimeout(r, 20));

    expect(screen.queryByText('5')).toBeNull();
    expect(screen.getAllByText('99').length).toBeGreaterThan(0);
  });

  it('does not paint security blocks red when the deny total is zero', async () => {
    const routes: Route[] = [
      { method: 'GET', url: '/api/enterprise/org/me', body: ORG_BODY },
      {
        method: 'GET',
        url: '/api/enterprise/org/org-1/agent-audit/events',
        body: {
          total: 0,
          tool_call_total: 0,
          security_event_total: 0,
          security_deny_total: 0,
          scanned_sandboxes: 1,
          failed_sandboxes: [],
          events: [],
        },
      },
    ];
    vi.stubGlobal('fetch', mockFetchRoutes(routes));
    render(<AgentAuditView />);

    await waitFor(() => {
      expect(screen.getByText('agentSecurityBlocks')).toBeInTheDocument();
    });

    const label = screen.getByText('agentSecurityBlocks');
    const card = label.closest('div.rounded-lg');
    const value = card?.querySelector('.text-2xl.font-bold');
    expect(value).not.toBeNull();
    expect(value?.className).not.toContain('text-red-600');
  });

  it('paints security blocks red when the deny total is above zero', async () => {
    const routes: Route[] = [
      { method: 'GET', url: '/api/enterprise/org/me', body: ORG_BODY },
      {
        method: 'GET',
        url: '/api/enterprise/org/org-1/agent-audit/events',
        body: {
          total: 1,
          tool_call_total: 0,
          security_event_total: 1,
          security_deny_total: 3,
          scanned_sandboxes: 1,
          failed_sandboxes: [],
          events: [],
        },
      },
    ];
    vi.stubGlobal('fetch', mockFetchRoutes(routes));
    render(<AgentAuditView />);

    await waitFor(() => {
      expect(screen.getByText('agentSecurityBlocks')).toBeInTheDocument();
    });

    const label = screen.getByText('agentSecurityBlocks');
    const card = label.closest('div.rounded-lg');
    const value = card?.querySelector('.text-2xl.font-bold');
    expect(value?.textContent).toBe('3');
    expect(value?.className).toContain('text-red-600');
  });
});
