/**
 * Unit tests for TurnCapabilityOverrideBar.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import TurnCapabilityOverrideBar from '../TurnCapabilityOverrideBar';
import useChatStore from '@/store/useChatStore';
import useSkillStore from '@/store/skill/useSkillStore';
import useConfigStore from '@/store/useConfigStore';

const TURN_T: Record<string, string> = {
  overrideSkillsShort: '{skills} skills',
  overrideMcpShort: '{mcps} MCP',
  nextTurnOnly: 'Applies to next turn only',
  clearOverride: 'Reset to default',
  popoverTitle: 'Next Turn Capabilities',
  tooltip: 'Next turn skills & MCPs',
  skillsSection: 'Skills',
  mcpSection: 'MCP Services',
  noSkills: 'No skills',
  noMcp: 'No MCP',
  usingAgentDefaults: 'Using default configuration',
  activeCount: '{skills} skills, {mcps} MCPs active',
};

const stableT = (key: string, params?: Record<string, number | string>) => {
  let template = TURN_T[key] || key;
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      template = template.replace(`{${k}}`, String(v));
    }
  }
  return template;
};

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, params?: Record<string, number | string>) => stableT(key, params),
}));

describe('TurnCapabilityOverrideBar', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useChatStore.setState({
      actionMode: 'agent',
      agentConfig: {
        agentId: 'agent-1',
        name: 'Test Agent',
        selectedSkillIds: ['skill-a', 'skill-b'],
        selectedMcpNames: ['mcp-a'],
      },
    });
    useSkillStore.setState({
      marketSkills: [{ id: 'skill-a', name: 'Skill A', user_invocable: true }],
      localSkills: [{ id: 'skill-b', name: 'Skill B', user_invocable: true }],
    });
    useConfigStore.setState({
      mcpConfigs: [{ name: 'mcp-a', enabled: true, command: 'mcp-cmd' }],
    });
  });

  it('renders nothing when selection is null', () => {
    const onSelectionChange = vi.fn();
    const { container } = render(
      <TurnCapabilityOverrideBar selection={null} onSelectionChange={onSelectionChange} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders summary bar when selection has overrides', () => {
    const onSelectionChange = vi.fn();
    render(
      <TurnCapabilityOverrideBar
        selection={{ skillIds: ['skill-a'], mcpNames: null }}
        onSelectionChange={onSelectionChange}
      />,
    );

    expect(screen.getByTestId('turn-capability-override-bar')).toBeInTheDocument();
    expect(screen.getByText('1 skills')).toBeInTheDocument();
    expect(screen.getByText('Applies to next turn only')).toBeInTheDocument();
  });

  it('triggers onSelectionChange(null) when reset button is clicked', () => {
    const onSelectionChange = vi.fn();
    render(
      <TurnCapabilityOverrideBar
        selection={{ skillIds: ['skill-a'], mcpNames: [] }}
        onSelectionChange={onSelectionChange}
      />,
    );

    const resetBtn = screen.getByText('Reset to default');
    fireEvent.click(resetBtn);

    expect(onSelectionChange).toHaveBeenCalledWith(null);
  });
});
