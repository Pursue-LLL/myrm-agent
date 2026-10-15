// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import en from '../../../../../../locales/en.json';

const { fetchMock, sonnerToast, riskToast, stableT } = vi.hoisted(() => ({
  stableT: (key: string) => key,
  fetchMock: vi.fn(),
  sonnerToast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
  riskToast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}));

vi.mock('next-intl', () => ({ useTranslations: () => stableT }));
vi.mock('sonner', () => ({ toast: sonnerToast }));
vi.mock('@/lib/utils/toast', () => ({ toast: riskToast }));
vi.mock('@/lib/api', () => ({ fetchWithTimeout: fetchMock }));
vi.mock('@/services/notification', () => ({
  notificationService: { permission: 'default', requestPermission: vi.fn() },
}));
vi.mock('@/store/useChatStore', () => ({
  default: (selector: (state: { chatId: string }) => unknown) => selector({ chatId: 'chat-1' }),
}));

import { setGlobalTranslator } from '@/services/i18nToastService';
import { useGoalStore } from '@/store/chat/goals/useGoalStore';
import { normalizeGoalState } from '@/store/chat/messageStream/streamHelpers';
import { GoalStatusCard } from '../GoalStatusCard';

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

async function openCard(): Promise<void> {
  useGoalStore.setState({
    activeGoal: normalizeGoalState({
      goal_id: 'g1',
      objective: 'Ship it',
      status: 'active',
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
