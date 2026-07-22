/**
 * [INPUT]
 * ./builtin-agent-i18n-data::BUILTIN_AGENT_I18N (POS: 内置智能体 i18n 数据 SSOT)
 *
 * [OUTPUT]
 * getBuiltinAgentName: 根据 agent ID 和 locale 获取本地化名称
 * getBuiltinAgentDescription: 根据 agent ID 和 locale 获取本地化描述
 *
 * [POS]
 * 内置智能体国际化解析层。数据见 builtin-agent-i18n-data.ts。
 */

import { BUILTIN_AGENT_I18N } from './builtin-agent-i18n-data';

type SupportedLocale = 'en' | 'zh' | 'zh-TW' | 'ja' | 'ko' | 'de';

function resolveLocale(locale: string): SupportedLocale {
  if (locale === 'zh-TW' || locale === 'zh-Hant') return 'zh-TW';
  if (locale.startsWith('zh')) return 'zh';
  if (locale.startsWith('ja')) return 'ja';
  if (locale.startsWith('ko')) return 'ko';
  if (locale.startsWith('de')) return 'de';
  return 'en';
}

export function getBuiltinAgentName(agentId: string, agentName: string, locale: string): string {
  const entry = BUILTIN_AGENT_I18N[agentId];
  if (!entry) return agentName;
  return entry[resolveLocale(locale)]?.name ?? agentName;
}

export function getBuiltinAgentDescription(agentId: string, agentDescription: string, locale: string): string {
  const entry = BUILTIN_AGENT_I18N[agentId];
  if (!entry) return agentDescription;
  return entry[resolveLocale(locale)]?.description ?? agentDescription;
}
