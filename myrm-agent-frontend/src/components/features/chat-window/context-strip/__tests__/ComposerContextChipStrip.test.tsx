/**
 * Unit tests for ComposerContextChipStrip.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { ComposerContextChipStrip } from '../ComposerContextChipStrip';
import useChatStore from '@/store/useChatStore';
import useSkillStore from '@/store/skill/useSkillStore';
import useConfigStore from '@/store/useConfigStore';

const TRANSLATIONS: Record<string, string> = {
  'chat.contextStrip.removeSkill': 'Remove skill',
  'chat.contextStrip.overloadAria': 'High tool load warning: Click to narrow active capabilities',
  'chat.contextStrip.badgeAria': '{count} active capabilities',
  'chat.contextStrip.capabilities': 'Active',
  'chat.contextStrip.activeCapabilitiesTitle': 'Turn Capability Scope',
  'chat.contextStrip.skillCountDesc': '{count} active skills',
  'chat.contextStrip.mcpCountDesc': '{count} active MCP services',
  'chat.contextStrip.overloadWarning': 'High tool count loaded',
  'chat.contextStrip.moreChipsAria': '{count} more context items',
  'chat.contextStrip.moreContextTitle': 'Mounted Context Items',
  'chat.turnCapabilities.overrideSkillsShort': '{skills} skills',
  'chat.turnCapabilities.overrideMcpShort': '{mcps} MCP',
  'chat.turnCapabilities.triggerAria': 'Turn capabilities',
  'chat.turnCapabilities.resetAria': 'Reset to default',
  'chat.workflowTemplateArmed.label': 'Pinned template',
  'chat.workflowTemplateArmed.disarm': 'Disarm',
};

const stableT = (namespace: string) => (key: string, params?: Record<string, number | string>) => {
  const fullKey = `${namespace}.${key}`;
  let template = TRANSLATIONS[fullKey] || TRANSLATIONS[key] || key;
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      template = template.replace(`{${k}}`, String(v));
    }
  }
  return template;
};

vi.mock('next-intl', () => ({
  useTranslations: (ns: string) => stableT(ns),
}));

describe('ComposerContextChipStrip', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useChatStore.setState({
      pendingExplicitSkillActivation: null,
      pendingWorkflowTemplateId: null,
      pendingWorkflowTemplateDisplayName: null,
      isWorkflowMode: false,
    });
    useSkillStore.setState({
      skills: [
        { id: 'skill-1', name: 'Skill 1', description: 'Skill 1' },
        { id: 'skill-2', name: 'Skill 2', description: 'Skill 2' },
      ],
    });
    useConfigStore.setState({
      mcpConfigs: {},
    });
  });

  it('renders only hidden toggle when no chips and not overloaded', () => {
    const { container } = render(
      <ComposerContextChipStrip
        turnCapabilitySelection={null}
        onTurnCapabilityChange={vi.fn()}
      />,
    );
    expect(screen.queryByTestId('composer-context-chip-strip')).toBeNull();
    expect(container.querySelector('[data-testid="context-chip-workflow-template"]')).toBeNull();
  });

  it('renders workflow template chip and handles disarm click', () => {
    useChatStore.setState({
      pendingWorkflowTemplateId: 'template-data-audit',
      pendingWorkflowTemplateDisplayName: 'Data Audit Template',
      isWorkflowMode: true,
    });

    render(
      <ComposerContextChipStrip
        turnCapabilitySelection={null}
        onTurnCapabilityChange={vi.fn()}
      />,
    );

    expect(screen.getByTestId('composer-context-chip-strip')).toBeInTheDocument();
    expect(screen.getByText('Data Audit Template')).toBeInTheDocument();

    const removeBtn = screen.getByTestId('context-chip-remove-workflow-template');
    fireEvent.click(removeBtn);

    expect(useChatStore.getState().pendingWorkflowTemplateId).toBeNull();
    expect(useChatStore.getState().isWorkflowMode).toBe(false);
  });

  it('renders explicit skill activation chips and supports atomic single-skill removal', () => {
    useChatStore.setState({
      pendingExplicitSkillActivation: {
        skillNames: ['python_interpreter', 'data_chart_renderer'],
        instruction: 'Generate quarterly analysis',
      },
    });

    render(
      <ComposerContextChipStrip
        turnCapabilitySelection={null}
        onTurnCapabilityChange={vi.fn()}
      />,
    );

    expect(screen.getByTestId('context-chip-skill-python_interpreter')).toBeInTheDocument();
    expect(screen.getByTestId('context-chip-skill-data_chart_renderer')).toBeInTheDocument();

    // Remove first skill atomically
    const removeFirstBtn = screen.getByTestId('context-chip-remove-skill-python_interpreter');
    fireEvent.click(removeFirstBtn);

    const pending = useChatStore.getState().pendingExplicitSkillActivation;
    expect(pending).not.toBeNull();
    expect(pending?.skillNames).toEqual(['data_chart_renderer']);
  });

  it('renders turn capability override chip and calls onTurnCapabilityChange(null) on remove', () => {
    const onTurnChange = vi.fn();

    render(
      <ComposerContextChipStrip
        turnCapabilitySelection={{ skillIds: ['skill-1'], mcpNames: null }}
        onTurnCapabilityChange={onTurnChange}
      />,
    );

    expect(screen.getByTestId('context-chip-turn-capability')).toBeInTheDocument();
    expect(screen.getByText('1 skills')).toBeInTheDocument();

    const removeBtn = screen.getByTestId('context-chip-remove-turn-capability');
    fireEvent.click(removeBtn);

    expect(onTurnChange).toHaveBeenCalledWith(null);
  });

  it('displays Amber Nudge when tool count exceeds threshold', () => {
    // Mock 16 skills to exceed overload threshold (15)
    useSkillStore.setState({
      skills: Array.from({ length: 16 }, (_, i) => ({
        id: `skill-${i}`,
        name: `Skill ${i}`,
        description: `Desc ${i}`,
      })),
    });

    render(
      <ComposerContextChipStrip
        turnCapabilitySelection={null}
        onTurnCapabilityChange={vi.fn()}
      />,
    );

    const badge = screen.getByTestId('active-capability-badge');
    expect(badge).toBeInTheDocument();
    expect(badge.className).toContain('border-amber-500');
    expect(screen.getByText('16 Active')).toBeInTheDocument();
  });

  it('supports overflow folding when chips exceed maxVisibleChips', () => {
    useChatStore.setState({
      pendingWorkflowTemplateId: 'tpl-1',
      pendingWorkflowTemplateDisplayName: 'Template 1',
      pendingExplicitSkillActivation: {
        skillNames: ['skill-a', 'skill-b', 'skill-c', 'skill-d'],
      },
    });

    render(
      <ComposerContextChipStrip
        turnCapabilitySelection={{ skillIds: ['s1'], mcpNames: null }}
        onTurnCapabilityChange={vi.fn()}
        maxVisibleChips={2}
      />,
    );

    // Total chips = 1 (template) + 4 (skills) + 1 (capability) = 6 chips.
    // With maxVisibleChips=2, overflow button should show +4
    const overflowBtn = screen.getByTestId('context-chip-overflow');
    expect(overflowBtn).toBeInTheDocument();
    expect(overflowBtn).toHaveTextContent('+4');
  });

  it('supports keyboard Delete/Backspace removal on focused chip', () => {
    useChatStore.setState({
      pendingWorkflowTemplateId: 'template-data-audit',
      pendingWorkflowTemplateDisplayName: 'Data Audit Template',
    });

    render(
      <ComposerContextChipStrip
        turnCapabilitySelection={null}
        onTurnCapabilityChange={vi.fn()}
      />,
    );

    const chip = screen.getByTestId('context-chip-workflow-template');
    fireEvent.keyDown(chip, { key: 'Backspace' });

    expect(useChatStore.getState().pendingWorkflowTemplateId).toBeNull();
  });
});
