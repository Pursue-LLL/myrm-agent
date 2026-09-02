/** @vitest-environment jsdom */
'use client';

import * as React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ComposerContextChipStrip } from '../ComposerContextChipStrip';
import { ContextChipItem } from '../ContextChipItem';
import { ActiveCapabilityBadge } from '../ActiveCapabilityBadge';

const stableT = (key: string, params?: Record<string, unknown>) => {
  if (params) {
    let str = key;
    for (const [k, v] of Object.entries(params)) {
      str += `:${k}=${String(v)}`;
    }
    return str;
  }
  return key;
};

// Mock translations
vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

// Mock store states
let mockChatStore = {
  pendingExplicitSkillActivation: null as { skillNames: string[]; instruction?: string | null } | null,
  setPendingExplicitSkillActivation: vi.fn(),
  pendingWorkflowTemplateId: null as string | null,
  pendingWorkflowTemplateDisplayName: null as string | null,
  clearPendingWorkflowTemplate: vi.fn(),
  setIsWorkflowMode: vi.fn(),
};

let mockSkillStore = {
  skills: [{ id: 'skill-1' }, { id: 'skill-2' }],
};

let mockConfigStore = {
  mcpConfigs: {
    server1: { command: 'node', args: [] },
  },
};

vi.mock('@/store/useChatStore', () => ({
  default: vi.fn((selector: (s: typeof mockChatStore) => unknown) => selector(mockChatStore)),
}));

vi.mock('@/store/skill/useSkillStore', () => ({
  default: vi.fn((selector: (s: typeof mockSkillStore) => unknown) => selector(mockSkillStore)),
}));

vi.mock('@/store/useConfigStore', () => ({
  default: vi.fn((selector: (s: typeof mockConfigStore) => unknown) => selector(mockConfigStore)),
}));

vi.mock('@/lib/utils/messageUtils', () => ({
  formatSkillChipLabel: (name: string) => `Formatted:${name}`,
}));

describe('ContextChipItem', () => {
  it('renders label and handles remove and click interactions', () => {
    const onRemove = vi.fn();
    const onClick = vi.fn();

    render(
      <ContextChipItem
        id="test-1"
        label="Test Chip"
        subtitle="sub"
        onRemove={onRemove}
        onClick={onClick}
      />,
    );

    expect(screen.getByText('Test Chip')).toBeInTheDocument();
    expect(screen.getByText('sub')).toBeInTheDocument();

    const removeBtn = screen.getByTestId('context-chip-remove-test-1');
    fireEvent.click(removeBtn);
    expect(onRemove).toHaveBeenCalledTimes(1);

    const chip = screen.getByTestId('context-chip-test-1');
    fireEvent.click(chip);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('triggers remove on Backspace or Delete keydown', () => {
    const onRemove = vi.fn();
    render(<ContextChipItem id="test-2" label="Keyboard Chip" onRemove={onRemove} />);

    const chip = screen.getByTestId('context-chip-test-2');
    fireEvent.keyDown(chip, { key: 'Backspace' });
    expect(onRemove).toHaveBeenCalledTimes(1);

    fireEvent.keyDown(chip, { key: 'Delete' });
    expect(onRemove).toHaveBeenCalledTimes(2);
  });
});

describe('ActiveCapabilityBadge', () => {
  it('returns null when total active tools is zero', () => {
    const { container } = render(<ActiveCapabilityBadge skillCount={0} mcpCount={0} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders active capability count and triggers click', () => {
    const onClick = vi.fn();
    render(<ActiveCapabilityBadge skillCount={2} mcpCount={1} onClick={onClick} />);

    const badge = screen.getByTestId('active-capability-badge');
    expect(badge).toBeInTheDocument();
    expect(screen.getByText(/3/)).toBeInTheDocument();

    fireEvent.click(badge);
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});

describe('ComposerContextChipStrip', () => {
  beforeEach(() => {
    mockChatStore = {
      pendingExplicitSkillActivation: null,
      setPendingExplicitSkillActivation: vi.fn(),
      pendingWorkflowTemplateId: null,
      pendingWorkflowTemplateDisplayName: null,
      clearPendingWorkflowTemplate: vi.fn(),
      setIsWorkflowMode: vi.fn(),
    };
    mockSkillStore = {
      skills: [{ id: 'skill-1' }, { id: 'skill-2' }],
    };
    mockConfigStore = {
      mcpConfigs: {
        server1: { command: 'node', args: [] },
      },
    };
  });

  it('renders nothing when no chips are active and not overloaded', () => {
    const { container } = render(
      <ComposerContextChipStrip
        turnCapabilitySelection={null}
        onTurnCapabilityChange={vi.fn()}
      />,
    );
    expect(container.querySelector('[data-testid="composer-context-chip-strip"]')).toBeNull();
  });

  it('renders workflow template chip and handles disarm', () => {
    mockChatStore.pendingWorkflowTemplateId = 'audit-template';
    mockChatStore.pendingWorkflowTemplateDisplayName = 'Audit Template';

    render(
      <ComposerContextChipStrip
        turnCapabilitySelection={null}
        onTurnCapabilityChange={vi.fn()}
      />,
    );

    expect(screen.getByText('Audit Template')).toBeInTheDocument();
    const removeBtn = screen.getByTestId('context-chip-remove-workflow-template');
    fireEvent.click(removeBtn);

    expect(mockChatStore.clearPendingWorkflowTemplate).toHaveBeenCalledTimes(1);
    expect(mockChatStore.setIsWorkflowMode).toHaveBeenCalledWith(false);
  });

  it('renders multiple skill chips and handles atomic single skill removal', () => {
    mockChatStore.pendingExplicitSkillActivation = {
      skillNames: ['python_interpreter', 'data_visualizer'],
      instruction: 'chart instruction',
    };

    render(
      <ComposerContextChipStrip
        turnCapabilitySelection={null}
        onTurnCapabilityChange={vi.fn()}
      />,
    );

    expect(screen.getByText('Formatted:python_interpreter')).toBeInTheDocument();
    expect(screen.getByText('Formatted:data_visualizer')).toBeInTheDocument();

    const removeFirst = screen.getByTestId('context-chip-remove-skill-python_interpreter');
    fireEvent.click(removeFirst);

    expect(mockChatStore.setPendingExplicitSkillActivation).toHaveBeenCalledWith({
      skillNames: ['data_visualizer'],
      instruction: 'chart instruction',
    });
  });

  it('clears activation state when removing the last remaining skill', () => {
    mockChatStore.pendingExplicitSkillActivation = {
      skillNames: ['python_interpreter'],
    };

    render(
      <ComposerContextChipStrip
        turnCapabilitySelection={null}
        onTurnCapabilityChange={vi.fn()}
      />,
    );

    const removeSkill = screen.getByTestId('context-chip-remove-skill-python_interpreter');
    fireEvent.click(removeSkill);

    expect(mockChatStore.setPendingExplicitSkillActivation).toHaveBeenCalledWith(null);
  });

  it('renders capability scope chip and triggers reset on remove', () => {
    const onTurnCapabilityChange = vi.fn();
    render(
      <ComposerContextChipStrip
        turnCapabilitySelection={{ skillIds: ['skill-1'], mcpNames: null }}
        onTurnCapabilityChange={onTurnCapabilityChange}
      />,
    );

    const chip = screen.getByTestId('context-chip-turn-capability');
    expect(chip).toBeInTheDocument();

    const removeBtn = screen.getByTestId('context-chip-remove-turn-capability');
    fireEvent.click(removeBtn);
    expect(onTurnCapabilityChange).toHaveBeenCalledWith(null);
  });

  it('supports overflow folding when items exceed maxVisibleChips', () => {
    mockChatStore.pendingExplicitSkillActivation = {
      skillNames: ['skill-a', 'skill-b', 'skill-c', 'skill-d', 'skill-e'],
    };

    render(
      <ComposerContextChipStrip
        turnCapabilitySelection={null}
        onTurnCapabilityChange={vi.fn()}
        maxVisibleChips={3}
      />,
    );

    expect(screen.getByTestId('context-chip-overflow')).toBeInTheDocument();
    expect(screen.getByText('+2')).toBeInTheDocument();
  });
});
