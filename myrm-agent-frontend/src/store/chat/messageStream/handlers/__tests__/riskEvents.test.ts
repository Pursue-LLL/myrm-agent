import { beforeEach, describe, expect, it, vi } from 'vitest';

import en from '../../../../../../locales/en.json';
import zh from '../../../../../../locales/zh.json';
import { AgentEventType, type AgentStreamEvent } from '@/store/chat/types';
import { AdaptiveScheduler } from '../../../adaptiveScheduler';
import type { StreamHandlerActions, StreamHandlerState } from '../../types';
import type { StreamCtx } from '../../streamContext';

const toastMock = vi.hoisted(() =>
  Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
);

vi.mock('@/lib/utils/toast', () => ({ toast: toastMock }));

import { riskEvents } from '../riskEvents';
import { setGlobalTranslator } from '@/services/i18nToastService';

type Messages = Record<string, unknown>;

/** A translator over a real locale file, so the keys the handler asks for must exist there. */
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

function createCtx(type: string, data?: unknown) {
  const setLoading = vi.fn();
  const state: StreamHandlerState = {
    messages: [],
    messageAppeared: false,
    loading: true,
    scheduler: new AdaptiveScheduler(),
  };
  const actions: StreamHandlerActions = {
    setMessages: (updater) => updater(state),
    setMessageAppeared: () => undefined,
    setLoading,
    _processSuggestions: async () => undefined,
    scheduleAutoSave: () => undefined,
  };
  const ctx: StreamCtx = {
    data: { type, data } as unknown as AgentStreamEvent,
    input: '',
    sources: undefined,
    added: false,
    recievedMessage: '',
    state,
    actions,
    files: [],
  };
  return { ctx, setLoading };
}

const rule = (rule_id: string, display_name: string) => ({ rule_id, display_name, severity: 'high' });

describe('riskEvents', () => {
  beforeEach(() => {
    toastMock.error.mockClear();
    setGlobalTranslator(translatorFor(en as Messages));
  });

  it('ignores every other event', async () => {
    const { ctx } = createCtx(AgentEventType.MESSAGE_END);
    expect(await riskEvents(ctx)).toBeNull();
    expect(toastMock.error).not.toHaveBeenCalled();
  });

  it('words the notice in the user language, names the built-in rule as the settings page does, and ends the turn', async () => {
    setGlobalTranslator(translatorFor(zh as Messages));
    const { ctx, setLoading } = createCtx(AgentEventType.RISK_BLOCKED, {
      rules: [rule('api_key_like', 'API key or cloud credential pattern')],
    });

    const turn = await riskEvents(ctx);

    expect(turn).not.toBeNull();
    expect(setLoading).toHaveBeenCalledWith(false);
    expect(toastMock.error).toHaveBeenCalledWith('消息已被风控规则拦截', {
      description: '命中规则：API 密钥 / 云凭证。如需放行，请在「设置 → 安全策略 → 风控规则」中关闭对应规则。',
      duration: 10_000,
    });
  });
});
