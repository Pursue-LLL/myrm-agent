import { beforeEach, describe, expect, it, vi } from 'vitest';

import en from '../../../locales/en.json';
import zh from '../../../locales/zh.json';

const toastMock = vi.hoisted(() =>
  Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
);

vi.mock('@/lib/utils/toast', () => ({ toast: toastMock }));

import { setGlobalTranslator } from '@/services/i18nToastService';
import { parseRiskRules, showRiskHeldRefusal, showRiskHeldToast } from '../riskHeldToast';

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

    expect(toastMock.error).toHaveBeenCalledWith('消息已被风控规则拦截', {
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
});
