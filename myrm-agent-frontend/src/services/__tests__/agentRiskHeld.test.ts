import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import en from '../../../locales/en.json';

const toastMock = vi.hoisted(() =>
  Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
);

vi.mock('@/lib/utils/toast', () => ({ toast: toastMock }));

import { setGlobalTranslator } from '@/services/i18nToastService';
import { createAgent, updateAgent } from '../agent';
import { isRiskHeldError } from '../riskHeldToast';

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

const refusalBody = {
  detail: {
    code: 'risk_held',
    message: 'Text held by a risk rule',
    rules: [{ rule_id: 'api_key_like', display_name: 'API key or cloud credential pattern', severity: 'high' }],
  },
};

function stubFetch(status: number, body: unknown): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(typeof body === 'string' ? body : JSON.stringify(body), { status })),
  );
}

describe('saving an agent profile the server holds', () => {
  beforeEach(() => {
    toastMock.error.mockClear();
    setGlobalTranslator(translatorFor(en as Messages));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it.each([
    ['create', () => createAgent({ name: 'Falcon', system_prompt: 'key sk-AAAA' })],
    ['update', () => updateAgent('agent-1', { system_prompt: 'key sk-AAAA' })],
  ])('%s shows the localized notice once and throws an error that skips the failure toast', async (_name, save) => {
    stubFetch(400, refusalBody);

    const error = await save().catch((caught: unknown) => caught);

    expect(isRiskHeldError(error)).toBe(true);
    expect((error as Error).message).toBe(en.settings.securityPolicy.riskRules.blockedTitle);
    expect(toastMock.error).toHaveBeenCalledTimes(1);
    expect(toastMock.error.mock.calls[0]?.[0]).toBe(en.settings.securityPolicy.riskRules.blockedTitle);
  });

  it('keeps the server message for any other failure and shows no notice', async () => {
    stubFetch(400, { detail: { success: false, code: 1001, message: 'Agent name is required' } });

    const error = await createAgent({ name: '' }).catch((caught: unknown) => caught);

    expect(isRiskHeldError(error)).toBe(false);
    expect((error as Error).message).toBe('Agent name is required');
    expect(toastMock.error).not.toHaveBeenCalled();
  });
});
