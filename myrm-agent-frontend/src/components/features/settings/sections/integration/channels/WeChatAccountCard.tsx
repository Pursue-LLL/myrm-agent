'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { useTranslations } from 'next-intl';
import {
  IconWifi,
  IconWifiOff,
  IconLoader,
  IconTrash,
  IconPencil,
} from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { ConfirmDialog } from '@/components/features/app-shell/confirm-dialog';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from 'sonner';
import { getWeChatStatus, triggerWeChatLogin } from '@/services/channels';
import type { WeChatStatus } from '@/services/channels';
import { WeChatTroubleshootGuide } from './WeChatTroubleshootGuide';

const STATUS_I18N: Record<string, string> = {
  running: 'wechatConnected',
  stopped: 'wechatStopped',
  idle: 'wechatIdle',
  disabled: 'wechatStatusDisabled',
  degraded: 'wechatDegraded',
  error: 'wechatError',
};

export interface WeChatAccountCardProps {
  label: string;
  channelName: string;
  status?: WeChatStatus | null;
  onStatusChange?: (s: WeChatStatus) => void;
  onDelete?: () => void;
  onLabelChange?: (newLabel: string) => void;
  onRefresh?: () => Promise<unknown> | void;
  t: ReturnType<typeof useTranslations<'channels'>>;
}

export function WeChatAccountCard({
  label,
  channelName,
  status: externalStatus,
  onStatusChange,
  onDelete,
  onLabelChange,
  onRefresh,
  t,
}: WeChatAccountCardProps) {
  const [localStatus, setLocalStatus] = useState<WeChatStatus | null>(null);
  const [loginTriggering, setLoginTriggering] = useState(false);
  const loginTriggerTs = useRef(0);
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState('');
  const editInputRef = useRef<HTMLInputElement>(null);

  const isPrimary = channelName === 'wechat';
  const cardStatus = isPrimary ? (externalStatus ?? null) : localStatus;
  const isConnected = cardStatus?.connected ?? false;

  const fetchLocalStatus = useCallback(() => {
    return getWeChatStatus(channelName)
      .then(setLocalStatus)
      .catch(() => setLocalStatus(null));
  }, [channelName]);

  useEffect(() => {
    if (isPrimary) {
      return;
    }
    void fetchLocalStatus();
  }, [fetchLocalStatus, isPrimary]);

  useEffect(() => {
    if (isPrimary) {
      return;
    }
    const needsPolling = localStatus !== null && (!localStatus.connected || localStatus.qr_code);
    if (!needsPolling) {
      return;
    }
    const timer = setInterval(() => {
      void getWeChatStatus(channelName)
        .then(setLocalStatus)
        .catch(() => {});
    }, 3_000);
    return () => clearInterval(timer);
  }, [localStatus, channelName, isPrimary]);

  useEffect(() => {
    if (!loginTriggering) {
      return;
    }
    const elapsed = Date.now() - loginTriggerTs.current;
    if (elapsed < 500) {
      return;
    }
    if (cardStatus?.qr_code || cardStatus?.connected) {
      setLoginTriggering(false);
    }
  }, [loginTriggering, cardStatus?.qr_code, cardStatus?.connected]);

  const handleLogin = useCallback(async () => {
    setLoginTriggering(true);
    loginTriggerTs.current = Date.now();
    try {
      await triggerWeChatLogin(channelName);
      if (!isPrimary) {
        toast.info(t('wechatLoginTriggered'));
      }
      let attempts = 0;
      const poll = setInterval(async () => {
        attempts++;
        try {
          const s = await getWeChatStatus(channelName);
          if (isPrimary) {
            onStatusChange?.(s);
          } else {
            setLocalStatus(s);
          }
          if (s.qr_code || s.connected || attempts >= 10) {
            clearInterval(poll);
          }
        } catch {
          clearInterval(poll);
        }
      }, 1_000);
    } catch {
      toast.error(t('wechatLoginError'));
      setLoginTriggering(false);
    }
  }, [channelName, isPrimary, onStatusChange, t]);

  const startEditing = useCallback(() => {
    setEditValue(label);
    setEditing(true);
    setTimeout(() => editInputRef.current?.focus(), 50);
  }, [label]);

  const commitEdit = useCallback(() => {
    const trimmed = editValue.trim();
    if (trimmed && trimmed !== label) {
      onLabelChange?.(trimmed);
    }
    setEditing(false);
  }, [editValue, label, onLabelChange]);

  const cancelEdit = useCallback(() => {
    setEditing(false);
  }, []);

  const isConnecting =
    !isConnected && !cardStatus?.qr_code && !['stopped', 'error', 'degraded'].includes(cardStatus?.status ?? 'stopped');

  const statusText = cardStatus?.connected
    ? t('wechatConnected')
    : t(STATUS_I18N[cardStatus?.status ?? ''] ?? 'wechatDisconnected');

  const handleRefresh = useCallback(() => {
    if (isPrimary && onRefresh) {
      return onRefresh();
    }
    return fetchLocalStatus();
  }, [isPrimary, onRefresh, fetchLocalStatus]);

  return (
    <div className="rounded-lg border bg-card px-4 py-2.5 text-xs space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 min-w-0">
          {isConnected ? (
            <IconWifi className="h-3.5 w-3.5 text-green-500 shrink-0" />
          ) : (
            <IconWifiOff className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
          )}
          {editing ? (
            <input
              ref={editInputRef}
              type="text"
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  commitEdit();
                }
                if (e.key === 'Escape') {
                  cancelEdit();
                }
              }}
              onBlur={commitEdit}
              className="h-5 w-28 rounded border bg-background px-1.5 text-xs font-medium focus:outline-none focus:ring-1 focus:ring-ring"
              maxLength={50}
            />
          ) : (
            <button
              type="button"
              onClick={onLabelChange ? startEditing : undefined}
              className={cn(
                'font-medium truncate max-w-[140px]',
                onLabelChange && 'group inline-flex items-center gap-1 hover:text-primary cursor-pointer',
              )}
              title={label}
            >
              {label}
              {onLabelChange && (
                <IconPencil className="h-2.5 w-2.5 opacity-0 group-hover:opacity-60 transition-opacity shrink-0" />
              )}
            </button>
          )}
          <span
            className={cn(
              'inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[9px] font-medium shrink-0',
              isConnected
                ? 'bg-green-500/10 text-green-600 dark:text-green-400 border-green-500/20'
                : isConnecting
                  ? 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20'
                  : 'bg-muted text-muted-foreground border-muted',
            )}
          >
            {isConnecting ? t('wechatWaiting') : statusText}
          </span>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <Button
            variant="ghost"
            size="sm"
            className="h-6 text-[10px] px-2"
            onClick={handleLogin}
            disabled={loginTriggering || !!cardStatus?.qr_code || cardStatus?.status === 'disabled'}
          >
            {loginTriggering ? (
              <>
                <IconLoader className="h-3 w-3 animate-spin mr-1" />
                {t('wechatLoggingIn')}
              </>
            ) : cardStatus?.qr_code ? (
              <>
                <IconLoader className="h-3 w-3 animate-spin mr-1" />
                {t('wechatWaitingScan')}
              </>
            ) : isConnected ? (
              t('wechatReLogin')
            ) : (
              t('wechatTriggerLogin')
            )}
          </Button>
          {onDelete && (
            <ConfirmDialog
              trigger={
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 text-destructive/60 hover:text-destructive"
                  aria-label={`delete-${channelName}`}
                  title={t('channelDeleteInstanceTitle')}
                >
                  <IconTrash className="h-3 w-3" />
                </Button>
              }
              title={t('channelDeleteInstanceTitle')}
              description={t('channelDeleteInstanceMessage', { name: label })}
              confirmText={t('channelDeleteInstanceConfirm')}
              cancelText={t('channelDeleteInstanceCancel')}
              variant="destructive"
              onConfirm={onDelete}
            />
          )}
        </div>
      </div>

      {cardStatus?.qr_code && (
        <div className="rounded-lg border bg-card p-3 text-center space-y-2">
          <p className="text-xs text-muted-foreground">{t('wechatScanQR')}</p>
          <div className="inline-block bg-white p-3 rounded-lg">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={cardStatus.qr_code} alt="WeChat QR Code" className="w-48 h-48" />
          </div>
          <p className="text-xs text-muted-foreground">{t('wechatQRExpiry')}</p>
        </div>
      )}

      {!isConnected &&
        !cardStatus?.qr_code &&
        cardStatus?.status !== 'disabled' &&
        ['stopped', 'error', 'degraded'].includes(cardStatus?.status ?? '') && (
          <div className="text-center py-2 space-y-2">
            <p className="text-xs text-muted-foreground">
              {cardStatus?.status === 'stopped'
                ? cardStatus?.bot_id
                  ? t('wechatDisconnectedHint')
                  : t('wechatNotConfigured')
                : t('wechatConnectionError')}
            </p>
            {cardStatus?.error && (
              <p className="text-[10px] text-destructive/80 max-w-sm mx-auto break-all">{cardStatus.error}</p>
            )}
          </div>
        )}

      {cardStatus?.bot_id && (
        <p className="text-[10px] text-muted-foreground">
          <span className="font-medium">Bot ID:</span> {cardStatus.bot_id}
        </p>
      )}

      <WeChatTroubleshootGuide
        channelName={channelName}
        status={cardStatus}
        onTriggerLogin={handleLogin}
        onRefreshStatus={handleRefresh}
        isTriggering={loginTriggering}
      />
    </div>
  );
}
