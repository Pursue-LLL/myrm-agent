'use client';

import { useState } from 'react';
import { IconPlus, IconLoader } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/primitives/alert-dialog';
import type { ChannelPairing } from '@/services/channels';
import { PairingItem } from './PairingItem';
import { PairingForm } from './PairingForm';

const CHANNEL_OPTIONS = [
  'whatsapp',
  'telegram',
  'feishu',
  'wechat',
  'discord',
  'slack',
  'wecom',
  'teams',
  'mattermost',
  'googlechat',
  'dingtalk',
  'line',
  'signal',
  'matrix',
  'imessage',
];

const HINT_CHANNELS = [
  'whatsapp',
  'telegram',
  'feishu',
  'wechat',
  'discord',
  'slack',
  'dingtalk',
  'email',
  'wecom',
  'teams',
  'line',
  'signal',
  'imessage',
];

function channelLabel(name: string, t: (key: string) => string): string {
  const key = `channel${name.charAt(0).toUpperCase()}${name.slice(1)}`;
  const translated = t(key);
  return translated !== key ? translated : name;
}

function channelSpecificText(prefix: string, channel: string, t: (key: string) => string): string {
  if (!channel) return t(prefix);
  if (HINT_CHANNELS.includes(channel)) {
    const key = `${prefix}${channel.charAt(0).toUpperCase()}${channel.slice(1)}`;
    const translated = t(key);
    if (translated !== key) return translated;
  }
  return t(prefix);
}

export interface PairingManagerProps {
  pairings: ChannelPairing[];
  loading: boolean;
  fixedChannel?: string;
  mode?: 'allowlist' | 'pairing';
  onAdd: (channel: string, senderId: string, role?: 'admin' | 'member', dailyQuota?: number | null) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  onUpdateStatus: (id: string, status: 'active' | 'blocked') => Promise<void>;
  onUpdateDisplayName?: (id: string, displayName: string) => Promise<void>;
  onUpdateRole?: (id: string, role: 'admin' | 'member') => Promise<void>;
  onUpdateDailyQuota?: (id: string, dailyQuota: number | null) => Promise<void>;
  t: (key: string, values?: Record<string, string | number>) => string;
}

export function PairingManager({
  pairings,
  loading,
  fixedChannel,
  mode,
  onAdd,
  onDelete,
  onUpdateStatus,
  onUpdateDisplayName,
  onUpdateRole,
  onUpdateDailyQuota,
  t,
}: PairingManagerProps) {
  const filteredPairings = fixedChannel ? pairings.filter((p) => p.channel === fixedChannel) : pairings;

  const [showForm, setShowForm] = useState(false);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ChannelPairing | null>(null);

  const handleAdd = async (channel: string, senderId: string, role: 'admin' | 'member', dailyQuota: number | null) => {
    await onAdd(channel, senderId, role, dailyQuota);
    setShowForm(false);
  };

  const handleStatusChange = async (id: string, status: 'active' | 'blocked') => {
    setUpdatingId(id);
    try {
      await onUpdateStatus(id, status);
    } finally {
      setUpdatingId(null);
    }
  };

  const handleRoleChange = async (id: string, role: 'admin' | 'member') => {
    if (!onUpdateRole) return;
    setUpdatingId(id);
    try {
      await onUpdateRole(id, role);
    } finally {
      setUpdatingId(null);
    }
  };

  const handleQuotaChange = async (id: string, quota: number | null) => {
    if (!onUpdateDailyQuota) return;
    setUpdatingId(id);
    try {
      await onUpdateDailyQuota(id, quota);
    } finally {
      setUpdatingId(null);
    }
  };

  return (
    <div className="space-y-3">
      {loading && (
        <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
          <IconLoader className="h-4 w-4 animate-spin" />
        </div>
      )}

      {!loading && filteredPairings.length === 0 && !showForm && (
        <p className="text-sm text-muted-foreground py-4 text-center">{t('noPairings')}</p>
      )}

      <div className="space-y-2">
        {filteredPairings.map((p) => (
          <PairingItem
            key={p.id}
            pairing={p}
            fixedChannel={fixedChannel}
            isUpdating={updatingId === p.id}
            channelLabel={(ch) => channelLabel(ch, t)}
            onUpdateStatus={handleStatusChange}
            onUpdateDisplayName={onUpdateDisplayName}
            onUpdateRole={onUpdateRole ? handleRoleChange : undefined}
            onUpdateDailyQuota={onUpdateDailyQuota ? handleQuotaChange : undefined}
            onDeleteRequest={setDeleteTarget}
            t={t}
          />
        ))}
      </div>

      {showForm && (
        <PairingForm
          fixedChannel={fixedChannel}
          channelOptions={CHANNEL_OPTIONS}
          mode={mode}
          channelLabel={(ch) => channelLabel(ch, t)}
          senderIdPlaceholder={(ch) => channelSpecificText('senderIdPlaceholder', ch, t)}
          senderIdHint={(ch) => channelSpecificText('senderIdHint', ch, t)}
          onSubmit={handleAdd}
          onCancel={() => setShowForm(false)}
          t={t}
        />
      )}

      {!showForm && (
        <Button variant="outline" size="sm" onClick={() => setShowForm(true)}>
          <IconPlus className="h-3.5 w-3.5 mr-1" />
          {t('addPairing')}
        </Button>
      )}

      <AlertDialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('deleteConfirmTitle')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('deleteConfirm', {
                channel: deleteTarget ? channelLabel(deleteTarget.channel, t) : '',
                senderId: deleteTarget?.sender_id ?? '',
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={async () => {
                if (deleteTarget) {
                  await onDelete(deleteTarget.id);
                }
                setDeleteTarget(null);
              }}
            >
              {t('delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
