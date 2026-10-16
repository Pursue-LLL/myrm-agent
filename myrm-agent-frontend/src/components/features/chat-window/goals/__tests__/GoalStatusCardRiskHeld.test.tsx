// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import en from '../../../../../../locales/en.json';

const { fetchMock, sendMessage, chatState, addInputHistory, sonnerToast, riskToast, stableT } = vi.hoisted(() => {
  const sendMessage = vi.fn<(content: string, ...rest: unknown[]) => Promise<boolean>>();
  return {
    stableT: (key: string) => key,
    fetchMock: vi.fn(),
    sendMessage,
    /** The open chat as the store holds it; a test changes `chatId` to open another chat. */
    chatState: {
      chatId: 'chat-1',
      agentConfig: { agentId: 'agent-1' },
      incognitoMode: false,
      inputMessage: '',
      files: [],
      pendingExplicitSkillActivation: null,
      sendMessage,
      setInputMessage: vi.fn(),
      setFiles: vi.fn(),
      setPendingExplicitSkillActivation: vi.fn(),
    },
    addInputHistory: vi.fn(),
    sonnerToast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
    riskToast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
  };
});

vi.mock('next-intl', () => ({ useTranslations: () => stableT }));
vi.mock('sonner', () => ({ toast: sonnerToast }));
vi.mock('@/lib/utils/toast', () => ({ toast: riskToast }));
vi.mock('@/lib/api', () => ({ fetchWithTimeout: fetchMock }));
vi.mock('@/services/notification', () => ({
  notificationService: { permission: 'default', requestPermission: vi.fn() },
}));
vi.mock('@/store/useChatStore', () => ({
  default: Object.assign((selector: (state: typeof chatState) => unknown) => selector(chatState), {
    getState: () => chatState,
  }),
}));
vi.mock('@/hooks/message-input/useInputHistory', () => ({ addInputHistory }));

import { setGlobalTranslator } from '@/services/i18nToastService';
import { useGoalStore } from '@/store/chat/goals/useGoalStore';
import { normalizeGoalState } from '@/store/chat/messageStream/streamHelpers';
import { GoalStatusCard } from '../GoalStatusCard';
import type { GoalStatus } from '../goalStatusTypes';

type Messages = Record<string, unknown>;

function translatorFor(messages: Messages) {
  const lookup = (key: string): string | undefined => {
    const value = key.split('.').reduce<unknown>((node, part) => (node as Messages | undefined)?.[part], messages);
    return typeof value === 'string' ? value : undefined;
  };
  return Object.assign(
    (key: string, values?: Record<string, unknown>) =>
      (lookup(key) ?? key).replace(/\{(\w+)\}/g, (_, name: string) => String(values?.[name] ?? '')),
    { has: (key: string) => lookup(key) !== undefined },
  );
}

const refusal = {
  detail: {
    code: 'risk_held',
    message: 'Text held by a risk rule',
    rules: [{ rule_id: 'api_key_like', display_name: 'API key or cloud credential pattern', severity: 'high' }],
  },
};

const jsonResponse = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });

/** Answers the card's own startup requests with an empty success and the given reply for the one under test. */
function answer(method: string, urlEnd: string, reply: () => Response): void {
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) =>
    url.endsWith(urlEnd) && init?.method === method ? reply() : jsonResponse(200, {}),
  );
}

async function openCard(status: GoalStatus = 'active'): Promise<void> {
  useGoalStore.setState({
    chatId: chatState.chatId,
    activeGoal: normalizeGoalState({
      goal_id: 'g1',
      objective: 'Ship it',
      status,
      tokens_used: 0,
      time_used_seconds: 0,
    }),
  });
  render(<GoalStatusCard />);
  fireEvent.click(await screen.findByTestId('goal-status-header'));
}

/** Opens the objective editor, types `value` and saves; returns the editor's textarea. */
function saveObjective(value: string): HTMLElement {
  fireEvent.click(screen.getByRole('button', { name: 'editObjective' }));
  const editor = screen.getByDisplayValue('Ship it');
  fireEvent.change(editor, { target: { value } });
  fireEvent.click(screen.getByRole('button', { name: 'save' }));
  return editor;
}

describe('GoalStatusCard when the server holds the text', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    chatState.chatId = 'chat-1';
    sendMessage.mockResolvedValue(true);
    setGlobalTranslator(translatorFor(en as Messages));
  });

  it('explains a held objective once and shows no failure toast of its own', async () => {
    answer('PATCH', '/goals/chat-1/objective', () => jsonResponse(400, refusal));
    await openCard();

    const editor = saveObjective('Deploy with key sk-AAAAAABBBBBBCCCCCCDDDD-0');

    await waitFor(() => expect(riskToast.error).toHaveBeenCalledTimes(1));
    expect(riskToast.error.mock.calls[0]?.[0]).toBe(en.settings.securityPolicy.riskRules.blockedTitle);
    expect(sonnerToast.error).not.toHaveBeenCalled();
    expect(editor.isConnected).toBe(true);
  });

  it('still reports any other objective failure with its own toast', async () => {
    answer('PATCH', '/goals/chat-1/objective', () => new Response('boom', { status: 500 }));
    await openCard();

    saveObjective('A new objective');

    await waitFor(() => expect(sonnerToast.error).toHaveBeenCalledWith('objectiveUpdateFailed'));
    expect(riskToast.error).not.toHaveBeenCalled();
  });

  it('explains a held sub-goal once and shows no failure toast of its own', async () => {
    answer('POST', '/goals/chat-1/subgoals', () => jsonResponse(400, refusal));
    await openCard();

    const input = screen.getByPlaceholderText('subgoalPlaceholder');
    fireEvent.change(input, { target: { value: 'use key sk-AAAAAABBBBBBCCCCCCDDDD-0' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => expect(riskToast.error).toHaveBeenCalledTimes(1));
    expect(sonnerToast.error).not.toHaveBeenCalled();
    expect(input).toHaveValue('use key sk-AAAAAABBBBBBCCCCCCDDDD-0');
  });

  it('keeps a sub-goal the server could not take in the box, whatever the reason', async () => {
    answer('POST', '/goals/chat-1/subgoals', () => jsonResponse(400, { detail: 'Goal is not active' }));
    await openCard();

    const input = screen.getByPlaceholderText('subgoalPlaceholder');
    fireEvent.change(input, { target: { value: 'write the docs' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => expect(sonnerToast.error).toHaveBeenCalledWith('subgoalAddFailed'));
    expect(input).toHaveValue('write the docs');
  });

  it('empties the box once the sub-goal was taken, and adds a text only once however often it is submitted', async () => {
    answer('POST', '/goals/chat-1/subgoals', () => jsonResponse(200, {}));
    await openCard();

    const input = screen.getByPlaceholderText('subgoalPlaceholder');
    fireEvent.change(input, { target: { value: 'write the docs' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => expect(input).toHaveValue(''));
    const added = fetchMock.mock.calls.filter(
      ([url, init]) => String(url).endsWith('/goals/chat-1/subgoals') && (init as RequestInit)?.method === 'POST',
    );
    expect(added).toHaveLength(1);
  });

  it('keeps a held review feedback in the box with the goal in review and sends nothing to the agent', async () => {
    answer('POST', '/goals/chat-1/status', () => jsonResponse(400, refusal));
    await openCard('needs_human_review');

    const input = screen.getByPlaceholderText('feedbackPlaceholder');
    fireEvent.change(input, { target: { value: 'use key sk-AAAAAABBBBBBCCCCCCDDDD-0' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => expect(riskToast.error).toHaveBeenCalledTimes(1));
    expect(sonnerToast.error).not.toHaveBeenCalled();
    expect(sendMessage).not.toHaveBeenCalled();
    expect(input).toHaveValue('use key sk-AAAAAABBBBBBCCCCCCDDDD-0');
    expect(useGoalStore.getState().activeGoal?.status).toBe('needs_human_review');
  });

  it('sends the goal back to work first and then the review feedback to the agent', async () => {
    answer('POST', '/goals/chat-1/status', () => jsonResponse(200, {}));
    await openCard('needs_human_review');

    const input = screen.getByPlaceholderText('feedbackPlaceholder');
    fireEvent.change(input, { target: { value: 'use the staging data' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => expect(sendMessage).toHaveBeenCalledTimes(1));
    // The feedback is the next message of the chat and carries none of the files staged in the composer.
    const [content, ...rest] = sendMessage.mock.calls[0];
    expect(content).toBe('use the staging data');
    expect(rest.at(-1)).toEqual({ files: [] });
    expect(useGoalStore.getState().activeGoal?.status).toBe('active');
    expect(useGoalStore.getState().activeGoal?.reason).toBeUndefined();
    const posted = fetchMock.mock.calls
      .filter(([url, init]) => String(url).endsWith('/goals/chat-1/status') && (init as RequestInit)?.method === 'POST')
      .map(([, init]) => JSON.parse(String((init as RequestInit).body)));
    expect(posted).toEqual([{ action: 'reject', note: 'use the staging data' }]);
  });

  it('neither moves the goal of another chat nor sends the feedback into it when that chat was opened meanwhile', async () => {
    answer('POST', '/goals/chat-1/status', () => {
      // What the goal sync does when the user opens chat-2 while the reject request is out.
      chatState.chatId = 'chat-2';
      useGoalStore.getState().bindChat('chat-2');
      useGoalStore.getState().setActiveGoal(
        'chat-2',
        normalizeGoalState({
          goal_id: 'g2',
          objective: 'Goal of chat 2',
          status: 'needs_human_review',
          tokens_used: 0,
          time_used_seconds: 0,
        }),
      );
      return jsonResponse(200, {});
    });
    await openCard('needs_human_review');

    const input = screen.getByPlaceholderText('feedbackPlaceholder');
    fireEvent.change(input, { target: { value: 'use the staging data' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => expect(addInputHistory).toHaveBeenCalledWith('use the staging data', 'agent-1'));
    expect(sendMessage).not.toHaveBeenCalled();
    expect(useGoalStore.getState().activeGoal).toMatchObject({
      objective: 'Goal of chat 2',
      status: 'needs_human_review',
    });
  });

  it('still reports any other sub-goal failure with its own toast', async () => {
    answer('POST', '/goals/chat-1/subgoals', () => jsonResponse(400, { detail: 'Goal is not active' }));
    await openCard();

    const input = screen.getByPlaceholderText('subgoalPlaceholder');
    fireEvent.change(input, { target: { value: 'write the docs' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => expect(sonnerToast.error).toHaveBeenCalledWith('subgoalAddFailed'));
    expect(riskToast.error).not.toHaveBeenCalled();
  });
});
