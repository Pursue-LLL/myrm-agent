/**
 * [INPUT]
 * - locales/en.json (POS: 真实语言包)
 * - @/services/i18nToastService::setGlobalTranslator (POS: 非 React 代码的通知翻译入口)
 *
 * [OUTPUT]
 * - riskHeldRefusalBody: 服务端拒绝被风控规则拦下的文字时的 HTTP 400 响应体
 * - riskHeldTitle: 该拒绝在英文界面上的通知标题
 * - installEnglishToastTranslator: 让通知服务按真实英文语言包造句
 * - jsonResponse: 带状态码的 JSON Response
 *
 * [POS]
 * 「被风控拦下的文字只提示一次」类测试共用的夹具：调用方对 `@/lib/utils/toast`（统一通知）与
 * `sonner`（调用方自己的失败提示）各放一个 mock，即可分别断言两处。
 */
import en from '../../locales/en.json';
import { setGlobalTranslator } from '@/services/i18nToastService';

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

export const riskHeldRefusalBody = {
  detail: {
    code: 'risk_held',
    message: 'Text held by a risk rule',
    rules: [{ rule_id: 'api_key_like', display_name: 'API key or cloud credential pattern', severity: 'high' }],
  },
};

export const riskHeldTitle: string = en.settings.securityPolicy.riskRules.blockedTitle;

export function installEnglishToastTranslator(): void {
  setGlobalTranslator(translatorFor(en as Messages));
}

/** 带 JSON 内容类型：`apiRequest` 只把这类成功响应当作 JSON 解析。 */
export const jsonResponse = (status: number, body: unknown): Response =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
