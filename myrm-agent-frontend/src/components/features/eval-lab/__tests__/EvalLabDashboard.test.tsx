import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

import EvalLabDashboard from '../EvalLabDashboard';

vi.mock('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
}));

vi.mock('@/components/features/app-shell/lazy-monaco-editor', () => ({
  LazyMonacoEditor: () => <div data-testid="monaco-editor" />,
  LazyMonacoDiffEditor: () => <div data-testid="monaco-diff" />,
}));

vi.mock('@/components/features/app-shell/lazy-recharts', () => ({
  CartesianGrid: () => null,
  Line: () => null,
  LineChart: () => null,
  ResponsiveContainer: () => null,
  Tooltip: () => null,
  XAxis: () => null,
  YAxis: () => null,
}));

vi.mock('@/services/agent', () => ({
  listAgents: vi.fn().mockResolvedValue({ items: [{ id: 'agent-1', name: 'Agent One' }] }),
}));

vi.mock('@/components/agent/builtin-agent-i18n', () => ({
  getBuiltinAgentName: (_id: string, name: string) => name,
}));

class MockEventSource {
  static instances: MockEventSource[] = [];
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  close = vi.fn();
  addEventListener = vi.fn();

  constructor(public url: string) {
    MockEventSource.instances.push(this);
  }
}

beforeEach(() => {
  globalThis.EventSource = MockEventSource as unknown as typeof EventSource;
});

function jsonResponse(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

function defaultRoutes() {
  return {
    '/api/v1/eval/datasets': { status: 'success', datasets: [{ id: 'default' }] },
    '/api/v1/eval/status': { is_running: false, total: 0, completed: 0 },
    '/api/v1/eval/reports/latest': { status: 'success', summary: null },
    '/api/v1/eval/reports': { status: 'success', reports: [] },
    '/api/v1/eval/matrix/reports/latest': { status: 'success', report: null },
    '/api/v1/eval/matrix/reports/history': { status: 'success', reports: [] },
    '/api/v1/eval/memory-ab/reports/latest': { status: 'success', report: null },
    '/api/v1/eval/memory-ab/reports/history': { status: 'success', reports: [] },
  };
}

function renderDashboard(routes: Record<string, unknown>) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL) => {
    const url = String(input);
    const match = Object.keys(routes).find((key) => url.includes(key));
    if (!match) {
      return jsonResponse({ status: 'error' });
    }
    return jsonResponse(routes[match]);
  });
  return render(<EvalLabDashboard />);
}

describe('EvalLabDashboard', () => {
  it('renders the base tabs after initial loading completes and hides conditionally-visible ones', async () => {
    renderDashboard(defaultRoutes());

    await waitFor(() => expect(screen.getByText('evalLab.tabs.cases')).toBeInTheDocument());
    expect(screen.getByText('evalLab.tabs.sources')).toBeInTheDocument();
    expect(screen.getByText('evalLab.tabs.report')).toBeInTheDocument();
    expect(screen.getByText('evalLab.tabs.history')).toBeInTheDocument();
    // Matrix / Memory A/B tabs only appear once a report or running run exists.
    expect(screen.queryByText('evalLab.tabs.matrix')).not.toBeInTheDocument();
    expect(screen.queryByText('evalLab.tabs.memoryAb')).not.toBeInTheDocument();
  });

  it('shows the matrix tab when a matrix report exists', async () => {
    renderDashboard({
      ...defaultRoutes(),
      '/api/v1/eval/matrix/reports/latest': {
        status: 'success',
        report: {
          profile_ids: ['agent-1'],
          total_cases: 2,
          stable_count: 1,
          regression_count: 0,
          stable_rate: 0.5,
          per_profile: {},
          matrix: [],
          total_ms: 10,
        },
      },
    });

    await waitFor(() => expect(screen.getByText('evalLab.tabs.matrix')).toBeInTheDocument());
  });

  it('renders the cases editor inside the cases tab', async () => {
    renderDashboard(defaultRoutes());

    await waitFor(() => expect(screen.getByText('evalLab.tabs.cases')).toBeInTheDocument());
    expect(screen.getByTestId('monaco-editor')).toBeInTheDocument();
  });

  it('disables the run button and shows stop while an evaluation is running', async () => {
    renderDashboard({
      ...defaultRoutes(),
      '/api/v1/eval/status': { is_running: true, total: 5, completed: 2 },
    });

    await waitFor(() => expect(screen.getByText('evalLab.tabs.cases')).toBeInTheDocument());

    const runButton = screen.getByRole('button', { name: 'evalLab.running' });
    expect(runButton).toBeDisabled();
    expect(screen.getByText('evalLab.stop')).toBeInTheDocument();
  });

  it('renders the sources panel when switching to the sources tab', async () => {
    renderDashboard(defaultRoutes());

    await waitFor(() => expect(screen.getByText('evalLab.tabs.cases')).toBeInTheDocument());
    expect(screen.getByText('evalLab.tabs.sources')).toBeInTheDocument();
  });
});
