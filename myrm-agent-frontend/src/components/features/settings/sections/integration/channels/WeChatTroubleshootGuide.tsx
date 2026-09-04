'use client';

import { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconHelpCircle,
  IconChevronDown,
  IconChevronUp,
  IconRefresh,
  IconLoader,
  IconCopy,
  IconCheck,
} from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { toast } from 'sonner';
import type { WeChatStatus } from '@/services/channels';

interface WeChatTroubleshootGuideProps {
  channelName: string;
  status: WeChatStatus | null;
  onTriggerLogin?: () => void;
  onRefreshStatus?: () => void;
  isTriggering?: boolean;
}

export function WeChatTroubleshootGuide({
  channelName,
  status,
  onTriggerLogin,
  onRefreshStatus,
  isTriggering = false,
}: WeChatTroubleshootGuideProps) {
  const t = useTranslations('channels');
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const handleToggle = useCallback(() => {
    setOpen((prev) => !prev);
  }, []);

  const handleRefresh = useCallback(async () => {
    if (!onRefreshStatus) return;
    setRefreshing(true);
    try {
      await Promise.resolve(onRefreshStatus());
      toast.success(t('wechatTroubleshootRefreshSuccess'));
    } catch {
      toast.error(t('wechatTroubleshootRefreshError'));
    } finally {
      setRefreshing(false);
    }
  }, [onRefreshStatus, t]);

  const handleCopyReport = useCallback(() => {
    const rawBotId = status?.bot_id;
    const maskedBotId = rawBotId
      ? rawBotId.length > 6
        ? `${rawBotId.slice(0, 3)}***${rawBotId.slice(-3)}`
        : '***'
      : 'none';

    const report = [
      '=== Myrm WeChat Diagnostics Report ===',
      `Channel: ${channelName}`,
      `Status: ${status?.status ?? 'unknown'}`,
      `Connected: ${status?.connected ? 'true' : 'false'}`,
      `HasQR: ${status?.qr_code ? 'true' : 'false'}`,
      `BotId: ${maskedBotId}`,
      `Timestamp: ${new Date().toISOString()}`,
    ].join('\n');

    navigator.clipboard
      .writeText(report)
      .then(() => {
        setCopied(true);
        toast.success(t('wechatTroubleshootReportCopied'));
        setTimeout(() => setCopied(false), 2000);
      })
      .catch(() => {
        toast.error(t('wechatTroubleshootReportCopyError'));
      });
  }, [channelName, status, t]);

  return (
    <div className="pt-0.5">
      <Button
        variant="ghost"
        size="sm"
        onClick={handleToggle}
        className="h-6 px-2 text-[11px] text-muted-foreground hover:text-foreground gap-1 transition-colors"
        data-testid="wechat-troubleshoot-toggle"
      >
        <IconHelpCircle className="h-3 w-3 text-muted-foreground" />
        <span>{t('wechatTroubleshootButton')}</span>
        {open ? <IconChevronUp className="h-3 w-3" /> : <IconChevronDown className="h-3 w-3" />}
      </Button>

      {open && (
        <div
          data-testid="wechat-troubleshoot-panel"
          className="mt-2 rounded-lg border bg-muted/40 p-3 text-xs space-y-3 transition-all"
        >
          <div className="font-medium text-foreground flex items-center justify-between">
            <span className="text-xs font-semibold">{t('wechatTroubleshootTitle')}</span>
            <span className="text-[10px] text-muted-foreground">Art146 Self-Diagnostic</span>
          </div>

          <div className="space-y-2 text-muted-foreground leading-relaxed">
            <div className="rounded border bg-background/80 p-2.5 space-y-1">
              <p className="font-medium text-foreground text-[11px] flex items-center gap-1.5">
                <span className="flex h-4 w-4 items-center justify-center rounded-full bg-primary/10 text-primary text-[10px] font-bold">
                  1
                </span>
                {t('wechatTroubleshootStep1Title')}
              </p>
              <p className="text-[11px] pl-5.5 text-muted-foreground/90">{t('wechatTroubleshootStep1Desc')}</p>
            </div>

            <div className="rounded border bg-background/80 p-2.5 space-y-1">
              <p className="font-medium text-foreground text-[11px] flex items-center gap-1.5">
                <span className="flex h-4 w-4 items-center justify-center rounded-full bg-primary/10 text-primary text-[10px] font-bold">
                  2
                </span>
                {t('wechatTroubleshootStep2Title')}
              </p>
              <p className="text-[11px] pl-5.5 text-muted-foreground/90">{t('wechatTroubleshootStep2Desc')}</p>
            </div>

            <div className="rounded border bg-background/80 p-2.5 space-y-1">
              <p className="font-medium text-foreground text-[11px] flex items-center gap-1.5">
                <span className="flex h-4 w-4 items-center justify-center rounded-full bg-primary/10 text-primary text-[10px] font-bold">
                  3
                </span>
                {t('wechatTroubleshootStep3Title')}
              </p>
              <p className="text-[11px] pl-5.5 text-muted-foreground/90">{t('wechatTroubleshootStep3Desc')}</p>
            </div>

            <div className="rounded border bg-background/80 p-2.5 space-y-1">
              <p className="font-medium text-foreground text-[11px] flex items-center gap-1.5">
                <span className="flex h-4 w-4 items-center justify-center rounded-full bg-primary/10 text-primary text-[10px] font-bold">
                  4
                </span>
                {t('wechatTroubleshootStep4Title')}
              </p>
              <p className="text-[11px] pl-5.5 text-muted-foreground/90">{t('wechatTroubleshootStep4Desc')}</p>
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-border/50">
            <div className="flex items-center gap-1.5">
              {onRefreshStatus && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleRefresh}
                  disabled={refreshing}
                  className="h-7 px-2.5 text-[11px] gap-1"
                >
                  <IconRefresh className={`h-3 w-3 ${refreshing ? 'animate-spin' : ''}`} />
                  <span>{t('wechatTroubleshootActionRefresh')}</span>
                </Button>
              )}
              {onTriggerLogin && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={onTriggerLogin}
                  disabled={isTriggering}
                  className="h-7 px-2.5 text-[11px] gap-1"
                >
                  {isTriggering ? <IconLoader className="h-3 w-3 animate-spin" /> : <IconRefresh className="h-3 w-3" />}
                  <span>{t('wechatTroubleshootActionReLogin')}</span>
                </Button>
              )}
            </div>

            <Button
              variant="ghost"
              size="sm"
              onClick={handleCopyReport}
              className="h-7 px-2.5 text-[11px] text-muted-foreground hover:text-foreground gap-1"
              data-testid="wechat-troubleshoot-copy-btn"
            >
              {copied ? <IconCheck className="h-3 w-3 text-green-500" /> : <IconCopy className="h-3 w-3" />}
              <span>{copied ? t('wechatTroubleshootCopied') : t('wechatTroubleshootCopyReport')}</span>
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
