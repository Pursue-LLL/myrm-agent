import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { confirmResult, previewPayload, serverPreview, skillPreview } from './pluginImportTestKit';

vi.mock('next-intl', async () => {
  const kit = await import('./pluginImportTestKit');
  return { useTranslations: kit.useTranslationsStub, useLocale: () => 'en' };
});

const mockFetchAgents = vi.fn();
let mockAgents: Array<{ id: string; name: string }>;

vi.mock('@/store/useAgentStore', () => ({
  default: () => ({ agents: mockAgents, fetchAgents: mockFetchAgents }),
}));

const mockToast = vi.fn();
vi.mock('@/hooks/shared/useToast', () => ({
  toast: mockToast,
}));

vi.mock('@/services/agent', () => ({
  getAgentReadiness: vi.fn().mockResolvedValue({ overall_level: 'ready', items: [], agent_id: 'a', checked_at: 0 }),
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

const PLUGIN_PREVIEW = previewPayload({
  skills: [
    skillPreview({ name: 'summarize', description: 'Summarize a PDF', file_count: 2, virtual_id: 'skill:0' }),
    skillPreview({ name: 'extract', description: 'Extract tables', file_count: 1, virtual_id: 'skill:1' }),
  ],
  servers: [serverPreview({ env_key_count: 1, has_placeholders: true })],
  diagnostics: [{ component: 'skill:1', code: 'warn', message: 'Missing description', level: 'warning' }],
});

const CONFLICTING_SKILL = skillPreview({ description: 'Already installed skill', conflict: true });

let fetchMock: ReturnType<typeof vi.fn>;

describe('PluginImportDialog', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    mockToast.mockClear();
    mockFetchAgents.mockClear();
    mockFetchAgents.mockResolvedValue(undefined);
    mockAgents = [{ id: 'agent-1', name: 'Research Assistant' }];
    fetchMock = vi.fn();
    global.fetch = fetchMock as unknown as typeof fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
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

  /** Render the dialog and drive it to the review step for `payload`. */
  async function openPreview(payload: ReturnType<typeof previewPayload>, ...followUps: unknown[]) {
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => payload });
    for (const body of followUps) {
      fetchMock.mockResolvedValueOnce({ ok: true, json: async () => body });
    }
    const handlers = await renderDialog();
    selectFile(new File(['zip'], 'plugin.zip', { type: 'application/zip' }));
    await screen.findByText(payload.plugin.name);
    return handlers;
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

  it('keeps the dropzone visible with a progress message while the archive is being parsed', async () => {
    fetchMock.mockReturnValueOnce(new Promise(() => {}));
    await renderDialog();
    selectFile(new File(['zip'], 'plugin.zip', { type: 'application/zip' }));
    expect(await screen.findByText('Parsing...')).toBeInTheDocument();
  });

  it('renders the preview with plugin card, skills, servers and diagnostics', async () => {
    await openPreview(PLUGIN_PREVIEW);

    expect(screen.getByText('v1.0.0')).toBeInTheDocument();
    expect(screen.getByText('MIT')).toBeInTheDocument();
    expect(screen.getByText('summarize')).toBeInTheDocument();
    expect(screen.getByText('extract')).toBeInTheDocument();
    expect(screen.getByText('pdf-server')).toBeInTheDocument();
    expect(screen.getByText('Missing description')).toBeInTheDocument();
    expect(screen.getByText(/needs config/)).toBeInTheDocument();
  });

  it('lets the user toggle a skill to skip and back', async () => {
    await openPreview(PLUGIN_PREVIEW);

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

  it('submits the confirm request and stays open on a result page instead of closing', async () => {
    const { onImportComplete, onOpenChange } = await openPreview(
      PLUGIN_PREVIEW,
      confirmResult({ imported_skills: 2, imported_servers: 1 }),
    );

    // Bind to the agent and confirm.
    fireEvent.change(screen.getByTestId('agent-select'), {
      target: { value: 'agent-1' },
    });
    fireEvent.click(screen.getByTestId('trusted-source-checkbox'));
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
            agents: [],
            bind_agent_id: 'agent-1',
          }),
        }),
      );
    });

    expect(await screen.findByText('Import complete')).toBeInTheDocument();
    expect(screen.getByText('Imported 0 agents, 2 skills and 1 servers')).toBeInTheDocument();
    expect(onImportComplete).toHaveBeenCalledTimes(1);
    expect(onOpenChange).not.toHaveBeenCalled();
    expect(mockToast).not.toHaveBeenCalled();

    // Done closes the dialog.
    fireEvent.click(screen.getByText('Done'));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('shows an error toast when the confirm request fails', async () => {
    fetchMock
      .mockResolvedValueOnce({ ok: true, json: async () => PLUGIN_PREVIEW })
      .mockResolvedValueOnce({ ok: false, json: async () => ({ detail: 'confirm failed' }) });
    await renderDialog();
    selectFile(new File(['zip'], 'plugin.zip', { type: 'application/zip' }));
    await screen.findByText('reports-plugin');

    fireEvent.click(screen.getByTestId('trusted-source-checkbox'));
    fireEvent.click(screen.getByText('Import'));

    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith({
        title: 'Confirm error',
        description: 'confirm failed',
        variant: 'destructive',
      });
    });
    // The review stays in place so the user can retry.
    expect(screen.getByText('summarize')).toBeInTheDocument();
  });

  it('reselect resets the form back to the upload dropzone', async () => {
    await openPreview(PLUGIN_PREVIEW);

    fireEvent.click(screen.getByText('Reselect'));
    expect(screen.getByText('Drop your plugin ZIP here')).toBeInTheDocument();
  });

  it('import another returns to the dropzone after a finished import', async () => {
    await openPreview(PLUGIN_PREVIEW, confirmResult({ imported_skills: 2, imported_servers: 1 }));
    fireEvent.click(screen.getByTestId('trusted-source-checkbox'));
    fireEvent.click(screen.getByText('Import'));
    await screen.findByText('Import complete');

    fireEvent.click(screen.getByText('Import another'));
    expect(screen.getByText('Drop your plugin ZIP here')).toBeInTheDocument();
  });

  it('shows an empty state when the plugin has no importable components', async () => {
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => previewPayload() });
    await renderDialog();
    selectFile(new File(['zip'], 'plugin.zip', { type: 'application/zip' }));
    expect(await screen.findByText('No importable components')).toBeInTheDocument();
  });

  it('renders a friendly server type label and env count badge', async () => {
    await openPreview(PLUGIN_PREVIEW);
    expect(screen.getByText(/Local process/)).toBeInTheDocument();
    expect(screen.getByText('1 env vars')).toBeInTheDocument();
  });

  it('marks skills with security issues as blocked and skips them by default', async () => {
    await openPreview(
      previewPayload({
        skills: [
          skillPreview({
            name: 'risky',
            description: 'Dangerous skill',
            security_issues: ['Dangerous pattern detected: rm -rf'],
          }),
        ],
        servers: [serverPreview()],
      }),
    );

    expect(screen.getByText(/security risk/)).toBeInTheDocument();
    // The blocked skill is pre-skipped: only the MCP server offers an Install toggle.
    expect(screen.getAllByText('Install')).toHaveLength(1);
  });

  it('marks oversized skills as blocked and skips them by default', async () => {
    await openPreview(
      previewPayload({
        skills: [
          skillPreview({
            name: 'huge',
            description: 'Too large',
            oversized_content: true,
            blocked_reason: 'oversized_content',
          }),
        ],
        servers: [serverPreview()],
      }),
    );

    expect(screen.getByText(/storage size limit/)).toBeInTheDocument();
    expect(screen.getAllByText('Install')).toHaveLength(1);
  });

  it('marks conflicting skills, pre-skips them and allows replace', async () => {
    await openPreview(
      previewPayload({
        skills: [{ ...CONFLICTING_SKILL, existing_version: '0.9.0' }],
        servers: [serverPreview()],
      }),
    );

    // Conflict hint and the installed version are shown; the conflicting skill starts skipped
    // (only the MCP server keeps an Install toggle).
    expect(screen.getByText(/already exists/)).toBeInTheDocument();
    expect(screen.getByText('Installed version: 0.9.0')).toBeInTheDocument();
    expect(screen.getByText('Skip')).toBeInTheDocument();
    expect(screen.getAllByText('Install')).toHaveLength(1);

    // Switching it on upgrades in place (replace), not duplicate install.
    fireEvent.click(screen.getByText('Skip'));
    expect(screen.getByText('Replace')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Replace'));
    expect(screen.getByText('Skip')).toBeInTheDocument();
  });

  it('turns conflicting skills into replace when using Select all', async () => {
    await openPreview(
      previewPayload({
        skills: [
          skillPreview({ name: 'fresh', description: 'New skill' }),
          { ...CONFLICTING_SKILL, virtual_id: 'skill:1' },
        ],
        servers: [serverPreview()],
      }),
    );

    // The fresh skill starts installed; the conflicting one starts skipped.
    expect(screen.getAllByText('Install')).toHaveLength(2);
    expect(screen.getByText('Skip')).toBeInTheDocument();

    // Select all: the conflicting skill upgrades in place (Replace) instead of creating a duplicate,
    // while the fresh skill stays a plain install. (Skills render before servers, so [0] targets them.)
    fireEvent.click(screen.getAllByText('Select all')[0]);
    expect(screen.getByText('Replace')).toBeInTheDocument();
    expect(screen.getAllByText('Install')).toHaveLength(2);
    expect(screen.queryByText('Skip')).not.toBeInTheDocument();
  });

  it('submits replace resolution for conflicting skills', async () => {
    await openPreview(
      previewPayload({ skills: [CONFLICTING_SKILL], servers: [serverPreview()] }),
      confirmResult({ imported_skills: 1 }),
    );

    // Switch from default skip to replace, then confirm.
    fireEvent.click(screen.getByText('Skip'));
    fireEvent.click(screen.getByTestId('trusted-source-checkbox'));
    fireEvent.click(screen.getByText('Import'));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenNthCalledWith(
        2,
        '/api/v1/plugins/import/confirm',
        expect.objectContaining({
          body: JSON.stringify({
            session_id: 'sess-1',
            skills: [{ component: 'skill', virtual_id: 'skill:0', name: 'summarize', resolution: 'replace' }],
            servers: [{ component: 'mcp', virtual_id: 'mcp:0', name: 'pdf-server', resolution: 'install' }],
            agents: [],
            bind_agent_id: null,
          }),
        }),
      );
    });
  });

  it('disables the Import button until trusted source checkbox is checked', async () => {
    await openPreview(PLUGIN_PREVIEW);

    const importButton = screen.getByRole('button', { name: 'Import' });
    expect(importButton).toBeDisabled();

    const checkbox = screen.getByTestId('trusted-source-checkbox');
    expect(checkbox).not.toBeChecked();

    fireEvent.click(checkbox);
    expect(checkbox).toBeChecked();
    expect(importButton).not.toBeDisabled();

    fireEvent.click(checkbox);
    expect(checkbox).not.toBeChecked();
    expect(importButton).toBeDisabled();
  });

  it('renders missing artifact warning and disables installation for broken servers', async () => {
    await openPreview(
      previewPayload({
        servers: [serverPreview({ name: 'broken-server', command: 'node', missing_artifact: 'dist/index.js' })],
        diagnostics: [
          {
            component: 'mcp:broken-server',
            code: 'mcp_missing_artifact',
            message: "MCP server 'broken-server' references entrypoint 'dist/index.js', which does not exist.",
            level: 'error',
          },
        ],
      }),
    );

    expect(screen.getAllByText(/dist\/index\.js/).length).toBeGreaterThan(0);

    // The button for the broken server should be disabled
    const installButtons = screen.getAllByRole('button', { name: /Install|Skip/ });
    const serverButton = installButtons.find((btn) => btn.closest('.divide-y')?.textContent?.includes('broken-server'));
    expect(serverButton).toBeDisabled();
  });

  it('marks server with is_runnable=false and missing_artifacts as disabled and displays error message', async () => {
    await openPreview(
      previewPayload({
        plugin: { ...previewPayload().plugin, name: 'unrunnable-plugin' },
        servers: [
          serverPreview({
            name: 'unrunnable-server',
            command: 'node',
            is_runnable: false,
            missing_artifacts: ['out/bundle.js'],
          }),
        ],
      }),
    );

    expect(screen.getAllByText(/out\/bundle\.js/).length).toBeGreaterThan(0);

    const installButtons = screen.getAllByRole('button', { name: /Install|Skip/ });
    const serverButton = installButtons.find((btn) =>
      btn.closest('.divide-y')?.textContent?.includes('unrunnable-server'),
    );
    expect(serverButton).toBeDisabled();
  });

  it('renders capability tier badges and privilege escalation warning', async () => {
    await openPreview(
      previewPayload({
        plugin: {
          ...previewPayload().plugin,
          name: 'advanced-mcp-plugin',
          version: '1.2.0',
          capabilities: ['shell_exec', 'network'],
          effective_tier: 'shell_exec',
          risk_level: 'high',
          capability_diff: { added: ['shell_exec'], removed: [], has_escalation: true },
        },
        servers: [
          serverPreview({
            name: 'shell-runner-srv',
            command: './run.sh',
            capabilities: ['shell_exec', 'fs_read'],
          }),
        ],
      }),
    );

    // Risk badge
    expect(screen.getByText('High Risk')).toBeInTheDocument();

    // Capabilities title & badges in plugin card
    expect(screen.getByText('Sandbox Capabilities:')).toBeInTheDocument();
    expect(screen.getAllByText('Shell Exec').length).toBeGreaterThan(0);
    expect(screen.getByText('Network Outbound')).toBeInTheDocument();

    // Escalation warning alert
    expect(screen.getByText('Privilege Escalation Risk Detected')).toBeInTheDocument();
    expect(screen.getByText(/added \[Shell Exec\]/)).toBeInTheDocument();

    // Server-level capability badges
    expect(screen.getByText('shell-runner-srv')).toBeInTheDocument();
    expect(screen.getByText('File Read')).toBeInTheDocument();
  });

  it('renders undeclared privilege warning on rogue mcp server', async () => {
    await openPreview(
      previewPayload({
        servers: [
          serverPreview({
            name: 'sneaky-srv',
            command: 'bash -c rm',
            capabilities: ['shell_exec', 'destructive'],
          }),
        ],
        diagnostics: [
          {
            component: 'mcp:sneaky-srv',
            code: 'capability_undeclared_privilege',
            message: "MCP server 'sneaky-srv' requires undeclared capability (destructive).",
            level: 'error',
          },
        ],
      }),
    );

    expect(
      screen.getByText(
        'Undeclared capability detected: this service requires permissions beyond what was declared in plugin.json.',
      ),
    ).toBeInTheDocument();
  });
});
