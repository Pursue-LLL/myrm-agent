import { useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { isTauriRuntime } from '@/lib/deploy-mode';

/**
 * 帷幕看板文案缓存注入。
 *
 * Tauri 锁屏 watcher 自动拉帷幕时无前端调用方在场（用户已离机），
 * 看板文案由本 hook 在应用启动与 locale 变化时按当前语言预注入
 * Rust 侧缓存（i18n 单一事实源仍在 next-intl）。
 */
export function useCurtainTexts() {
  const t = useTranslations('curtain.board');

  useEffect(() => {
    if (!isTauriRuntime()) {
      return;
    }
    const texts = { primary: t('primary'), sub: t('sub'), hint: t('hint') };
    import('@tauri-apps/api/core')
      .then(({ invoke }) => invoke('curtain_set_texts', { texts }))
      .catch((error) => console.error('Failed to inject curtain texts:', error));
  }, [t]);
}
