import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
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
    'serverState.disabledHint':
      'Enable this MCP server in MCP Settings before using it',
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

const mockToast = vi.fn();
vi.mock('@/hooks/shared/useToast', () => ({
  toast: mockToast,
}));

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
  DialogContent: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="dialog-content">{children}</div>
  ),
  DialogHeader: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="dialog-header">{children}</div>
  ),
  DialogTitle: ({ children }: { children: React.ReactNode }) => (
    <h2 data-testid="dialog-title">{children}</h2>
  ),
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

  it('shows an error toast on list failure', async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 500 });

    render(<PluginManagerDialog {...baseProps} />);

    await waitFor(() =>
      expect(mockToast).toHaveBeenCalledWith(
        expect.objectContaining({ variant: 'destructive' }),
      ),
    );
  });
});