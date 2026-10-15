/**
 * [INPUT] next-intl::useTranslations (POS: growthDashboard.growthTypes 文案)
 * [OUTPUT] useGrowthTypeLabel: 成长类型标识（技能草稿/补丁/记忆提取与各演进类型）到本地化名称，未收录的类型回落为通用名称，不向用户展示原始标识
 * [POS] features/growth 成长事件列表、提案卡片与审核审计表共享的类型名称来源
 */
'use client';

import { useCallback } from 'react';
import { useTranslations } from 'next-intl';

export function useGrowthTypeLabel(): (growthType: string) => string {
  const t = useTranslations('growthDashboard.growthTypes');
  return useCallback(
    (growthType: string) => {
      const key = growthType as Parameters<typeof t>[0];
      return t.has(key) ? t(key) : t('other');
    },
    [t],
  );
}
