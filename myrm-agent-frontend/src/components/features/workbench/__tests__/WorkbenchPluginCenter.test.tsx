/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { WorkbenchPluginCenter } from '../tabs/WorkbenchPluginCenter';
import * as workbenchService from '@/services/workbench';

const stableT = (key: string, values?: Record<string, unknown>) => {
    if (values && 'id' in values) {
      return `${key}:${String(values.id)}`;
    }
    return key;
  };

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/services/workbench', () => ({
  fetchWorkbenchPlugins: vi.fn(),
  probePluginHealth: vi.fn(),
}));

const mockPlugins: workbenchService.PluginItem[] = [
  {
    plugin_id: 'plugin-git',
    name: 'Git Integration',
    version: '1.2.0',
    description: 'Embedded git diff and log visualizer',
    status: 'healthy',
    author: 'Myrmidon',
    github_repo: 'https://github.com/myrmidon/git-plugin',
    is_installed: true,
    last_probed_at: '2026-01-01T00:00:00Z',
  },
  {
    plugin_id: 'plugin-linter',
    name: 'ESLint / Ruff Bridge',
    version: '0.9.1',
    description: 'Real-time diagnostic linting bridge',
    status: 'degraded',
    author: 'Community',
    github_repo: null,
    is_installed: true,
    last_probed_at: '2026-02-01T00:00:00Z',
  },
];

describe('WorkbenchPluginCenter component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(workbenchService.fetchWorkbenchPlugins).mockResolvedValue(mockPlugins);
    vi.mocked(workbenchService.probePluginHealth).mockResolvedValue({
      plugin_id: 'plugin-linter',
      status: 'healthy',
      latency_ms: 18,
      message: 'All endpoints responding within SLA',
      details: {},
    });
  });

  it('renders plugin items and statuses after fetch', async () => {
    render(<WorkbenchPluginCenter />);

    await waitFor(() => {
      expect(screen.getByText('Git Integration')).toBeDefined();
      expect(screen.getByText('v1.2.0')).toBeDefined();
      expect(screen.getByText('ESLint / Ruff Bridge')).toBeDefined();
      expect(screen.getByText('degraded')).toBeDefined();
    });
  });

  it('probes plugin health and shows probe result card', async () => {
    render(<WorkbenchPluginCenter />);

    await waitFor(() => {
      expect(screen.getByText('ESLint / Ruff Bridge')).toBeDefined();
    });

    const probeButtons = screen.getAllByRole('button', { name: /probeAction/i });
    // Click probe on the second plugin (plugin-linter)
    fireEvent.click(probeButtons[1]);

    await waitFor(() => {
      expect(workbenchService.probePluginHealth).toHaveBeenCalledWith('plugin-linter');
      expect(screen.getByText(/All endpoints responding within SLA/)).toBeDefined();
      expect(screen.getByText(/probeSuccessTitle:plugin-linter/)).toBeDefined();
    });
  });

  it('repairs degraded plugin when clicking repair button', async () => {
    render(<WorkbenchPluginCenter />);

    await waitFor(() => {
      expect(screen.getByText('repairAction')).toBeDefined();
    });

    const repairBtn = screen.getByRole('button', { name: /repairAction/i });
    fireEvent.click(repairBtn);

    // After repair, status changes to healthy and repair button is gone
    await waitFor(() => {
      expect(screen.queryByText('repairAction')).toBeNull();
    });
  });

  it('reloads plugins when refresh button is clicked', async () => {
    render(<WorkbenchPluginCenter />);

    await waitFor(() => {
      expect(screen.getByText('Git Integration')).toBeDefined();
    });

    const refreshBtn = screen.getByRole('button', { name: 'refreshAction' });
    fireEvent.click(refreshBtn);

    await waitFor(() => {
      expect(workbenchService.fetchWorkbenchPlugins).toHaveBeenCalledTimes(2);
    });
  });
});
