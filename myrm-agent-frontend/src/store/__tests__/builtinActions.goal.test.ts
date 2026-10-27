import { expectDefined } from '@/test-utils/expectDefined';
import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';

const showI18nToastMock = vi.fn();

vi.mock('@/store/useChatStore', () => ({
  default: { getState: () => ({ chatId: 'test-chat-123' }) },
}));

vi.mock('@/services/i18nToastService', () => ({
  showI18nToast: (...args: unknown[]) => showI18nToastMock(...args),
}));

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn(),
  fetchWithTimeout: vi.fn(),
}));

import { fetchWithTimeout } from '@/lib/api';
import { buildBuiltinActions } from '@/store/builtinActions';

describe('/goal control commands', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const goalAction = () => {
    const action = buildBuiltinActions().find((a) => a.name === 'goal');
    expectDefined(action, "Action 'goal'");
    return action;
  };
  const serverAnswers = (status: number, body: unknown = {}) =>
    (fetchWithTimeout as Mock).mockResolvedValue(new Response(JSON.stringify(body), { status }));

  it.each([
    ['pause', 'goalPaused', 'pause'],
    ['resume', 'goalResumed', 'resume'],
    ['clear', 'goalCleared', 'cancel'],
  ])('/goal %s reports success only after the server took the action', async (subcommand, toastKey, apiAction) => {
    serverAnswers(200, { status: 'success' });

    const result = await goalAction().execute(`/goal ${subcommand}`);

    expect(result).toEqual({ success: true, newInputValue: '' });
    expect(fetchWithTimeout).toHaveBeenCalledWith(
      '/goals/test-chat-123/status',
      expect.objectContaining({ body: JSON.stringify({ action: apiAction }) }),
    );
    expect(showI18nToastMock).toHaveBeenCalledWith(`commands.builtin.${toastKey}`, undefined, { type: 'success' });
  });

  it('/goal resume tells the user to try again in a moment when the goal is still finishing its last step', async () => {
    serverAnswers(409, { detail: 'The goal previous turn is still stopping' });

    const result = await goalAction().execute('/goal resume');

    expect(result.success).toBe(false);
    expect(showI18nToastMock).toHaveBeenCalledWith('commands.builtin.goalActionBusy', undefined, { type: 'error' });
    expect(showI18nToastMock).not.toHaveBeenCalledWith('commands.builtin.goalActionFailed', undefined, {
      type: 'error',
    });
    expect(showI18nToastMock).not.toHaveBeenCalledWith('commands.builtin.goalResumed', undefined, {
      type: 'success',
    });
  });

  it.each(['pause', 'clear'])('/goal %s keeps a conflict an ordinary failure', async (subcommand) => {
    serverAnswers(409, { detail: 'refused' });

    const result = await goalAction().execute(`/goal ${subcommand}`);

    expect(result.success).toBe(false);
    expect(showI18nToastMock).toHaveBeenCalledWith('commands.builtin.goalActionFailed', undefined, { type: 'error' });
  });

  it.each([404, 500])('/goal resume fails when the server answers HTTP %i', async (status) => {
    serverAnswers(status, { detail: 'refused' });

    const result = await goalAction().execute('/goal resume');

    expect(result.success).toBe(false);
    expect(showI18nToastMock).toHaveBeenCalledWith('commands.builtin.goalActionFailed', undefined, { type: 'error' });
    expect(showI18nToastMock).not.toHaveBeenCalledWith('commands.builtin.goalResumed', undefined, {
      type: 'success',
    });
  });

  it('/goal status fails instead of claiming there is no goal when the server errors', async () => {
    serverAnswers(500, { detail: 'boom' });

    const result = await goalAction().execute('/goal status');

    expect(result.success).toBe(false);
    expect(showI18nToastMock).toHaveBeenCalledWith('commands.builtin.goalActionFailed', undefined, { type: 'error' });
    expect(showI18nToastMock).not.toHaveBeenCalledWith('commands.builtin.goalNoActive', undefined, { type: 'info' });
  });
});
