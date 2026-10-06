import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { agentPreview, confirmResult, previewPayload, serverPreview, skillPreview } from './pluginImportTestKit';
import type { PluginAgentResult } from '../pluginImportTypes';

vi.mock('next-intl', async () => {
  const kit = await import('./pluginImportTestKit');
  return { useTranslations: kit.useTranslationsStub, useLocale: () => 'en' };
});

const mockFetchAgents = vi.fn();
vi.mock('@/store/useAgentStore', () => ({
  default: () => ({ agents: [], fetchAgents: mockFetchAgents }),
}));

vi.mock('@/hooks/shared/useToast', () => ({ toast: vi.fn() }));

const { mockReadiness } = vi.hoisted(() => ({ mockReadiness: vi.fn() }));
vi.mock('@/services/agent', () => ({ getAgentReadiness: mockReadiness }));

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
  Dialog: ({ children, open }: { children: React.ReactNode; open: boolean }) => (open ? <div>{children}</div> : null),
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
  DialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
}));

vi.mock('@/components/primitives/scroll-area', () => ({
  ScrollArea: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

let fetchMock: ReturnType<typeof vi.fn>;

function agentResult(overrides: Partial<PluginAgentResult> = {}): PluginAgentResult {
  return {
    agent_id: 'agent-new',
    package_name: 'Report Lead',
    stored_name: 'Report Lead',
    action: 'created',
    previous_version_saved: false,
    withheld_tools: [],
    unresolved_skills: [],
    unresolved_connectors: [],
    unresolved_subagents: [],
    ...overrides,
  };
}

describe('PluginImportDialog - agents', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    mockFetchAgents.mockReset().mockResolvedValue(undefined);
    mockReadiness
      .mockReset()
      .mockResolvedValue({ overall_level: 'ready', items: [], agent_id: 'agent-new', checked_at: 0 });
    fetchMock = vi.fn();
    global.fetch = fetchMock as unknown as typeof fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  async function openPreview(payload: ReturnType<typeof previewPayload>, ...followUps: unknown[]) {
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => payload });
    for (const body of followUps) {
      fetchMock.mockResolvedValueOnce({ ok: true, json: async () => body });
    }
    const { default: PluginImportDialog } = await import('../PluginImportDialog');
    render(<PluginImportDialog open onOpenChange={vi.fn()} onImportComplete={vi.fn()} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(['zip'], 'plugin.zip', { type: 'application/zip' })] } });
    await screen.findByText(payload.plugin.name);
  }

  function lastConfirmBody(): Record<string, unknown> {
    const call = fetchMock.mock.calls.find(([url]) => url === '/api/v1/plugins/import/confirm');
    if (!call) {
      throw new Error('The confirm request was never sent');
    }
    return JSON.parse((call[1] as { body: string }).body) as Record<string, unknown>;
  }

  async function confirmImport() {
    fireEvent.click(screen.getByTestId('trusted-source-checkbox'));
    fireEvent.click(screen.getByText('Import'));
    await screen.findByText('Import complete');
  }

  it('lists agents with what each would be granted and what would not resolve', async () => {
    await openPreview(
      previewPayload({
        agents: [
          agentPreview({
            skill_names: ['summarize'],
            granted_tools: ['web_search'],
            withheld_tools: ['shell_exec'],
            unresolved_skills: ['missing-skill'],
            unresolved_connectors: ['missing-server'],
            unresolved_subagents: ['Ghost'],
            max_iterations: 90,
            effective_max_iterations: 30,
            recommended_model: 'claude-x',
            ignored_declarations: ['permissionMode'],
            subagent_names: ['Helper'],
          }),
          agentPreview({ name: 'Helper', virtual_id: 'agent:1', is_entry_agent: false, is_subagent: true }),
        ],
        workspace_file_count: 3,
      }),
    );

    expect(screen.getByText('Agents (2)')).toBeInTheDocument();
    expect(screen.getByText('Entry Agent')).toBeInTheDocument();
    expect(screen.getByText('Subagent')).toBeInTheDocument();
    expect(screen.getByText('1 skill(s)')).toBeInTheDocument();
    expect(screen.getByText(/1 tool\(s\)/)).toBeInTheDocument();
    expect(screen.getByText('Left off: shell_exec')).toBeInTheDocument();
    expect(screen.getByText('Skills not available: missing-skill')).toBeInTheDocument();
    expect(screen.getByText('MCP servers not available: missing-server')).toBeInTheDocument();
    expect(screen.getByText('Sub-agents missing: Ghost')).toBeInTheDocument();
    expect(screen.getByText('Loop limit lowered from 90 to 30')).toBeInTheDocument();
    expect(screen.getByText('Written for claude-x')).toBeInTheDocument();
    expect(screen.getByText('Not used: permissionMode')).toBeInTheDocument();
    expect(screen.getByText('Workspace Assets (3)')).toBeInTheDocument();
    // Both agents start installed.
    expect(screen.getAllByText('Install')).toHaveLength(2);
    expect(screen.getByText('Summary 2/0/0')).toBeInTheDocument();
  });

  it('lets the user skip agents one by one and in bulk', async () => {
    await openPreview(
      previewPayload({
        agents: [agentPreview(), agentPreview({ name: 'Helper', virtual_id: 'agent:1', is_entry_agent: false })],
      }),
    );

    fireEvent.click(screen.getAllByText('Install')[0]);
    expect(screen.getByText('Summary 1/0/0')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Skip all'));
    expect(screen.getByText('Summary 0/0/0')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Import' })).toBeDisabled();

    fireEvent.click(screen.getByText('Select all'));
    expect(screen.getByText('Summary 2/0/0')).toBeInTheDocument();
  });

  it('imports a same-name agent as a copy by default and lets the user replace it', async () => {
    await openPreview(
      previewPayload({ agents: [agentPreview({ conflict: true, existing_agent_id: 'agent-old' })] }),
      confirmResult({
        imported_agents: 1,
        agents: [agentResult({ action: 'replaced', previous_version_saved: true })],
      }),
    );

    expect(screen.getByText('An agent with this name already exists')).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Import as copy' })).toHaveAttribute('aria-checked', 'true');

    fireEvent.click(screen.getByRole('radio', { name: 'Replace' }));
    expect(screen.getByRole('radio', { name: 'Replace' })).toHaveAttribute('aria-checked', 'true');

    await confirmImport();
    expect(lastConfirmBody().agents).toEqual([
      { component: 'agent', virtual_id: 'agent:0', name: 'Report Lead', resolution: 'replace' },
    ]);
    expect(screen.getByText('Replaced')).toBeInTheDocument();
    expect(screen.getByText('The previous version was saved')).toBeInTheDocument();
  });

  it('never offers to replace a built-in agent', async () => {
    await openPreview(previewPayload({ agents: [agentPreview({ conflict: true, existing_is_built_in: true })] }));

    expect(screen.getByText('A built-in agent has this name')).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Import as copy' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Skip' })).toBeInTheDocument();
    expect(screen.queryByRole('radio', { name: 'Replace' })).not.toBeInTheDocument();
  });

  it('keeps blocked components skipped and explains why', async () => {
    await openPreview(
      previewPayload({
        skills: [skillPreview({ name: 'local-skill', blocked_reason: 'skills_not_supported' })],
        servers: [serverPreview({ name: 'stdio-server', blocked_reason: 'stdio_not_allowed' })],
        deployment: { allows_local_skills: false, allow_stdio: false },
      }),
    );

    expect(screen.getByText('Custom skills cannot be installed here')).toBeInTheDocument();
    expect(screen.getByText('Local MCP servers cannot run here')).toBeInTheDocument();
    expect(screen.getByText('This environment does not allow custom skills')).toBeInTheDocument();
    expect(screen.getByText('Local-process MCP servers cannot run in this environment')).toBeInTheDocument();
    expect(screen.getByText('Summary 0/0/0')).toBeInTheDocument();

    // "Select all" must not push blocked components back in.
    fireEvent.click(screen.getAllByText('Select all')[0]);
    fireEvent.click(screen.getAllByText('Select all')[1]);
    expect(screen.getByText('Summary 0/0/0')).toBeInTheDocument();
  });

  it('reports what was created, per-component failures, secrets to fill and readiness', async () => {
    mockReadiness.mockResolvedValue({
      overall_level: 'warning',
      agent_id: 'agent-new',
      checked_at: 0,
      items: [
        {
          dimension: 'model',
          level: 'blocked',
          reason: 'provider_not_configured',
          next_action: 'n',
          settings_path: '/settings/models',
        },
      ],
    });
    await openPreview(
      previewPayload({ agents: [agentPreview()], servers: [serverPreview()] }),
      confirmResult({
        imported_agents: 1,
        imported_servers: 1,
        required_secret_keys: ['PDF_API_KEY'],
        created_agent_ids: ['agent-new'],
        agents: [agentResult({ stored_name: 'Report Lead (imported)', withheld_tools: ['shell_exec'] })],
        failures: [
          { component: 'skill', name: 'extract', code: 'install_failed', message: 'English diagnostic for logs' },
          { component: 'mcp', name: 'odd', code: 'brand_new_code', message: 'English diagnostic for logs' },
        ],
      }),
    );

    await confirmImport();

    expect(screen.getByText('Imported 1 agents, 0 skills and 1 servers')).toBeInTheDocument();
    expect(screen.getByText('Report Lead (imported)')).toBeInTheDocument();
    expect(screen.getByText('Imported from "Report Lead"')).toBeInTheDocument();
    expect(screen.getByText('Left off: shell_exec')).toBeInTheDocument();
    expect(screen.getByText('Configure these keys: PDF_API_KEY')).toBeInTheDocument();
    expect(screen.getByText('Imported MCP servers are disabled by default')).toBeInTheDocument();

    // Failure codes are localized; unknown codes fall back to a generic sentence, never raw English.
    expect(screen.getByText('Some components were not imported')).toBeInTheDocument();
    expect(screen.getByText(/The skill could not be installed/)).toBeInTheDocument();
    expect(screen.getByText(/It could not be imported/)).toBeInTheDocument();
    expect(screen.queryByText(/English diagnostic for logs/)).not.toBeInTheDocument();

    // Readiness arrives after the result is shown, with a deep link for unresolved items.
    const link = await screen.findByRole('link', { name: 'Fix' });
    expect(link).toHaveAttribute('href', '/settings/models');
    expect(screen.getByText('Model')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open agent' })).toHaveAttribute(
      'href',
      '/settings/agents?agentId=agent-new#loadout',
    );
    await waitFor(() => expect(mockFetchAgents).toHaveBeenCalledWith(1, undefined, true));
    expect(mockReadiness).toHaveBeenCalledWith('agent-new');
  });

  it('says so when readiness cannot be checked instead of hiding the result', async () => {
    mockReadiness.mockRejectedValue(new Error('offline'));
    await openPreview(
      previewPayload({ agents: [agentPreview()] }),
      confirmResult({ imported_agents: 1, agents: [agentResult()] }),
    );

    await confirmImport();

    expect(await screen.findByText('Readiness could not be checked')).toBeInTheDocument();
    const card = screen.getByText('Report Lead').closest('.divide-y') as HTMLElement;
    expect(within(card).getByText('Open agent')).toBeInTheDocument();
  });

  it('shows a ready state when nothing needs attention', async () => {
    await openPreview(
      previewPayload({ agents: [agentPreview()] }),
      confirmResult({ imported_agents: 1, agents: [agentResult()] }),
    );

    await confirmImport();

    expect(await screen.findByText('Ready to use')).toBeInTheDocument();
  });
});
