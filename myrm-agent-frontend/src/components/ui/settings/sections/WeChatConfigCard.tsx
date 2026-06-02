'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconWifi,
  IconWifiOff,
  IconLoader,
  IconPlus,
  IconTrash,
  IconCheck,
  IconX,
  IconPencil,
} from '@/components/ui/icons/PremiumIcons';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from 'sonner';
import {
  getWeChatStatus,
  triggerWeChatLogin,
  listChannelInstances,
  createChannelInstance,
  deleteChannelInstance,
  logoutWeChatChannel,
  updateChannelDisplayName,
} from '@/services/channels';
import type { WeChatStatus, ChannelInstance } from '@/services/channels';

export function WeChatConfigCard() {
  const t = useTranslations('channels');
  const [primaryStatus, setPrimaryStatus] = useState<WeChatStatus | null>(null);
  const [primaryLabel, setPrimaryLabel] = useState('');
  const [loading, setLoading] = useState(true);
  const [instances, setInstances] = useState<ChannelInstance[]>([]);
  const [addingInstance, setAddingInstance] = useState(false);
  const [showLabelInput, setShowLabelInput] = useState(false);
  const [newLabel, setNewLabel] = useState('');
  const labelInputRef = useRef<HTMLInputElement>(null);

  const fetchInstances = useCallback(() => {
    listChannelInstances('wechat')
      .then((all) => {
        const primary = all.find((i) => i.channelName === 'wechat');
        if (primary?.displayName) setPrimaryLabel(primary.displayName);
        setInstances(all.filter((i) => i.channelName !== 'wechat'));
      })
      .catch(() => setInstances([]));
  }, []);

  const fetchPrimaryStatus = useCallback((showLoading = false) => {
    if (showLoading) setLoading(true);
    getWeChatStatus()
      .then(setPrimaryStatus)
      .catch(() => setPrimaryStatus(null))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    fetchPrimaryStatus(true);
    fetchInstances();
  }, [fetchPrimaryStatus, fetchInstances]);

  useEffect(() => {
    const needsPolling = primaryStatus !== null && (!primaryStatus.connected || primaryStatus.qr_code);
    if (!needsPolling) return;
    const timer = setInterval(() => fetchPrimaryStatus(), 3_000);
    return () => clearInterval(timer);
  }, [primaryStatus?.connected, primaryStatus?.qr_code, fetchPrimaryStatus]);

  const handleDisplayNameChange = useCallback(
    (channelName: string, newName: string) => {
      updateChannelDisplayName(channelName, newName)
        .then((updated) => {
          if (channelName === 'wechat') {
            setPrimaryLabel(updated.displayName ?? '');
          } else {
            setInstances((prev) =>
              prev.map((i) => (i.channelName === channelName ? { ...i, displayName: updated.displayName } : i)),
            );
          }
        })
        .catch(() => toast.error(t('wechatLabelSaveError')));
    },
    [t],
  );

  const handleAddInstance = useCallback(async () => {
    setAddingInstance(true);
    try {
      const inst = await createChannelInstance('wechat', newLabel.trim() || undefined);
      setInstances((prev) => [...prev, inst]);
      toast.success(t('wechatInstanceAdded'));
      setShowLabelInput(false);
      setNewLabel('');
    } catch (error) {
      const message = error instanceof Error ? error.message : t('wechatInstanceAddError');
      toast.error(message);
    } finally {
      setAddingInstance(false);
    }
  }, [t, newLabel]);

  const handlePrimaryLogout = useCallback(async () => {
    try {
      await logoutWeChatChannel('wechat');
      setPrimaryStatus((prev) =>
        prev ? { ...prev, connected: false, qr_code: null, bot_id: null, status: 'stopped' } : prev,
      );
      toast.success(t('wechatInstanceRemoved'));
    } catch {
      toast.error(t('wechatInstanceRemoveError'));
    }
  }, [t]);

  const handleDeleteInstance = useCallback(
    async (instanceId: string) => {
      try {
        await deleteChannelInstance(instanceId);
        setInstances((prev) => prev.filter((i) => i.instanceId !== instanceId));
        toast.success(t('wechatInstanceRemoved'));
      } catch {
        toast.error(t('wechatInstanceRemoveError'));
      }
    },
    [t],
  );

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
        <IconLoader className="h-4 w-4 animate-spin" />
        <span>{t('wechatLoading')}</span>
      </div>
    );
  }

  if (!primaryStatus) {
    return <p className="text-sm text-muted-foreground py-4 text-center">{t('wechatNoChannel')}</p>;
  }

  return (
    <div className="space-y-2">
      <WeChatAccountCard
        label={primaryLabel || t('wechatDefaultLabel')}
        channelName="wechat"
        status={primaryStatus}
        onStatusChange={setPrimaryStatus}
        onDelete={handlePrimaryLogout}
        onLabelChange={(v) => handleDisplayNameChange('wechat', v)}
        t={t}
      />

      {instances.map((inst) => (
        <WeChatAccountCard
          key={inst.instanceId}
          label={inst.displayName || inst.channelName}
          channelName={inst.channelName}
          onDelete={() => handleDeleteInstance(inst.instanceId)}
          onLabelChange={(v) => handleDisplayNameChange(inst.channelName, v)}
          t={t}
        />
      ))}

      <div className="pt-1 space-y-2">
        {showLabelInput ? (
          <div className="flex items-center gap-2">
            <input
              ref={labelInputRef}
              type="text"
              value={newLabel}
              onChange={(e) => setNewLabel(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleAddInstance();
                if (e.key === 'Escape') {
                  setShowLabelInput(false);
                  setNewLabel('');
                }
              }}
              placeholder={t('wechatInstanceLabelPlaceholder')}
              className="flex-1 h-8 rounded-full border bg-background px-3 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
              maxLength={50}
              autoFocus
            />
            <Button
              variant="default"
              size="icon"
              className="h-8 w-8 shrink-0"
              onClick={handleAddInstance}
              disabled={addingInstance}
            >
              {addingInstance ? (
                <IconLoader className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <IconCheck className="h-3.5 w-3.5" />
              )}
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 shrink-0"
              onClick={() => {
                setShowLabelInput(false);
                setNewLabel('');
              }}
            >
              <IconX className="h-3.5 w-3.5" />
            </Button>
          </div>
        ) : (
          <Button
            variant="outline"
            size="sm"
            className="w-full text-xs gap-1.5"
            onClick={() => {
              setShowLabelInput(true);
              setTimeout(() => labelInputRef.current?.focus(), 50);
            }}
          >
            <IconPlus className="h-3.5 w-3.5" />
            {t('wechatAddAccount')}
          </Button>
        )}
      </div>
    </div>
  );
}

function WeChatAccountCard({
  label,
  channelName,
  status: externalStatus,
  onStatusChange,
  onDelete,
  onLabelChange,
  t,
}: {
  label: string;
  channelName: string;
  status?: WeChatStatus;
  onStatusChange?: (s: WeChatStatus) => void;
  onDelete?: () => void;
  onLabelChange?: (newLabel: string) => void;
  t: ReturnType<typeof useTranslations<'channels'>>;
}) {
  const [localStatus, setLocalStatus] = useState<WeChatStatus | null>(null);
  const [loginTriggering, setLoginTriggering] = useState(false);
  const loginTriggerTs = useRef(0);
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState('');
  const editInputRef = useRef<HTMLInputElement>(null);

  const isPrimary = channelName === 'wechat';
  const cardStatus = isPrimary ? (externalStatus ?? null) : localStatus;
  const isConnected = cardStatus?.connected ?? false;

  useEffect(() => {
    if (isPrimary) return;
    getWeChatStatus(channelName)
      .then(setLocalStatus)
      .catch(() => setLocalStatus(null));
  }, [channelName, isPrimary]);

  useEffect(() => {
    if (isPrimary) return;
    const needsPolling = localStatus !== null && (!localStatus.connected || localStatus.qr_code);
    if (!needsPolling) return;
    const timer = setInterval(() => {
      getWeChatStatus(channelName)
        .then(setLocalStatus)
        .catch(() => {});
    }, 3_000);
    return () => clearInterval(timer);
  }, [localStatus?.connected, localStatus?.qr_code, channelName, isPrimary]);

  useEffect(() => {
    if (!loginTriggering) return;
    const elapsed = Date.now() - loginTriggerTs.current;
    if (elapsed < 500) return;
    if (cardStatus?.qr_code || cardStatus?.connected) {
      setLoginTriggering(false);
    }
  }, [loginTriggering, cardStatus?.qr_code, cardStatus?.connected]);

  const handleLogin = useCallback(async () => {
    setLoginTriggering(true);
    loginTriggerTs.current = Date.now();
    try {
      await triggerWeChatLogin(channelName);
      if (!isPrimary) toast.info(t('wechatLoginTriggered'));
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

  const STATUS_I18N: Record<string, string> = {
    running: 'wechatConnected',
    stopped: 'wechatStopped',
    idle: 'wechatIdle',
    disabled: 'wechatStatusDisabled',
    degraded: 'wechatDegraded',
    error: 'wechatError',
  };
  const statusText = cardStatus?.connected
    ? t('wechatConnected')
    : t(STATUS_I18N[cardStatus?.status ?? ''] ?? 'wechatDisconnected');

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
                if (e.key === 'Enter') commitEdit();
                if (e.key === 'Escape') cancelEdit();
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
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 text-destructive/60 hover:text-destructive"
              onClick={onDelete}
            >
              <IconTrash className="h-3 w-3" />
            </Button>
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
    </div>
  );
}
