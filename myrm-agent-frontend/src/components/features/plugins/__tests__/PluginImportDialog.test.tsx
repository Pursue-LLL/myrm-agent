import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const stableT: (key: string) => string = (key) => {
  const map: Record<string, string> = {
    title: 'Import Plugin',
    subtitle: 'Install an agent plugin package',
    'upload.dropHint': 'Drop your plugin ZIP here',
    'upload.parsing': 'Parsing...',
    'upload.formatHint': 'Accepts .zip archives',
    'upload.archiveOnly': 'Only .zip archives are supported',
    'upload.singleArchiveOnly': 'Only a single archive is allowed',
    'upload.tooLarge': 'Archive exceeds the 20MB limit',
    'errors.previewFailed': 'Preview failed',
    'errors.confirmFailed': 'Confirm failed',
    'errors.parseTitle': 'Parse error',
    'errors.confirmTitle': 'Confirm error',
    'actions.reselect': 'Reselect',
    'actions.cancel': 'Cancel',
    'actions.confirm': 'Import',
    'actions.install': 'Install',
    'actions.replace': 'Replace',
    'actions.skip': 'Skip',
    'actions.selectAll': 'Select all',
    'actions.skipAll': 'Skip all',
    'bind.label': 'Bind to agent',
    'bind.placeholder': 'Select an agent',
    'bind.hint': 'The selected agent will receive the MCP servers.',
    'success.title': 'Import complete',
    'success.description': 'Imported skills and servers',
    summary: 'Summary',
    'sections.skills': 'Skills',
    'sections.servers': 'MCP Servers',
    'sections.files': 'files',
    'sections.placeholder': 'needs config',
    'empty.title': 'No importable components',
    'empty.hint': 'Check the diagnostics',
    'serverType.local': 'Local process',
    'serverType.remote': 'Remote service',
    'sections.envCount': '{count} env vars',
    'security.blocked': 'Blocked: {count} security risk(s) found — automatically skipped',
    'security.oversized': 'Skill content exceeds the storage size limit (64 KB) — automatically skipped',
    'security.conflict': 'A skill with this name already exists — Replace upgrades it, or Skip to keep the current one',
  };
  return map[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

const mockFetchAgents = vi.fn();
let mockAgents: Array<{ id: string; name: string }>;

vi.mock('@/store/useAgentStore', () => ({
  default: () => ({ agents: mockAgents, fetchAgents: mockFetchAgents }),
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
  DialogContent: ({ children, className }: { children: React.ReactNode; className?: string }) => (
    <div data-testid="dialog-content" className={className}>
      {children}
    </div>
  ),
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div data-testid="dialog-header">{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h2 data-testid="dialog-title">{children}</h2>,
  DialogDescription: ({ children }: { children: React.ReactNode }) => (
    <p data-testid="dialog-description">{children}</p>
  ),
}));

vi.mock('@/components/primitives/select', () => ({
  Select: ({
    value,
    onValueChange,
    children,
    disabled,
  }: {
    value?: string;
    onValueChange: (value: string) => void;
    children: React.ReactNode;
    disabled?: boolean;
  }) => (
    <select
      data-testid="agent-select"
      value={value ?? ''}
      disabled={disabled}
      onChange={(e) => onValueChange(e.target.value)}
    >
      {children}
    </select>
  ),
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  SelectValue: ({ placeholder }: { placeholder?: string }) => <>{placeholder}</>,
  SelectContent: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  SelectItem: ({ value, children }: { value: string; children: React.ReactNode }) => (
    <option value={value}>{children}</option>
  ),
}));

vi.mock('@/components/primitives/scroll-area', () => ({
  ScrollArea: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const PLUGIN_PREVIEW = {
  session_id: 'sess-1',
  plugin: {
    name: 'reports-plugin',
    version: '1.0.0',
    description: 'PDF report generation',
    author: { name: 'Alice' },
    homepage: null,
    repository: null,
    license: 'MIT',
    keywords: ['pdf'],
  },
  skills: [
    {
      name: 'summarize',
      description: 'Summarize a PDF',
      file_count: 2,
      virtual_id: 'skill:0',
      security_issues: [],
      oversized_content: false,
      conflict: false,
    },
    {
      name: 'extract',
      description: 'Extract tables',
      file_count: 1,
      virtual_id: 'skill:1',
      security_issues: [],
      oversized_content: false,
      conflict: false,
    },
  ],
  servers: [
    {
      name: 'pdf-server',
      type: 'stdio',
      command: './bin/pdf',
      url: null,
      env_key_count: 1,
      has_placeholders: true,
      virtual_id: 'mcp:0',
    },
  ],
  diagnostics: [{ component: 'skill:1', code: 'warn', message: 'Missing description', level: 'warning' }],
  is_valid: true,
};

let fetchMock: ReturnType<typeof vi.fn>;

describe('PluginImportDialog', () => {
  beforeEach(() => {
    mockToast.mockClear();
    mockFetchAgents.mockClear();
    mockAgents = [{ id: 'agent-1', name: 'Research Assistant' }];
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  async function renderDialog() {
    const { default: PluginImportDialog } = await import('../PluginImportDialog');
    const onOpenChange = vi.fn();
    const onImportComplete = vi.fn();
    render(<PluginImportDialog open={true} onOpenChange={onOpenChange} onImportComplete={onImportComplete} />);
    return { onOpenChange, onImportComplete };
  }

  function selectFile(file: File) {
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });
  }

  it('renders the upload dropzone when open', async () => {
    await renderDialog();
    expect(screen.getByTestId('dialog')).toBeInTheDocument();
    expect(screen.getByText('Import Plugin')).toBeInTheDocument();
    expect(screen.getByText('Drop your plugin ZIP here')).toBeInTheDocument();
  });

  it('rejects a non-zip file with a user-facing error', async () => {
    await renderDialog();
    selectFile(new File(['x'], 'plugin.txt', { type: 'text/plain' }));
    expect(await screen.findByText('Only .zip archives are supported')).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('rejects multiple files at once', async () => {
    await renderDialog();
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, {
      target: {
        files: [
          new File(['a'], 'a.zip', { type: 'application/zip' }),
          new File(['b'], 'b.zip', { type: 'application/zip' }),
        ],
      },
    });
    expect(await screen.findByText('Only a single archive is allowed')).toBeInTheDocument();
  });

  it('rejects archives larger than 20MB', async () => {
    await renderDialog();
    const big = new File([new ArrayBuffer(21 * 1024 * 1024)], 'big.zip', {
      type: 'application/zip',
    });
    Object.defineProperty(big, 'size', { value: 21 * 1024 * 1024 });
    selectFile(big);
    expect(await screen.findByText('Archive exceeds the 20MB limit')).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('shows a parse error when the preview endpoint fails', async () => {
    fetchMock.mockResolvedValueOnce({ ok: false, json: async () => ({ detail: 'boom' }) });
    await renderDialog();
    selectFile(new File(['zip'], 'plugin.zip', { type: 'application/zip' }));
    expect(await screen.findByText('boom')).toBeInTheDocument();
  });

  it('renders the preview with plugin card, skills, servers and diagnostics', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => PLUGIN_PREVIEW,
    });
    await renderDialog();
    selectFile(new File(['zip'], 'plugin.zip', { type: 'application/zip' }));

    expect(await screen.findByText('reports-plugin')).toBeInTheDocument();
    expect(screen.getByText('v1.0.0')).toBeInTheDocument();
    expect(screen.getByText('MIT')).toBeInTheDocument();
    expect(screen.getByText('summarize')).toBeInTheDocument();
    expect(screen.getByText('extract')).toBeInTheDocument();
    expect(screen.getByText('pdf-server')).toBeInTheDocument();
    expect(screen.getByText('Missing description')).toBeInTheDocument();
    expect(screen.getByText(/needs config/)).toBeInTheDocument();
  });

  it('lets the user toggle a skill to skip and back', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => PLUGIN_PREVIEW,
    });
    await renderDialog();
    selectFile(new File(['zip'], 'plugin.zip', { type: 'application/zip' }));
    await screen.findByText('summarize');

    // Both skills + the MCP server start installed (3 "Install" toggles).
    const installButtons = screen.getAllByText('Install');
    expect(installButtons.length).toBeGreaterThanOrEqual(3);

    // Click the first skill's toggle (skill:0) to switch it to skip.
    fireEvent.click(installButtons[0]);
    expect(screen.getByText('Skip')).toBeInTheDocument();
    expect(screen.getAllByText('Install')).toHaveLength(2);

    // Toggle it back to install.
    fireEvent.click(screen.getByText('Skip'));
    expect(screen.getAllByText('Install')).toHaveLength(3);
    expect(screen.queryByText('Skip')).not.toBeInTheDocument();
  });

  it('submits the confirm request with the correct payload and finishes the flow', async () => {
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => PLUGIN_PREVIEW }).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ imported_skills: 2, imported_servers: 1 }),
    });
    const { onImportComplete } = await renderDialog();
    selectFile(new File(['zip'], 'plugin.zip', { type: 'application/zip' }));
    await screen.findByText('reports-plugin');

    // Bind to the agent and confirm.
    fireEvent.change(screen.getByTestId('agent-select'), {
      target: { value: 'agent-1' },
    });
    fireEvent.click(screen.getByText('Import'));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenNthCalledWith(
        2,
        '/api/v1/plugins/import/confirm',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: 'sess-1',
            skills: [
              { component: 'skill', virtual_id: 'skill:0', name: 'summarize', resolution: 'install' },
              { component: 'skill', virtual_id: 'skill:1', name: 'extract', resolution: 'install' },
            ],
            servers: [{ component: 'mcp', virtual_id: 'mcp:0', name: 'pdf-server', resolution: 'install' }],
            bind_agent_id: 'agent-1',
          }),
        }),
      );
    });

    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith({
        title: 'Import complete',
        description: expect.stringContaining('Imported skills and servers'),
      });
      expect(onImportComplete).toHaveBeenCalledTimes(1);
    });
  });

  it('shows an error toast when the confirm request fails', async () => {
    fetchMock
      .mockResolvedValueOnce({ ok: true, json: async () => PLUGIN_PREVIEW })
      .mockResolvedValueOnce({ ok: false, json: async () => ({ detail: 'confirm failed' }) });
    await renderDialog();
    selectFile(new File(['zip'], 'plugin.zip', { type: 'application/zip' }));
    await screen.findByText('reports-plugin');

    fireEvent.click(screen.getByText('Import'));

    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith({
        title: 'Confirm error',
        description: 'confirm failed',
        variant: 'destructive',
      });
    });
  });

  it('reselect resets the form back to the upload dropzone', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => PLUGIN_PREVIEW,
    });
    await renderDialog();
    selectFile(new File(['zip'], 'plugin.zip', { type: 'application/zip' }));
    await screen.findByText('reports-plugin');

    fireEvent.click(screen.getByText('Reselect'));
    expect(screen.getByText('Drop your plugin ZIP here')).toBeInTheDocument();
  });

  it('shows an empty state when the plugin has no importable components', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        ...PLUGIN_PREVIEW,
        skills: [],
        servers: [],
      }),
    });
    await renderDialog();
    selectFile(new File(['zip'], 'plugin.zip', { type: 'application/zip' }));
    expect(await screen.findByText('No importable components')).toBeInTheDocument();
  });

  it('renders a friendly server type label and env count badge', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => PLUGIN_PREVIEW,
    });
    await renderDialog();
    selectFile(new File(['zip'], 'plugin.zip', { type: 'application/zip' }));
    expect(await screen.findByText(/Local process/)).toBeInTheDocument();
    expect(screen.getByText('{count} env vars')).toBeInTheDocument();
  });

  it('marks skills with security issues as blocked and skips them by default', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        ...PLUGIN_PREVIEW,
        skills: [
          {
            name: 'risky',
            description: 'Dangerous skill',
            file_count: 1,
            virtual_id: 'skill:0',
            security_issues: ['Dangerous pattern detected: rm -rf'],
            oversized_content: false,
          },
        ],
      }),
    });
    await renderDialog();
    selectFile(new File(['zip'], 'plugin.zip', { type: 'application/zip' }));

    expect(await screen.findByText(/security risk/)).toBeInTheDocument();
    // The blocked skill is pre-skipped: only the MCP server offers an Install toggle.
    expect(screen.getAllByText('Install')).toHaveLength(1);
  });

  it('marks oversized skills as blocked and skips them by default', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        ...PLUGIN_PREVIEW,
        skills: [
          {
            name: 'huge',
            description: 'Too large',
            file_count: 1,
            virtual_id: 'skill:0',
            security_issues: [],
            oversized_content: true,
          },
        ],
      }),
    });
    await renderDialog();
    selectFile(new File(['zip'], 'plugin.zip', { type: 'application/zip' }));

    expect(await screen.findByText(/storage size limit|storage limit/)).toBeInTheDocument();
    // The oversized skill is pre-skipped: only the MCP server offers an Install toggle.
    expect(screen.getAllByText('Install')).toHaveLength(1);
  });

  it('marks conflicting skills, pre-skips them and allows replace', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        ...PLUGIN_PREVIEW,
        skills: [
          {
            name: 'summarize',
            description: 'Already installed skill',
            file_count: 1,
            virtual_id: 'skill:0',
            security_issues: [],
            oversized_content: false,
            conflict: true,
          },
        ],
      }),
    });
    await renderDialog();
    selectFile(new File(['zip'], 'plugin.zip', { type: 'application/zip' }));

    // Conflict hint is shown and the conflicting skill starts skipped (only the
    // MCP server keeps an Install toggle).
    expect(await screen.findByText(/already exists/)).toBeInTheDocument();
    expect(screen.getByText('Skip')).toBeInTheDocument();
    expect(screen.getAllByText('Install')).toHaveLength(1);

    // Switching it on upgrades in place (replace), not duplicate install.
    fireEvent.click(screen.getByText('Skip'));
    expect(screen.getByText('Replace')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Replace'));
    expect(screen.getByText('Skip')).toBeInTheDocument();
  });

  it('turns conflicting skills into replace when using Select all', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        ...PLUGIN_PREVIEW,
        skills: [
          {
            name: 'fresh',
            description: 'New skill',
            file_count: 1,
            virtual_id: 'skill:0',
            security_issues: [],
            oversized_content: false,
            conflict: false,
          },
          {
            name: 'summarize',
            description: 'Already installed skill',
            file_count: 1,
            virtual_id: 'skill:1',
            security_issues: [],
            oversized_content: false,
            conflict: true,
          },
        ],
      }),
    });
    await renderDialog();
    selectFile(new File(['zip'], 'plugin.zip', { type: 'application/zip' }));

    await screen.findByText(/already exists/);
    // The fresh skill starts installed; the conflicting one starts skipped.
    expect(screen.getAllByText('Install')).toHaveLength(2);
    expect(screen.getByText('Skip')).toBeInTheDocument();

    // Select all: the conflicting skill upgrades in place (Replace) instead of
    // creating a duplicate, while the fresh skill stays a plain install.
    // (Skills section renders before the MCP servers section, so [0] targets it.)
    fireEvent.click(screen.getAllByText('Select all')[0]);
    expect(screen.getByText('Replace')).toBeInTheDocument();
    expect(screen.getAllByText('Install')).toHaveLength(2);
    expect(screen.queryByText('Skip')).not.toBeInTheDocument();
  });

  it('submits replace resolution for conflicting skills', async () => {
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          ...PLUGIN_PREVIEW,
          skills: [
            {
              name: 'summarize',
              description: 'Already installed skill',
              file_count: 1,
              virtual_id: 'skill:0',
              security_issues: [],
              oversized_content: false,
              conflict: true,
            },
          ],
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ imported_skills: 1, imported_servers: 0 }),
      });
    await renderDialog();
    selectFile(new File(['zip'], 'plugin.zip', { type: 'application/zip' }));

    await screen.findByText(/already exists/);
    // Switch from default skip to replace, then confirm.
    fireEvent.click(screen.getByText('Skip'));
    fireEvent.click(screen.getByText('Import'));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenNthCalledWith(
        2,
        '/api/v1/plugins/import/confirm',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: 'sess-1',
            skills: [{ component: 'skill', virtual_id: 'skill:0', name: 'summarize', resolution: 'replace' }],
            servers: [{ component: 'mcp', virtual_id: 'mcp:0', name: 'pdf-server', resolution: 'install' }],
            bind_agent_id: null,
          }),
        }),
      );
    });
  });
});
