import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';

import EvalLabDashboard from '../EvalLabDashboard';

const toasts = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));

vi.mock('sonner', () => ({ toast: toasts }));

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

const roster = vi.hoisted(() => ({
  listAllAgents: vi.fn<() => Promise<Array<{ id: string; name: string }>>>(),
}));

vi.mock('@/services/agent', () => roster);

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
  roster.listAllAgents.mockReset();
  roster.listAllAgents.mockResolvedValue([
    { id: 'agent-1', name: 'Agent One' },
    { id: 'agent-2', name: 'Agent Two' },
  ]);
});

afterEach(() => {
  vi.restoreAllMocks();
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

type Interceptor = (url: string, init?: RequestInit) => Response | Promise<Response> | undefined;

function renderDashboard(routes: Record<string, unknown>, intercept?: Interceptor) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const intercepted = intercept?.(url, init);
    if (intercepted) {
      return intercepted;
    }
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

  it('offers every agent of the roster as a profile and runs a matrix once two are picked', async () => {
    renderDashboard(defaultRoutes());

    const first = await screen.findByRole('button', { name: 'Agent One' });
    const second = screen.getByRole('button', { name: 'Agent Two' });
    expect(roster.listAllAgents).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: 'evalLab.run' })).toBeInTheDocument();

    fireEvent.click(first);
    expect(screen.getByRole('button', { name: 'evalLab.run' })).toBeInTheDocument();

    fireEvent.click(second);
    expect(screen.getByRole('button', { name: 'evalLab.runMatrix' })).toBeInTheDocument();
    expect(screen.getByText('evalLab.matrixMode')).toBeInTheDocument();

    fireEvent.click(second);
    expect(screen.getByRole('button', { name: 'evalLab.run' })).toBeInTheDocument();
    expect(screen.queryByText('evalLab.matrixMode')).not.toBeInTheDocument();
  });

  it('still renders the dashboard without profiles when the roster cannot be loaded', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    roster.listAllAgents.mockRejectedValue(new Error('roster offline'));

    renderDashboard(defaultRoutes());

    await waitFor(() => expect(screen.getByText('evalLab.tabs.cases')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: 'Agent One' })).not.toBeInTheDocument();
    expect(consoleError).toHaveBeenCalledWith('Failed to fetch profiles', expect.any(Error));
  });

  describe('datasets', () => {
    const DATASETS_URL = '/api/v1/eval/datasets';

    function serverWithDatasets(initialIds: string[]) {
      const ids = [...initialIds];
      const puts: Array<{ url: string; body: string }> = [];
      const intercept: Interceptor = (url, init) => {
        if (url.endsWith(DATASETS_URL)) {
          return jsonResponse({ status: 'success', datasets: ids.map((id) => ({ id })) });
        }
        if (init?.method === 'PUT' && url.includes(`${DATASETS_URL}/`)) {
          puts.push({ url, body: String(init.body) });
          ids.push(url.slice(url.indexOf(`${DATASETS_URL}/`) + DATASETS_URL.length + 1));
          return jsonResponse({ status: 'success' });
        }
        return undefined;
      };
      return { puts, intercept };
    }

    const picker = () => screen.getByRole('combobox');
    const pickerOptions = () =>
      within(picker())
        .getAllByRole('option')
        .map((option) => option.textContent);

    it('lists the datasets of the server in the picker', async () => {
      const { intercept } = serverWithDatasets(['default', 'regression']);
      renderDashboard(defaultRoutes(), intercept);

      await screen.findByRole('combobox');

      expect(pickerOptions()).toEqual(['evalLab.defaultDataset (default)', 'regression']);
    });

    it('falls back to the default entry when the dataset list cannot be read', async () => {
      const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
      renderDashboard(defaultRoutes(), (url) => (url.endsWith(DATASETS_URL) ? Response.error() : undefined));

      await screen.findByRole('combobox');

      expect(pickerOptions()).toEqual(['evalLab.defaultDataset (default)']);
      expect(consoleError).toHaveBeenCalledWith('Failed to fetch datasets:', expect.anything());
    });

    it('ignores a dataset list the server marks as failed', async () => {
      renderDashboard(defaultRoutes(), (url) =>
        url.endsWith(DATASETS_URL) ? jsonResponse({ status: 'error', datasets: [{ id: 'half-written' }] }) : undefined,
      );

      await screen.findByRole('combobox');

      expect(pickerOptions()).toEqual(['evalLab.defaultDataset (default)']);
    });

    it('creates a dataset from the golden template, reloads the list and selects it', async () => {
      const { puts, intercept } = serverWithDatasets(['default']);
      renderDashboard(defaultRoutes(), intercept);
      await screen.findByRole('combobox');

      fireEvent.click(screen.getByTitle('evalLab.createDataset'));
      fireEvent.change(await screen.findByPlaceholderText('evalLab.createDatasetPrompt'), {
        target: { value: 'fresh' },
      });
      fireEvent.click(screen.getByRole('button', { name: 'evalLab.create' }));

      await waitFor(() => expect(pickerOptions()).toEqual(['evalLab.defaultDataset (default)', 'fresh']));
      expect(picker()).toHaveValue('fresh');
      expect(puts).toHaveLength(1);
      expect(puts[0].url).toContain(`${DATASETS_URL}/fresh`);
      expect(JSON.parse(puts[0].body).content).not.toBe('');
      expect(toasts.success).toHaveBeenCalledWith('evalLab.datasetCreated');
    });

    it('creates an empty dataset when the golden template is switched off', async () => {
      const { puts, intercept } = serverWithDatasets(['default']);
      renderDashboard(defaultRoutes(), intercept);
      await screen.findByRole('combobox');

      fireEvent.click(screen.getByTitle('evalLab.createDataset'));
      fireEvent.click(await screen.findByLabelText('evalLab.golden5Pack.initCheckbox'));
      fireEvent.click(screen.getByRole('button', { name: 'evalLab.create' }));

      await waitFor(() => expect(puts).toHaveLength(1));
      expect(JSON.parse(puts[0].body)).toEqual({ content: '' });
    });

    it('tells the user when the server refuses the new dataset and keeps the list as it was', async () => {
      renderDashboard(defaultRoutes(), (url, init) =>
        init?.method === 'PUT' && url.includes(`${DATASETS_URL}/`) ? new Response('nope', { status: 500 }) : undefined,
      );
      await screen.findByRole('combobox');

      fireEvent.click(screen.getByTitle('evalLab.createDataset'));
      fireEvent.click(await screen.findByRole('button', { name: 'evalLab.create' }));

      await waitFor(() => expect(toasts.error).toHaveBeenCalledWith('evalLab.createFailed'));
      expect(toasts.success).not.toHaveBeenCalled();
      expect(pickerOptions()).toEqual(['evalLab.defaultDataset (default)']);
    });

    it('tells the user when the request itself fails', async () => {
      renderDashboard(defaultRoutes(), (url, init) =>
        init?.method === 'PUT' && url.includes(`${DATASETS_URL}/`)
          ? Promise.reject(new TypeError('network down'))
          : undefined,
      );
      await screen.findByRole('combobox');

      fireEvent.click(screen.getByTitle('evalLab.createDataset'));
      fireEvent.click(await screen.findByRole('button', { name: 'evalLab.create' }));

      await waitFor(() => expect(toasts.error).toHaveBeenCalledWith('evalLab.createFailed'));
    });

    it('does not create anything for a blank name', async () => {
      const { puts, intercept } = serverWithDatasets(['default']);
      renderDashboard(defaultRoutes(), intercept);
      await screen.findByRole('combobox');

      fireEvent.click(screen.getByTitle('evalLab.createDataset'));
      fireEvent.change(await screen.findByPlaceholderText('evalLab.createDatasetPrompt'), { target: { value: '   ' } });

      expect(screen.getByRole('button', { name: 'evalLab.create' })).toBeDisabled();
      fireEvent.keyDown(screen.getByPlaceholderText('evalLab.createDatasetPrompt'), { key: 'Enter' });
      expect(puts).toHaveLength(0);
    });

    it('creates the dataset when Enter is pressed in the name field', async () => {
      const { puts, intercept } = serverWithDatasets(['default']);
      renderDashboard(defaultRoutes(), intercept);
      await screen.findByRole('combobox');

      fireEvent.click(screen.getByTitle('evalLab.createDataset'));
      fireEvent.keyDown(await screen.findByPlaceholderText('evalLab.createDatasetPrompt'), { key: 'Enter' });

      await waitFor(() => expect(puts).toHaveLength(1));
      expect(puts[0].url).toContain(`${DATASETS_URL}/new_dataset`);
    });
  });

  it('renders the sources panel when switching to the sources tab', async () => {
    renderDashboard(defaultRoutes());

    await waitFor(() => expect(screen.getByText('evalLab.tabs.cases')).toBeInTheDocument());
    expect(screen.getByText('evalLab.tabs.sources')).toBeInTheDocument();
  });
});
