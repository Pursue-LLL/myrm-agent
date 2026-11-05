import { act, render, screen } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { TurnCapabilitySelection } from '@/hooks/message-input/turnCapabilityOverrideCore';
import type { Message } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';

import { ComposerOptionsRegion } from '../ComposerOptionsRegion';

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'zh'));

/** The props each stand-in last received, for the controls whose wiring the region owns. */
const received = vi.hoisted(() => ({
  fork: undefined as Record<string, unknown> | undefined,
  intensity: undefined as Record<string, unknown> | undefined,
  turnCapability: undefined as Record<string, unknown> | undefined,
}));

vi.mock('@/components/features/message-input-actions/DeepSearchToggle', () => ({
  default: () => <span data-testid="deep-search" />,
}));
vi.mock('@/components/features/message-input-actions/WorkflowModeToggle', () => ({
  default: () => <span data-testid="workflow" />,
}));
vi.mock('@/components/features/message-input-actions/GoalModeToggle', () => ({
  default: () => <span data-testid="goal" />,
}));
vi.mock('@/components/features/message-input-actions/IncognitoModeToggle', () => ({
  default: () => <span data-testid="incognito" />,
}));
vi.mock('@/components/features/message-input-actions/SecurityPresetSelector', () => ({
  default: () => <span data-testid="security-preset" />,
}));
vi.mock('@/components/features/message-input-actions/FocusFlushButton', () => ({
  default: () => <span data-testid="focus-flush" />,
}));
vi.mock('@/components/features/message-input-actions/AgentIndicator', () => ({
  default: () => <span data-testid="agent-indicator" />,
}));
vi.mock('@/components/features/message-input-actions/SessionSkillsToggle', () => ({
  default: () => <span data-testid="session-skills" />,
}));
vi.mock('@/components/features/message-input-actions/KnowledgePickerPopover', () => ({
  default: () => <span data-testid="knowledge" />,
}));
vi.mock('@/components/features/message-input-actions/ToolsPanel', () => ({
  default: () => <span data-testid="tools-panel" />,
}));
vi.mock('@/components/features/message-input-actions/ThinkingIntensityButton', () => ({
  default: (props: Record<string, unknown>) => {
    received.intensity = props;
    return <span data-testid="thinking-intensity" />;
  },
}));
vi.mock('@/components/features/message-input-actions/TurnCapabilityToggle', () => ({
  default: (props: Record<string, unknown>) => {
    received.turnCapability = props;
    return <span data-testid="turn-capability" />;
  },
}));
vi.mock('../../agent-config-panel/ExpertSummonPopover', () => ({
  ExpertSummonPopover: () => <span data-testid="expert-summon" />,
}));
vi.mock('../../ForkButton', () => ({
  ForkButton: (props: Record<string, unknown>) => {
    received.fork = props;
    return <span data-testid="fork" />;
  },
}));
vi.mock('../../thinking-permission', () => ({
  ThinkingBudgetEffortSlider: () => <span data-testid="thinking-slider" />,
}));

const message = (messageId: string): Message => ({
  messageId,
  chatId: 'chat-1',
  role: 'user',
  content: 'hello',
  createdAt: new Date(),
});

const DEFAULT_PROPS: ComponentProps<typeof ComposerOptionsRegion> = {
  id: 'options-region',
  expanded: true,
  loading: false,
  turnCapabilitySelection: null,
  onTurnCapabilityChange: vi.fn(),
  turnCapabilityOpen: false,
  onTurnCapabilityOpenChange: vi.fn(),
};

/** The test ids of the controls in the row captioned `caption`, in display order. */
function controlsUnder(caption: string): string[] {
  const body = screen.getByText(caption).nextElementSibling;
  return Array.from(body?.children ?? []).map((control) => control.getAttribute('data-testid') ?? '');
}

describe('composer options region', () => {
  beforeEach(() => {
    received.fork = undefined;
    received.intensity = undefined;
    received.turnCapability = undefined;
    useChatStore.setState({ actionMode: 'agent', chatId: '', messages: [] });
  });

  it('is a labelled region that is reachable while open', () => {
    render(<ComposerOptionsRegion {...DEFAULT_PROPS} />);

    const region = screen.getByRole('region', { name: '工具栏' });
    expect(region).toHaveAttribute('id', 'options-region');
    expect(region).toHaveAttribute('data-state', 'open');
    expect(region).not.toHaveAttribute('inert');
  });

  it('takes the controls out of reach while closed, but keeps them mounted for their state and scripted clicks', () => {
    render(<ComposerOptionsRegion {...DEFAULT_PROPS} expanded={false} />);

    const region = screen.getByTestId('composer-options-region');
    expect(region).toHaveAttribute('data-state', 'closed');
    expect(region).toHaveAttribute('inert');
    expect(screen.getByTestId('incognito')).toBeInTheDocument();
    expect(screen.getByTestId('tools-panel')).toBeInTheDocument();
  });

  it('never shows on a phone, which reaches the same options through its action sheet', () => {
    render(<ComposerOptionsRegion {...DEFAULT_PROPS} />);

    const classes = screen.getByTestId('composer-options-region').className.split(/\s+/);
    expect(classes).toContain('hidden');
    expect(classes).toContain('sm:grid');
  });

  it('files every secondary control under one of three captions', () => {
    render(<ComposerOptionsRegion {...DEFAULT_PROPS} />);

    expect(controlsUnder('思考')).toEqual(['thinking-slider', 'thinking-intensity']);
    expect(controlsUnder('模式')).toEqual([
      'deep-search',
      'workflow',
      'goal',
      'incognito',
      'security-preset',
      'focus-flush',
    ]);
    expect(controlsUnder('能力')).toEqual([
      'expert-summon',
      'agent-indicator',
      'session-skills',
      'knowledge',
      'turn-capability',
      'tools-panel',
    ]);
  });

  it('offers a fork of the latest message only in a chat that has messages and is not generating', () => {
    const { rerender } = render(<ComposerOptionsRegion {...DEFAULT_PROPS} />);
    expect(screen.queryByTestId('fork')).toBeNull();

    // A chat without messages.
    act(() => useChatStore.setState({ chatId: 'chat-1', messages: [] }));
    rerender(<ComposerOptionsRegion {...DEFAULT_PROPS} />);
    expect(screen.queryByTestId('fork')).toBeNull();

    // A chat with messages, while a turn runs.
    act(() => useChatStore.setState({ chatId: 'chat-1', messages: [message('m-1'), message('m-2')] }));
    rerender(<ComposerOptionsRegion {...DEFAULT_PROPS} loading />);
    expect(screen.queryByTestId('fork')).toBeNull();

    // The same chat, idle.
    rerender(<ComposerOptionsRegion {...DEFAULT_PROPS} />);
    expect(screen.getByTestId('fork')).toBeInTheDocument();
    expect(received.fork).toEqual({ chatId: 'chat-1', messageIndex: 1 });
  });

  it('hands the turn capability picker its selection, its open state and a lock while generating', () => {
    const selection: TurnCapabilitySelection = { skillIds: ['skill-a'], mcpNames: null };
    const onChange = vi.fn();
    const onOpenChange = vi.fn();
    render(
      <ComposerOptionsRegion
        {...DEFAULT_PROPS}
        loading
        turnCapabilitySelection={selection}
        onTurnCapabilityChange={onChange}
        turnCapabilityOpen
        onTurnCapabilityOpenChange={onOpenChange}
      />,
    );

    expect(received.turnCapability).toEqual({
      selection,
      onSelectionChange: onChange,
      disabled: true,
      open: true,
      onOpenChange,
    });
  });

  it('tells the thinking button which action mode is active', () => {
    useChatStore.setState({ actionMode: 'fast' });
    render(<ComposerOptionsRegion {...DEFAULT_PROPS} />);

    expect(received.intensity).toMatchObject({ actionMode: 'fast' });
  });
});
