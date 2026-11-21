import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { TurnCapabilitySelection } from '@/hooks/message-input/turnCapabilityOverrideCore';
import { useTurnCapabilitySelection } from '@/hooks/message-input/useTurnCapabilitySelection';
import type { AgentConfig } from '@/store/chat/types';

const SELECTION: TurnCapabilitySelection = { skillIds: ['skill-b'], mcpNames: null };

interface Scope {
  chatId: string | undefined;
  agentConfig: AgentConfig | null;
}

function agent(overrides: Partial<AgentConfig> = {}): AgentConfig {
  return {
    selectedSkillIds: ['skill-a', 'skill-b'],
    selectedMcpNames: ['mcp-a'],
    systemPrompt: '',
    useGlobalInstruction: true,
    agentId: 'agent-1',
    ...overrides,
  };
}

const FIRST_SCOPE: Scope = { chatId: 'chat-1', agentConfig: agent() };

/** Renders the hook and records, for every render, which chat it was for and what selection it showed. */
function renderSelection() {
  const renders: Array<{ chatId: string | undefined; selection: TurnCapabilitySelection | null }> = [];
  const hook = renderHook(
    (scope: Scope) => {
      const value = useTurnCapabilitySelection(scope.chatId, scope.agentConfig);
      renders.push({ chatId: scope.chatId, selection: value.turnCapabilitySelection });
      return value;
    },
    { initialProps: FIRST_SCOPE },
  );
  return { ...hook, renders };
}

describe('useTurnCapabilitySelection', () => {
  it('starts without a selection', () => {
    const { result } = renderSelection();

    expect(result.current.turnCapabilitySelection).toBeNull();
    expect(result.current.consumeTurnCapabilitySelection()).toBeNull();
  });

  it('holds a selection until it is consumed, and hands it over only once', () => {
    const { result } = renderSelection();
    act(() => result.current.setTurnCapabilitySelection(SELECTION));
    expect(result.current.turnCapabilitySelection).toEqual(SELECTION);

    let consumed: TurnCapabilitySelection | null = null;
    act(() => {
      consumed = result.current.consumeTurnCapabilitySelection();
    });

    expect(consumed).toEqual(SELECTION);
    expect(result.current.turnCapabilitySelection).toBeNull();
    expect(result.current.consumeTurnCapabilitySelection()).toBeNull();
  });

  it.each<[string, Scope]>([
    ['the chat changes', { chatId: 'chat-2', agentConfig: agent() }],
    ['the chat is gone', { chatId: undefined, agentConfig: agent() }],
    ['the agent changes', { chatId: 'chat-1', agentConfig: agent({ agentId: 'agent-2' }) }],
    ['the agent skill list changes', { chatId: 'chat-1', agentConfig: agent({ selectedSkillIds: ['skill-a'] }) }],
    ['the agent MCP list changes', { chatId: 'chat-1', agentConfig: agent({ selectedMcpNames: [] }) }],
    ['the agent config is gone', { chatId: 'chat-1', agentConfig: null }],
  ])('drops the selection when %s', (_reason, nextScope) => {
    const { result, rerender } = renderSelection();
    act(() => result.current.setTurnCapabilitySelection(SELECTION));

    rerender(nextScope);

    expect(result.current.turnCapabilitySelection).toBeNull();
  });

  it('keeps the selection when the agent config is rebuilt with the same contents', () => {
    const { result, rerender } = renderSelection();
    act(() => result.current.setTurnCapabilitySelection(SELECTION));

    rerender({ chatId: 'chat-1', agentConfig: agent() });

    expect(result.current.turnCapabilitySelection).toEqual(SELECTION);
  });

  it('never shows the selection of the old chat to a render of the new one', () => {
    const { result, rerender, renders } = renderSelection();
    act(() => result.current.setTurnCapabilitySelection(SELECTION));

    rerender({ chatId: 'chat-2', agentConfig: agent() });

    const newChatRenders = renders.filter((render) => render.chatId === 'chat-2');
    expect(newChatRenders.length).toBeGreaterThan(0);
    expect(newChatRenders.every((render) => render.selection === null)).toBe(true);
  });

  it('does not bring the selection back when the old chat is shown again', () => {
    const { result, rerender } = renderSelection();
    act(() => result.current.setTurnCapabilitySelection(SELECTION));

    rerender({ chatId: 'chat-2', agentConfig: agent() });
    rerender(FIRST_SCOPE);

    expect(result.current.turnCapabilitySelection).toBeNull();
  });

  it('ignores a selection set through a setter that belongs to a scope that has been left', () => {
    const { result, rerender } = renderSelection();
    const settersOfFirstChat = result.current.setTurnCapabilitySelection;
    rerender({ chatId: 'chat-2', agentConfig: agent() });

    act(() => settersOfFirstChat(SELECTION));

    expect(result.current.turnCapabilitySelection).toBeNull();
  });
});
