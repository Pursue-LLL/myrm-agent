import { act, render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { AgentConfig } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';

import { FlowPadModal } from '../flow-pad-modal';

const kit = vi.hoisted(() => ({ renders: 0 }));

/** The modal calls its draft hook once per render, so the count of calls is the count of renders. */
vi.mock('../useFlowPadDraft', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../useFlowPadDraft')>();
  return {
    ...actual,
    useFlowPadDraft: (...args: Parameters<typeof actual.useFlowPadDraft>) => {
      kit.renders += 1;
      return actual.useFlowPadDraft(...args);
    },
  };
});

const agentNamed = (agentName: string): AgentConfig => ({
  selectedSkillIds: [],
  selectedMcpNames: [],
  systemPrompt: '',
  useGlobalInstruction: true,
  agentName,
});

beforeEach(() => {
  kit.renders = 0;
  useChatStore.setState({ agentConfig: agentNamed('General'), inputMessage: '', messages: [] });
});

/** The pad is mounted for the whole app session and is closed nearly all the time. */
function renderSettledPad() {
  render(<FlowPadModal />);
  const settled = kit.renders;
  return () => kit.renders - settled;
}

describe('FlowPadModal re-rendering while the pad is closed', () => {
  it('stays put while the user types or a reply streams in, none of which it shows', () => {
    const rendersSince = renderSettledPad();

    // One update per act(), like keystrokes and stream chunks that arrive in separate frames.
    for (let keystroke = 1; keystroke <= 25; keystroke += 1) {
      act(() => useChatStore.setState({ inputMessage: 'x'.repeat(keystroke) }));
    }
    for (let chunk = 1; chunk <= 25; chunk += 1) {
      act(() => useChatStore.setState({ messages: [] }));
    }

    expect(rendersSince()).toBe(0);
  });

  it('redraws when the agent behind the chat changes', () => {
    const rendersSince = renderSettledPad();

    act(() => useChatStore.setState({ agentConfig: agentNamed('Writer') }));

    expect(rendersSince()).toBeGreaterThan(0);
  });
});
