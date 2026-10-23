/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const mockListAgents = vi.fn();
const mockGetSubagentPresets = vi.fn();

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

vi.mock('@/components/agent/builtin-agent-i18n', () => ({
  getBuiltinAgentName: (_id: string, name: string) => name,
  getBuiltinAgentDescription: (_id: string, description: string) => description,
}));

vi.mock('@/services/agent', () => ({
  listAgents: () => mockListAgents(),
  getSubagentPresets: () => mockGetSubagentPresets(),
}));

import { AgentSubagentBinding } from '../AgentSubagentBinding';
import type { SubagentPresetItem } from '@/services/agent';

const PRESETS: SubagentPresetItem[] = [
  {
    id: 'structure-planner',
    display_name: 'Structure & Outline Planner',
    description: 'Plans MECE outlines.',
    category: 'office',
    risk_level: 'low',
    required_builtin_tools: [],
  },
  {
    id: 'browser',
    display_name: 'Browser Automation Specialist',
    description: 'Navigates web pages.',
    category: 'research',
    risk_level: 'medium',
    required_builtin_tools: ['browser'],
  },
  {
    id: 'explore',
    display_name: 'Codebase Explorer',
    description: 'Read-only code search.',
    category: 'engineering',
    risk_level: 'low',
    required_builtin_tools: [],
  },
];

describe('AgentSubagentBinding', () => {
  beforeEach(() => {
    mockListAgents.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 });
    mockGetSubagentPresets.mockResolvedValue(PRESETS);
  });

  it('renders built-in preset ids instead of dropping them', async () => {
    render(<AgentSubagentBinding selectedIds={['structure-planner']} currentAgentId={null} onChange={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('subagentPresets.structure-planner.name')).toBeInTheDocument();
    });
    expect(screen.getByText('builtinSpecialistBadge')).toBeInTheDocument();
  });

  it('warns when a browser preset requires an off built-in tool', async () => {
    const onOpenBuiltinTools = vi.fn();
    render(
      <AgentSubagentBinding
        selectedIds={['browser']}
        currentAgentId={null}
        onChange={vi.fn()}
        enabledBuiltinTools={[]}
        onOpenBuiltinTools={onOpenBuiltinTools}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText('subagentMissingBuiltinTool')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'subagentEnableBuiltinTool' }));
    expect(onOpenBuiltinTools).toHaveBeenCalledTimes(1);
  });

  it('blocks adding a browser preset until its built-in tool is enabled', async () => {
    const onChange = vi.fn();
    const onOpenBuiltinTools = vi.fn();
    render(
      <AgentSubagentBinding
        selectedIds={[]}
        currentAgentId={null}
        onChange={onChange}
        enabledBuiltinTools={[]}
        onOpenBuiltinTools={onOpenBuiltinTools}
      />,
    );

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'addSubagent' })).toBeEnabled();
    });
    fireEvent.click(screen.getByRole('button', { name: 'addSubagent' }));

    await waitFor(() => {
      expect(screen.getByText('subagentPresets.browser.name')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText('subagentPresets.browser.name'));

    expect(onOpenBuiltinTools).toHaveBeenCalledTimes(1);
    expect(onChange).not.toHaveBeenCalled();
  });

  it('adds an available preset through subagent_ids', async () => {
    const onChange = vi.fn();
    render(<AgentSubagentBinding selectedIds={[]} currentAgentId={null} onChange={onChange} />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'addSubagent' })).toBeEnabled();
    });
    fireEvent.click(screen.getByRole('button', { name: 'addSubagent' }));

    await waitFor(() => {
      expect(screen.getByText('subagentPresets.explore.name')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText('subagentPresets.explore.name'));

    expect(onChange).toHaveBeenCalledWith(['explore']);
  });
});
