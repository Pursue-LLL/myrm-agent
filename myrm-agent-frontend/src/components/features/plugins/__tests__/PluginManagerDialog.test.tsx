import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import PluginManagerDialog from '../PluginManagerDialog';

const stableT: (key: string) => string = (key) => {
  const map: Record<string, string> = {
    title: 'Manage Plugins',
    subtitle: 'Manage imported Agent Plugins',
    'empty.title': 'No installed plugins',
    'empty.hint': 'Import a plugin first.',
    'empty.servers': 'No MCP servers',
    'badges.bundled': 'Bundled files',
    'serverState.enabled': 'Active',
    'serverState.disabled': 'Disabled',
    'serverState.disabledHint': 'Enable this MCP server in MCP Settings before using it',
    'actions.refresh': 'Refresh',
    'actions.close': 'Close',
    'actions.cancel': 'Cancel',
    'actions.uninstall': 'Uninstall',
    'errors.listFailed': 'Failed to load installed plugins',
    'errors.uninstallFailed': 'Failed to uninstall the plugin',
    'success.uninstalled': 'Uninstall Successful',
    'success.summary': 'Removed {servers} MCP server(s) and unbound {agents} agent(s)',
    'confirm.title': 'Confirm Uninstall',
    'confirm.description': 'Uninstalling "{name}" removes its MCP servers.',
  };
  return map[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

const mockToast = vi.hoisted(() => vi.fn());
vi.mock('@/hooks/shared/useToast', () => ({
  toast: mockToast,
}));

const { reloadKeys } = vi.hoisted(() => ({ reloadKeys: vi.fn() }));
vi.mock('@/services/config', () => ({ getConfigSyncManager: () => ({ reloadKeys }) }));

vi.mock('sonner', () => ({
  toast: Object.assign(vi.fn(), {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
    dismiss: vi.fn(),
  }),
}));

vi.mock('@/components/primitives/dialog', () => ({
  Dialog: ({ children, open }: { children: React.ReactNode; open: boolean }) =>
    open ? <div data-testid="dialog">{children}</div> : null,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div data-testid="dialog-content">{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div data-testid="dialog-header">{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h2 data-testid="dialog-title">{children}</h2>,
  DialogDescription: ({ children }: { children: React.ReactNode }) => (
    <p data-testid="dialog-description">{children}</p>
  ),
}));

vi.mock('@/components/primitives/alert-dialog', () => ({
  AlertDialog: ({ children, open }: { children: React.ReactNode; open: boolean }) =>
    open ? <div data-testid="alert-dialog">{children}</div> : null,
  AlertDialogContent: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="alert-content">{children}</div>
  ),
  AlertDialogHeader: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  AlertDialogTitle: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  AlertDialogDescription: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  AlertDialogFooter: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  AlertDialogCancel: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  AlertDialogAction: ({
    children,
    onClick,
  }: {
    children: React.ReactNode;
    onClick?: (e: React.MouseEvent) => void;
  }) => <button onClick={onClick as never}>{children}</button>,
}));

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

const baseProps = { open: true, onOpenChange: vi.fn(), onPluginChanged: vi.fn() };

describe('PluginManagerDialog', () => {
  beforeEach(() => {
    reloadKeys.mockReset();
    reloadKeys.mockResolvedValue(undefined);
    baseProps.onPluginChanged.mockClear();
  });

  /** Lists `demo-plugin`, then confirms its uninstall; the DELETE request answers with `deleteResponse`. */
  async function uninstallDemoPlugin(deleteResponse: unknown) {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [{ name: 'demo-plugin', servers: ['pdf-server'], has_bundled_files: false }],
      })
      .mockResolvedValueOnce(deleteResponse);

    render(<PluginManagerDialog {...baseProps} />);
    await screen.findByText('demo-plugin');
    fireEvent.click(screen.getByRole('button', { name: 'Uninstall' }));
    // The confirmation's action carries the same label; it is the last "Uninstall" button.
    const actions = await screen.findAllByRole('button', { name: 'Uninstall' });
    fireEvent.click(actions[actions.length - 1]);
  }

  it('renders server status badges from server_meta', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [
        {
          name: 'demo-plugin',
          servers: ['pdf-server', 'web-server'],
          server_meta: [
            { name: 'pdf-server', enabled: false },
            { name: 'web-server', enabled: true },
          ],
          has_bundled_files: true,
        },
      ],
    });

    render(<PluginManagerDialog {...baseProps} />);

    expect(await screen.findByText('demo-plugin')).toBeInTheDocument();
    expect(screen.getByText('pdf-server')).toBeInTheDocument();
    expect(screen.getByText('web-server')).toBeInTheDocument();
    // disabled server shows "Disabled" badge
    expect(screen.getByText('Disabled')).toBeInTheDocument();
    // enabled server shows "Active" badge
    expect(screen.getByText('Active')).toBeInTheDocument();
    // bundled badge
    expect(screen.getByText('Bundled files')).toBeInTheDocument();
    // disabled server carries the disabledHint guidance as its native title
    const disabledHint = screen.getByTitle('Enable this MCP server in MCP Settings before using it');
    expect(disabledHint).toBeInTheDocument();
    expect(disabledHint).toHaveClass('cursor-help');
  });

  it('falls back to plain server names when server_meta is absent', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [
        {
          name: 'legacy-plugin',
          servers: ['srv-a'],
          has_bundled_files: false,
        },
      ],
    });

    render(<PluginManagerDialog {...baseProps} />);

    expect(await screen.findByText('legacy-plugin')).toBeInTheDocument();
    expect(screen.getByText('srv-a')).toBeInTheDocument();
  });

  it('shows empty state when no plugins installed', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => [] });

    render(<PluginManagerDialog {...baseProps} />);

    expect(await screen.findByText('No installed plugins')).toBeInTheDocument();
  });

  it('shows only the localized title when listing fails, never the technical cause', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    mockFetch.mockResolvedValueOnce({ ok: false, status: 500 });

    render(<PluginManagerDialog {...baseProps} />);

    await waitFor(() =>
      expect(mockToast).toHaveBeenCalledWith({ title: 'Failed to load installed plugins', variant: 'destructive' }),
    );
    expect(consoleError).toHaveBeenCalled();
    consoleError.mockRestore();
  });

  it('shows only the localized title when uninstalling fails, never the server sentence', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});

    await uninstallDemoPlugin({ ok: false, status: 500, json: async () => ({ detail: 'database is locked' }) });

    await waitFor(() =>
      expect(mockToast).toHaveBeenCalledWith({ title: 'Failed to uninstall the plugin', variant: 'destructive' }),
    );
    expect(consoleError).toHaveBeenCalledWith(
      'Plugin uninstall failed:',
      expect.objectContaining({ message: 'database is locked' }),
    );
    // Nothing was removed on the server, so the cached MCP servers are still right.
    expect(reloadKeys).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });

  it('reloads the cached MCP servers after an uninstall that removed servers, so they are not saved back', async () => {
    await uninstallDemoPlugin({
      ok: true,
      json: async () => ({ plugin_name: 'demo-plugin', removed_servers: 2, unbound_agents: 0, removed_files: false }),
    });

    await waitFor(() => expect(reloadKeys).toHaveBeenCalledExactlyOnceWith(['mcpServers']));
    expect(baseProps.onPluginChanged).toHaveBeenCalled();
  });

  it('leaves the cached MCP servers alone when the uninstall removed none', async () => {
    await uninstallDemoPlugin({
      ok: true,
      json: async () => ({ plugin_name: 'demo-plugin', removed_servers: 0, unbound_agents: 1, removed_files: false }),
    });

    await waitFor(() => expect(baseProps.onPluginChanged).toHaveBeenCalled());
    expect(reloadKeys).not.toHaveBeenCalled();
  });
});
