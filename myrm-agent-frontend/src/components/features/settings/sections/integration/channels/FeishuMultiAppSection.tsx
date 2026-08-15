'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconPlus,
  IconTrash,
  IconPencil,
  IconLoader,
  IconWifi,
  IconWifiOff,
  IconKey,
} from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { ConfirmDialog } from '@/components/features/app-shell/confirm-dialog';
import { cn } from '@/lib/utils/classnameUtils';
import { getChannelInstanceMeta, listChannelStatuses, type ChannelStatus } from '@/services/channels';
import { useChannelInstances } from '@/hooks/channels/useChannelInstances';
import { FeishuQrRegisterDialog } from './FeishuQrRegisterDialog';
import { FeishuCredentialsEditDialog } from './FeishuCredentialsEditDialog';

export function FeishuMultiAppSection() {
  const t = useTranslations('channels');
  const [statuses, setStatuses] = useState<ChannelStatus[]>([]);
  const [maxInstances, setMaxInstances] = useState(0);
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [editChannelName, setEditChannelName] = useState<string | null>(null);

  const { instances, extraInstances, loading, refresh, removeInstance, renameInstance } = useChannelInstances({
    channelType: 'feishu',
    primaryName: 'feishu',
    i18nPrefix: 'feishu',
  });

  const refreshStatuses = useCallback(() => {
    listChannelStatuses()
      .then((all) => setStatuses(all))
      .catch(() => setStatuses([]));
  }, []);

  const refreshCapacity = useCallback(() => {
    getChannelInstanceMeta()
      .then((meta) => setMaxInstances(meta.maxInstancesPerType))
      .catch(() => setMaxInstances(0));
  }, []);

  useEffect(() => {
    void refresh();
    refreshStatuses();
    refreshCapacity();
  }, [refresh, refreshStatuses, refreshCapacity]);

  const statusFor = useCallback(
    (channelName: string): ChannelStatus | undefined => statuses.find((s) => s.name === channelName),
    [statuses],
  );

  const handleQrSuccess = useCallback(() => {
    void refresh();
    refreshStatuses();
    refreshCapacity();
  }, [refresh, refreshStatuses, refreshCapacity]);

  const handleCredentialsSaved = useCallback(() => {
    void refresh();
    refreshStatuses();
    refreshCapacity();
  }, [refresh, refreshStatuses, refreshCapacity]);

  const handleAddClick = useCallback(() => {
    setAddDialogOpen(true);
  }, []);

  const atInstanceLimit = maxInstances > 0 && instances.length >= maxInstances;

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
        <IconLoader className="h-4 w-4 animate-spin" />
        <span>{t('feishuMultiAppDesc')}</span>
      </div>
    );
  }

  return (
    <div className="space-y-3 pt-1">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-medium">{t('feishuMultiAppTitle')}</p>
          <p className="text-xs text-muted-foreground">{t('feishuMultiAppDesc')}</p>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="shrink-0 text-xs gap-1.5"
          onClick={handleAddClick}
          disabled={atInstanceLimit}
          title={
            atInstanceLimit
              ? t('feishuMultiAppLimitReached', { count: instances.length, max: maxInstances })
              : undefined
          }
        >
          <IconPlus className="h-3.5 w-3.5" />
          {t('feishuAddApp')}
        </Button>
      </div>

      {atInstanceLimit && (
        <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-600 dark:text-amber-400">
          {t('feishuMultiAppLimitReached', { count: instances.length, max: maxInstances })}
        </p>
      )}

      {extraInstances.length === 0 && (
        <p className="rounded-lg border border-dashed px-3 py-3 text-center text-xs text-muted-foreground">
          {t('feishuScanToAdd')}
        </p>
      )}

      {extraInstances.map((inst) => (
        <FeishuAppCard
          key={inst.instanceId}
          channelName={inst.channelName}
          label={inst.displayName || inst.channelName}
          status={statusFor(inst.channelName)}
          onDelete={() => void removeInstance(inst.instanceId)}
          onRename={(label) => void renameInstance(inst.channelName, label)}
          onEditCredentials={() => setEditChannelName(inst.channelName)}
          t={t}
        />
      ))}

      <FeishuQrRegisterDialog
        open={addDialogOpen}
        onOpenChange={setAddDialogOpen}
        allowLabel
        onSuccess={handleQrSuccess}
      />

      <FeishuCredentialsEditDialog
        open={editChannelName !== null}
        onOpenChange={(open) => !open && setEditChannelName(null)}
        channelName={editChannelName ?? ''}
        onSaved={handleCredentialsSaved}
      />
    </div>
  );
}

function FeishuAppCard({
  channelName,
  label,
  status,
  onDelete,
  onRename,
  onEditCredentials,
  t,
}: {
  channelName: string;
  label: string;
  status?: ChannelStatus;
  onDelete: () => void;
  onRename: (label: string) => void;
  onEditCredentials: () => void;
  t: ReturnType<typeof useTranslations<'channels'>>;
}) {
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState('');
  const editInputRef = useRef<HTMLInputElement>(null);

  const isConnected = status?.connected ?? false;

  const startEditing = useCallback(() => {
    setEditValue(label);
    setEditing(true);
    setTimeout(() => editInputRef.current?.focus(), 50);
  }, [label]);

  const commitEdit = useCallback(() => {
    const trimmed = editValue.trim();
    if (trimmed && trimmed !== label) {
      onRename(trimmed);
    }
    setEditing(false);
  }, [editValue, label, onRename]);

  const cancelEdit = useCallback(() => {
    setEditing(false);
  }, []);

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
              onClick={startEditing}
              aria-label={`rename-${channelName}`}
              className="group inline-flex items-center gap-1 font-medium truncate max-w-[140px] hover:text-primary cursor-pointer"
              title={label}
            >
              {label}
              <IconPencil className="h-2.5 w-2.5 opacity-0 group-hover:opacity-60 transition-opacity shrink-0" />
            </button>
          )}
          <span
            className={cn(
              'inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[9px] font-medium shrink-0',
              isConnected
                ? 'bg-green-500/10 text-green-600 dark:text-green-400 border-green-500/20'
                : 'bg-muted text-muted-foreground border-muted',
            )}
          >
            {isConnected ? t('feishuConnected') : t('feishuStatusUnconfigured')}
          </span>
        </div>
        <div className="flex items-center gap-0.5 shrink-0">
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 text-muted-foreground hover:text-foreground shrink-0"
            aria-label={`edit-credentials-${channelName}`}
            onClick={onEditCredentials}
            title={t('feishuEditCredentials')}
          >
            <IconKey className="h-3 w-3" />
          </Button>
          <ConfirmDialog
            trigger={
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 text-destructive/60 hover:text-destructive shrink-0"
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
        </div>
      </div>
      <p className="text-[10px] text-muted-foreground break-all">{channelName}</p>
    </div>
  );
}
