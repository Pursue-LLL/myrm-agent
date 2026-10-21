'use client';

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconAlertTriangle,
  IconChevronDown,
  IconChevronUp,
  IconShieldCheck,
  IconExternalLink,
} from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';

const STORAGE_KEY = 'myrm_wechat_risk_banner_dismissed';

interface WeChatRiskDisclosureBannerProps {
  onNavigateToWeCom?: () => void;
}

export function WeChatRiskDisclosureBanner({ onNavigateToWeCom }: WeChatRiskDisclosureBannerProps) {
  const t = useTranslations('channels');
  const [dismissed, setDismissed] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved === '1') {
        setDismissed(true);
      }
    } catch {
      // 容错：无可用 localStorage 时默认保持展示
    }
  }, []);

  const handleDismiss = useCallback(() => {
    setDismissed(true);
    try {
      localStorage.setItem(STORAGE_KEY, '1');
    } catch {
      // 忽略存储失败
    }
  }, []);

  const handleExpand = useCallback(() => {
    setDismissed(false);
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // 忽略存储失败
    }
  }, []);

  if (!mounted) {
    return null;
  }

  if (dismissed) {
    return (
      <div
        data-testid="wechat-risk-banner-compact"
        className="flex items-center justify-between rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-xs text-amber-700 dark:text-amber-400 transition-colors"
      >
        <div className="flex items-center gap-2 min-w-0">
          <IconAlertTriangle className="h-3.5 w-3.5 shrink-0 text-amber-600 dark:text-amber-400" />
          <span className="truncate">{t('wechatRiskBannerCompactTitle')}</span>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={handleExpand}
          className="h-6 px-2 text-[11px] text-amber-700 hover:text-amber-800 dark:text-amber-300 dark:hover:text-amber-200 shrink-0 gap-1"
        >
          <span>{t('wechatRiskBannerExpand')}</span>
          <IconChevronDown className="h-3 w-3" />
        </Button>
      </div>
    );
  }

  return (
    <div
      data-testid="wechat-risk-banner-full"
      className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3.5 text-xs text-amber-900 dark:text-amber-200 space-y-2.5 transition-all"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 font-medium text-amber-800 dark:text-amber-300">
          <IconAlertTriangle className="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
          <span className="text-sm">{t('wechatRiskBannerTitle')}</span>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={handleDismiss}
          className="h-6 w-6 p-0 text-amber-700 hover:text-amber-800 dark:text-amber-400 dark:hover:text-amber-200 shrink-0"
          aria-label={t('wechatRiskBannerDismiss')}
        >
          <IconChevronUp className="h-3.5 w-3.5" />
        </Button>
      </div>

      <p className="text-xs leading-relaxed text-amber-800/90 dark:text-amber-300/90">{t('wechatRiskBannerDesc')}</p>

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 pt-1 border-t border-amber-500/20">
        <div className="flex items-center gap-1.5 text-[11px] text-amber-700 dark:text-amber-300">
          <IconShieldCheck className="h-3.5 w-3.5 shrink-0 text-green-600 dark:text-green-400" />
          <span>{t('wechatRiskBannerWeComHint')}</span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {onNavigateToWeCom && (
            <Button
              variant="outline"
              size="sm"
              onClick={onNavigateToWeCom}
              className="h-6 px-2.5 text-[11px] border-amber-500/30 bg-amber-500/5 hover:bg-amber-500/20 text-amber-800 dark:text-amber-200 gap-1"
            >
              <span>{t('wechatRiskBannerWeComAction')}</span>
              <IconExternalLink className="h-3 w-3" />
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={handleDismiss}
            className="h-6 px-2.5 text-[11px] text-amber-700 hover:text-amber-800 dark:text-amber-400 dark:hover:text-amber-200"
          >
            {t('wechatRiskBannerDismiss')}
          </Button>
        </div>
      </div>
    </div>
  );
}
