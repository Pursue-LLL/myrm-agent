'use client';

/**
 * [POS] Tauri 桌面端版本更新结果反馈提示组件
 *
 * 挂载在 DeferredAppInitializers 中，冷启动时触发 useUpdateHandoff：
 * - 升级成功：弹出 Success Toast 告知用户已成功升级至最新版本
 * - 升级未生效/失败：弹出 Warning/Error Toast，提醒用户可能因权限或文件占用导致未成功，并提供手动重试
 */

import { useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';

import { isTauriRuntime } from '@/lib/deploy-mode';
import { useUpdateHandoff, type UpdateHandoffResult } from '@/hooks/tauri/useUpdateHandoff';
import { useAppUpdate } from '@/hooks/tauri/useAppUpdate';

export function UpdateHandoffNotifier() {
  const t = useTranslations('appUpdate');
  const { check } = useAppUpdate({ autoCheck: false });

  const { result, dismiss } = useUpdateHandoff();

  useEffect(() => {
    if (!isTauriRuntime() || !result) {
      return;
    }

    if (result.type === 'success') {
      toast.success(t('handoffSuccessTitle'), {
        description: t('handoffSuccessDescription', {
          version: result.currentVersion,
          fromVersion: result.fromVersion,
        }),
        duration: 6000,
      });
      dismiss();
    } else if (result.type === 'failure') {
      toast.error(t('handoffFailureTitle'), {
        description: t('handoffFailureDescription', {
          currentVersion: result.currentVersion,
          targetVersion: result.targetVersion,
        }),
        action: {
          label: t('retry'),
          onClick: () => {
            void check();
          },
        },
        duration: 10000,
      });
      dismiss();
    }
  }, [result, dismiss, check, t]);

  return null;
}
