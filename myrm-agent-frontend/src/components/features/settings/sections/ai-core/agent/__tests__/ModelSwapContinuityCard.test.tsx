/** @vitest-environment jsdom */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ModelSwapContinuityCard } from '../ModelSwapContinuityCard';
import type { AgentCapabilitiesTabProps } from '../AgentCapabilitiesTab';

const stableT = (key: string, params?: Record<string, unknown>) => {
  if (params) {
    let str = key;
    for (const [k, v] of Object.entries(params)) {
      str += `:${k}=${v}`;
    }
    return str;
  }
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/services/llm-config', () => ({
  fetchModelCapabilitiesBatch: vi.fn().mockResolvedValue({
    'claude-3-5-sonnet': {
      supports_vision: true,
      supports_function_calling: true,
      supports_reasoning: false,
      max_input_tokens: 200000,
    },
    'deepseek-chat': {
      supports_vision: false,
      supports_function_calling: true,
      supports_reasoning: false,
      max_input_tokens: 64000,
    },
  }),
}));

describe('ModelSwapContinuityCard', () => {
  const mockEditor: AgentCapabilitiesTabProps['editor'] = {
    modelSelection: { providerId: 'anthropic', model: 'claude-3-5-sonnet' },
    setModelSelection: vi.fn(),
    maxIterations: 100,
    setMaxIterations: vi.fn(),
    workspacePolicy: {
      mode: 'safe_read_write',
      read_write_roots: [],
      writable_workspaces: [],
      command_policy: 'whitelist_only',
      allowed_commands: [],
      denied_commands: [],
      network_policy: 'allow_outbound',
      allowed_domains: [],
      denied_domains: [],
      isolation_level: 'process',
      allow_subprocesses: true,
      allow_background_daemons: false,
      max_memory_mb: 2048,
      max_cpu_cores: 2,
    },
    setWorkspacePolicy: vi.fn(),
    engineParams: null,
    setEngineParams: vi.fn(),
    sessionPolicy: null,
    setSessionPolicy: vi.fn(),
    cronPostRunVerify: false,
    setCronPostRunVerify: vi.fn(),
    busyInputMode: 'steer',
    setBusyInputMode: vi.fn(),
    selectedSkillDetails: [{ id: 'skill-1', name: 'GitOps Skill' }] as any,
    selectedMcpDetails: [{ id: 'mcp-1', name: 'Postgres MCP' }] as any,
    systemPrompt: 'test prompt',
    useGlobalInstruction: true,
    enabledBuiltinTools: ['read_file', 'write_file'],
    isReadonly: false,
    saveVersion: 1,
    setEditDialogType: vi.fn(),
    setEditDialogOpen: vi.fn(),
    openapiServices: [],
    setOpenapiServices: vi.fn(),
    selectedSubagentIds: ['subagent-1'],
    setSelectedSubagentIds: vi.fn(),
    subagentRebindHint: false,
    dismissSubagentRebindHint: vi.fn(),
    notifyTargets: [],
    setNotifyTargets: vi.fn(),
    setBrowserSource: vi.fn(),
    setDialogPolicy: vi.fn(),
    setSessionRecording: vi.fn(),
  };

  it('renders preserved asset continuity badges correctly', () => {
    render(<ModelSwapContinuityCard editor={mockEditor} effectiveModelSlug="claude-3-5-sonnet" />);

    expect(screen.getByText('title')).toBeInTheDocument();
    expect(screen.getByText('assetSkills:count=1')).toBeInTheDocument();
    expect(screen.getByText('assetMcp:count=1')).toBeInTheDocument();
    expect(screen.getByText('assetMemory')).toBeInTheDocument();
    expect(screen.getByText('assetWorkspace')).toBeInTheDocument();
    expect(screen.getByText('assetSubagents:count=1')).toBeInTheDocument();
  });

  it('toggles expansion and shows model family discipline for Claude', async () => {
    render(<ModelSwapContinuityCard editor={mockEditor} effectiveModelSlug="claude-3-5-sonnet" />);

    const toggleBtn = screen.getByRole('button', { name: /expandDetails/i });
    fireEvent.click(toggleBtn);

    expect(screen.getByText('disciplineTitle:family=Claude')).toBeInTheDocument();
    expect(screen.getByText('recommendedPromptMode:mode=Full')).toBeInTheDocument();
    expect(screen.getByText('disciplineClaude')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('visionNative')).toBeInTheDocument();
    });
  });

  it('displays vision fallback indicator when model lacks vision support', async () => {
    render(<ModelSwapContinuityCard editor={mockEditor} effectiveModelSlug="deepseek-chat" />);

    const toggleBtn = screen.getByRole('button', { name: /expandDetails/i });
    fireEvent.click(toggleBtn);

    expect(screen.getByText('disciplineTitle:family=DeepSeek')).toBeInTheDocument();
    expect(screen.getByText('recommendedPromptMode:mode=Lean / Full')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('visionFallbackActive')).toBeInTheDocument();
    });
  });
});
