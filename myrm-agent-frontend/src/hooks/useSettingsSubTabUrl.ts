'use client';

/**
 * [INPUT] store/useSettingsDirtyStore (POS: Settings 脏数据自动保存)
 * [OUTPUT] useSettingsSubTabUrl: Center Section 子 Tab URL 同步（pathname 守卫）
 * [POS] Settings 多 Tab 容器的 URL 同步 Hook，防止 hidden Section 误触发 router.replace
 */
import { useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import useSettingsDirtyStore from '@/store/useSettingsDirtyStore';
import { toast } from 'sonner';

export function shouldSyncSettingsSubTabUrl(pathname: string, tabSlug: string): boolean {
  return pathname.endsWith(`/settings/${tabSlug}`);
}

export function buildSettingsSubTabQuery(
  currentSearch: string,
  tabValue: string,
  resolveSubParam: (value: string) => string | null,
): string {
  const params = new URLSearchParams(currentSearch);
  const sub = resolveSubParam(tabValue);
  if (sub === null) {
    params.delete('sub');
  } else {
    params.set('sub', sub);
  }
  return params.toString();
}

/**
 * Sync Settings center-section sub-tab changes to URL query `sub`,
 * only when the current pathname matches the given tab slug.
 */
export function useSettingsSubTabUrl(tabSlug: string) {
  const t = useTranslations('settings');
  const router = useRouter();

  const syncSubTabUrl = useCallback(
    (value: string, resolveSubParam: (tabValue: string) => string | null) => {
      if (!shouldSyncSettingsSubTabUrl(window.location.pathname, tabSlug)) return;

      const query = buildSettingsSubTabQuery(window.location.search, value, resolveSubParam);
      router.replace(`${window.location.pathname}?${query}`, { scroll: false });
    },
    [router, tabSlug],
  );

  const handleTabChange = useCallback(
    (value: string, setActiveTab: (tabValue: string) => void, resolveSubParam: (tabValue: string) => string | null) => {
      const store = useSettingsDirtyStore.getState();
      void store.autoSaveAll().then((ok) => {
        if (!ok) {
          toast.error(t('autoSaveFailed'));
          return;
        }
        setActiveTab(value);
        syncSubTabUrl(value, resolveSubParam);
      });
    },
    [t, syncSubTabUrl],
  );

  return { handleTabChange };
}

/** Default resolver: omit `sub` for the default tab, otherwise use tab value. */
export function defaultSubTabResolver(defaultTab: string) {
  return (value: string): string | null => (value === defaultTab ? null : value);
}
