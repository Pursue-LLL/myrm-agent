/** @vitest-environment jsdom */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { AgentConfig } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';
import useProviderStore from '@/store/useProviderStore';

// The global test setup translates a message key to itself, so copy is asserted by key.
const mocks = vi.hoisted(() => {
  /** A module whose default export renders an empty marker, so the page order can be read from the DOM. */
  const stubModule = (testId: string) => async () => {
    const { createElement } = await import('react');
    return { default: () => createElement('div', { 'data-testid': testId }) };
  };
  return {
    stubModule,
    gates: {} as Record<string, boolean>,
    resolveSmartRouting: vi.fn(),
    useChatTurnPrewarm: vi.fn(),
    messageInputProps: vi.fn(),
  };
});

// Small real stores instead of the app's: the component reacts to them exactly as it does in the app.
vi.mock('@/store/useChatStore', async () => {
  const { create } = await import('zustand');
  return { default: create(() => ({ actionMode: 'agent', agentConfig: null })) };
});
vi.mock('@/store/useProviderStore', async () => {
  const { create } = await import('zustand');
  return { default: create(() => ({ defaultModelConfig: {}, providers: [], customModelInfo: {} })) };
});
vi.mock('@/store/useFeatureGateStore', () => ({
  useFeatureGateStore: (selector: (state: { isEnabled: (featureId: string) => boolean }) => unknown) =>
    selector({ isEnabled: (featureId) => mocks.gates[featureId] === true }),
}));
vi.mock('@/lib/model-routing', () => ({
  resolveSmartRouting: (...args: unknown[]) => mocks.resolveSmartRouting(...args),
}));
vi.mock('@/hooks/chat/useChatTurnPrewarm', () => ({
  useChatTurnPrewarm: (options: unknown) => mocks.useChatTurnPrewarm(options),
}));

vi.mock('../MessageInput', async () => {
  const { createElement } = await import('react');
  return {
    default: (props: object) => {
      mocks.messageInputProps(props);
      return createElement('div', { 'data-testid': 'message-input' });
    },
  };
});
vi.mock('../playbook', async () => {
  const { createElement } = await import('react');
  return {
    ModelOrchestrationPlaybookDialog: ({ open }: { open: boolean }) =>
      createElement('div', { 'data-testid': 'playbook-dialog', 'data-open': String(open) }),
  };
});
vi.mock('../../companion/CompanionWidget', mocks.stubModule('companion-widget'));
vi.mock('../NoProviderBanner', mocks.stubModule('no-provider-banner'));
vi.mock('../IncognitoNotice', mocks.stubModule('incognito-notice'));
vi.mock('../agent-config-panel/AgentConfigPanel', mocks.stubModule('agent-config-panel'));
vi.mock('../SamplePrompts', mocks.stubModule('sample-prompts'));
vi.mock('../MigrationDiscoveryBanner', mocks.stubModule('migration-discovery-banner'));
vi.mock('../ResourcePressureBanner', mocks.stubModule('resource-pressure-banner'));
vi.mock('../UpdateNudgeBanner', mocks.stubModule('update-nudge-banner'));
vi.mock('@/components/billing/WorkUnitBalanceBar', mocks.stubModule('work-unit-balance-bar'));

import EmptyChat from '../EmptyChat';

/** Top to bottom: urgent state first, the composer, then the optional offers, then the starter prompts. */
const READING_ORDER = [
  'empty-chat-title',
  'no-provider-banner',
  'work-unit-balance-bar',
  'message-input',
  'incognito-notice',
  'resource-pressure-banner',
  'migration-discovery-banner',
  'update-nudge-banner',
  'sample-prompts',
  'agent-config-panel',
];

const INITIAL_PROVIDER_STATE = useProviderStore.getInitialState();

function expectBefore(earlier: HTMLElement, later: HTMLElement) {
  expect(earlier.compareDocumentPosition(later) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
}

describe('EmptyChat', () => {
  beforeEach(() => {
    mocks.gates = {};
    useChatStore.setState({ actionMode: 'agent', agentConfig: null });
    useProviderStore.setState(INITIAL_PROVIDER_STATE);
    mocks.resolveSmartRouting.mockReset().mockReturnValue({ active: false });
    mocks.useChatTurnPrewarm.mockReset();
    mocks.messageInputProps.mockReset();
  });

  it('shows the title and every first-screen block in reading order', () => {
    render(<EmptyChat />);

    expect(screen.getByTestId('empty-chat-title')).toHaveTextContent('researchBegins');
    const blocks = READING_ORDER.map((testId) => screen.getByTestId(testId));
    blocks.slice(1).forEach((block, index) => expectBefore(blocks[index], block));
  });

  it('adds the companion widget beside the composer only while its feature gate is on', () => {
    const closed = render(<EmptyChat />);
    expect(screen.queryByTestId('companion-widget')).toBeNull();
    closed.unmount();

    mocks.gates = { companion_mode: true };
    render(<EmptyChat />);
    expectBefore(screen.getByTestId('companion-widget'), screen.getByTestId('message-input'));
  });

  describe('smart routing', () => {
    const agentConfig: AgentConfig = {
      selectedSkillIds: [],
      selectedMcpNames: [],
      systemPrompt: '',
      useGlobalInstruction: true,
    };

    it('hands the chat and provider state to the resolver', () => {
      useChatStore.setState({ actionMode: 'fast', agentConfig });

      render(<EmptyChat />);

      const { defaultModelConfig, providers, customModelInfo } = useProviderStore.getState();
      expect(mocks.resolveSmartRouting).toHaveBeenCalledWith(
        'fast',
        agentConfig,
        defaultModelConfig,
        providers,
        customModelInfo,
      );
    });

    it('asks the resolver again when the chat mode or the providers change', () => {
      render(<EmptyChat />);
      expect(mocks.resolveSmartRouting).toHaveBeenCalledTimes(1);

      act(() => {
        useChatStore.setState({ actionMode: 'fast' });
      });
      expect(mocks.resolveSmartRouting).toHaveBeenCalledTimes(2);
      expect(mocks.resolveSmartRouting).toHaveBeenLastCalledWith(
        'fast',
        null,
        expect.anything(),
        expect.anything(),
        expect.anything(),
      );

      act(() => {
        useProviderStore.setState({ providers: [] });
      });
      expect(mocks.resolveSmartRouting).toHaveBeenCalledTimes(3);
    });

    it('offers the routing playbook only while smart routing is active', () => {
      render(<EmptyChat />);

      expect(screen.queryByTestId('smart-routing-narrative-badge')).toBeNull();
      expect(screen.getByTestId('playbook-dialog')).toHaveAttribute('data-open', 'false');
    });

    it('opens the playbook from the routing badge without asking the resolver again', () => {
      mocks.resolveSmartRouting.mockReturnValue({ active: true });
      render(<EmptyChat />);

      const badge = screen.getByTestId('smart-routing-narrative-badge');
      expect(badge).toHaveAttribute('title', 'smartRoutingBadgeClickHint');
      expect(badge).toHaveTextContent('smartRoutingBadge');
      expect(badge).toHaveTextContent('smartRoutingBadgeAction');

      fireEvent.click(badge);

      expect(screen.getByTestId('playbook-dialog')).toHaveAttribute('data-open', 'true');
      expect(mocks.resolveSmartRouting).toHaveBeenCalledTimes(1);
    });
  });

  it('prewarms the first turn when it mounts and focuses the composer', () => {
    render(<EmptyChat />);

    expect(mocks.useChatTurnPrewarm).toHaveBeenCalledWith({ autoOnMount: true });
    expect(mocks.messageInputProps).toHaveBeenCalledWith({ loading: false, focusOnMount: true });
  });
});
