/**
 * [INPUT]
 * - lib/utils/localeUtils.ts (POS: App locale 解析与营销接力工具)
 * - store/useConfigStore.ts (POS: 用户个人设置与云同步)
 *
 * [OUTPUT]
 * - persistLocaleToPersonalSettings(): 将前端 locale 写入 personalSettings（与 LanguageSwitcher 同源）
 * - syncCookieLocaleToPersonalSettings(): 登录/OAuth 后将 NEXT_LOCALE cookie 同步到 personalSettings
 *
 * [POS]
 * 对齐 messageRequest 的 personalSettings.locale 优先级，避免营销漏斗 UI 语言与 Agent 回复语言分裂。
 */
import useConfigStore from '@/store/useConfigStore';
import { getClientLocale, normalizeLocaleForBackend } from '@/lib/utils/localeUtils';

export async function persistLocaleToPersonalSettings(
  frontendLocale: string | null,
): Promise<void> {
  const backendLocale = normalizeLocaleForBackend(frontendLocale);
  if (!backendLocale) return;

  const { personalSettings, updatePersonalSettings } = useConfigStore.getState();
  if (personalSettings?.locale === backendLocale) return;

  await updatePersonalSettings({ locale: backendLocale });
}

/** After marketing middleware sets NEXT_LOCALE, persist it for agent message locale. */
export async function syncCookieLocaleToPersonalSettings(): Promise<void> {
  await persistLocaleToPersonalSettings(getClientLocale());
}
