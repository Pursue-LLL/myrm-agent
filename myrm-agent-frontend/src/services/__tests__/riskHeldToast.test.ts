import { beforeEach, describe, expect, it, vi } from 'vitest';

import en from '../../../locales/en.json';
import zh from '../../../locales/zh.json';

const toastMock = vi.hoisted(() =>
  Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
);

vi.mock('@/lib/utils/toast', () => ({ toast: toastMock }));

import { setGlobalTranslator } from '@/services/i18nToastService';
import { RiskBlockedError } from '@/store/chat/streamErrors';
import {
  isRiskHeldError,
  parseRiskRules,
  RiskHeldRefusalError,
  riskHeldErrorFromResponse,
  showRiskHeldRefusal,
  showRiskHeldToast,
} from '../riskHeldToast';

type Messages = Record<string, unknown>;

/** A translator over a real locale file, so the keys the notice asks for must exist there. */
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

const rule = (rule_id: string, display_name: string) => ({ rule_id, display_name, severity: 'high' });

describe('riskHeldToast', () => {
  beforeEach(() => {
    toastMock.error.mockClear();
    setGlobalTranslator(translatorFor(en as Messages));
  });

  it('words the notice in the user language and names a built-in rule as the settings page does', () => {
    setGlobalTranslator(translatorFor(zh as Messages));

    showRiskHeldToast([rule('api_key_like', 'API key or cloud credential pattern')]);

    expect(toastMock.error).toHaveBeenCalledWith('内容已被风控规则拦截', {
      description: '命中规则：API 密钥 / 云凭证。如需放行，请在「设置 → 安全策略 → 风控规则」中关闭对应规则。',
      duration: 10_000,
    });
  });

  it('keeps the own name of a custom rule, lists each rule once and names at most three', () => {
    showRiskHeldToast([
      rule('my_rule', 'Project Falcon'),
      rule('my_rule', 'Project Falcon'),
      rule('private_key_marker', 'Private key material'),
      rule('jwt_token_like', 'JWT token'),
      rule('env_file_secret', 'Environment secret variable'),
    ]);

    const [, options] = toastMock.error.mock.calls[0] as [string, { description: string }];
    expect(options.description.startsWith('Matched: Project Falcon / ')).toBe(true);
    expect(options.description.split(' / ')).toHaveLength(3);
  });

  it('keeps the own name of a custom rule whose id is an Object member, whatever the translator says', () => {
    const lookup = translatorFor(en as Messages);
    setGlobalTranslator(
      Object.assign((key: string, values?: Record<string, unknown>) => lookup(key, values), { has: () => true }),
    );

    showRiskHeldToast([rule('constructor', 'Project Falcon')]);

    const [, options] = toastMock.error.mock.calls[0] as [string, { description: string }];
    expect(options.description.startsWith('Matched: Project Falcon.')).toBe(true);
  });

  it('reads only well-formed rules from a payload', () => {
    expect(parseRiskRules([rule('a', 'A'), { rule_id: 'b' }, null, 'c'])).toEqual([rule('a', 'A')]);
    expect(parseRiskRules(undefined)).toEqual([]);
    expect(parseRiskRules({ rule_id: 'a', display_name: 'A' })).toEqual([]);
  });

  it('shows the notice for a risk-held refusal body and says so', () => {
    const shown = showRiskHeldRefusal({
      code: 'risk_held',
      message: 'Text held by a risk rule',
      rules: [rule('jwt_token_like', 'JWT token')],
    });

    expect(shown).toBe(true);
    expect(toastMock.error).toHaveBeenCalledTimes(1);
    const [title, options] = toastMock.error.mock.calls[0] as [string, { description: string }];
    expect(title).toBe(en.settings.securityPolicy.riskRules.blockedTitle);
    expect(options.description.startsWith('Matched: ')).toBe(true);
  });

  it.each([
    ['another error code', { code: 'quota_exceeded', rules: [rule('a', 'A')] }],
    ['a string detail', 'Text held by a risk rule'],
    ['no detail', undefined],
    ['a null detail', null],
  ])('leaves %s to the generic error toast', (_name, detail) => {
    expect(showRiskHeldRefusal(detail)).toBe(false);
    expect(toastMock.error).not.toHaveBeenCalled();
  });

  describe('for a failed fetch that did not go through apiRequest', () => {
    const refusal = {
      detail: { code: 'risk_held', message: 'Text held by a risk rule', rules: [rule('jwt_token_like', 'JWT token')] },
    };
    const respond = (status: number, body: string) => new Response(body, { status });

    it('shows the notice once and returns an error carrying the neutral title, not the server text', async () => {
      const response = respond(400, JSON.stringify(refusal));

      const error = await riskHeldErrorFromResponse(response);

      expect(error).toBeInstanceOf(RiskHeldRefusalError);
      expect(error?.message).toBe(en.settings.securityPolicy.riskRules.blockedTitle);
      expect(error?.message).not.toContain('held by a risk rule');
      expect(isRiskHeldError(error)).toBe(true);
      expect(toastMock.error).toHaveBeenCalledTimes(1);
    });

    it('leaves the body readable for the caller', async () => {
      const response = respond(400, JSON.stringify(refusal));

      await riskHeldErrorFromResponse(response);

      expect(await response.json()).toEqual(refusal);
    });

    it.each([
      ['another 400 body', 400, JSON.stringify({ detail: { code: 'model_not_configured' } })],
      ['a string detail', 400, JSON.stringify({ detail: 'Bad input' })],
      ['a body that is not JSON', 400, 'Bad Request'],
      ['a refusal body under another status', 500, JSON.stringify(refusal)],
    ])('returns null without a notice for %s', async (_name, status, body) => {
      const response = respond(status, body);

      expect(await riskHeldErrorFromResponse(response)).toBeNull();
      expect(toastMock.error).not.toHaveBeenCalled();
      expect(await response.text()).toBe(body);
    });
  });

  describe('isRiskHeldError', () => {
    it('recognises an error whose data is a risk-held refusal, as apiRequest throws it', () => {
      const apiError = Object.assign(new Error('Text held by a risk rule'), {
        data: { code: 'risk_held', rules: [] },
      });

      expect(isRiskHeldError(apiError)).toBe(true);
    });

    it('recognises the chat stream refusal, whose notice the risk event has already shown', () => {
      expect(isRiskHeldError(new RiskBlockedError())).toBe(true);
    });

    it.each([
      ['a plain error', new Error('boom')],
      ['an error with another code', Object.assign(new Error('x'), { data: { code: 'quota_exceeded' } })],
      ['a non-error value', { data: { code: 'risk_held' } }],
      ['undefined', undefined],
    ])('does not take %s for one', (_name, value) => {
      expect(isRiskHeldError(value)).toBe(false);
    });
  });
});
