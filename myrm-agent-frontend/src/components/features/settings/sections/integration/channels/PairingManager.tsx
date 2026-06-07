'use client';

import { useState } from 'react';
import {
  IconPlus,
  IconTrash,
  IconLoader,
  IconCheckCircle,
  IconBan,
  IconLock,
  IconPencil,
  IconCheck,
  IconX,
} from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
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
];

const STATUS_STYLES: Record<string, { className: string; key: string }> = {
  active: {
    className: 'bg-emerald-500/10 text-emerald-600 border-emerald-500/30',
    key: 'statusActive',
  },
  pending: {
    className: 'bg-amber-500/10 text-amber-600 border-amber-500/30',
    key: 'statusPending',
  },
  blocked: {
    className: 'bg-destructive/10 text-destructive border-destructive/30',
    key: 'statusBlocked',
  },
};

function channelLabel(name: string, t: (key: string) => string): string {
  const key = `channel${name.charAt(0).toUpperCase()}${name.slice(1)}`;
  const translated = t(key);
  return translated !== key ? translated : name;
}

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
];

function channelSpecificText(prefix: string, channel: string, t: (key: string) => string): string {
  if (!channel) return t(prefix);
  if (HINT_CHANNELS.includes(channel)) {
    const key = `${prefix}${channel.charAt(0).toUpperCase()}${channel.slice(1)}`;
    const translated = t(key);
    if (translated !== key) return translated;
  }
  return t(prefix);
}

function senderIdPlaceholder(channel: string, t: (key: string) => string): string {
  return channelSpecificText('senderIdPlaceholder', channel, t);
}

function senderIdHint(channel: string, t: (key: string) => string): string {
  return channelSpecificText('senderIdHint', channel, t);
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
  t,
}: {
  pairings: ChannelPairing[];
  loading: boolean;
  fixedChannel?: string;
  mode?: 'allowlist' | 'pairing';
  onAdd: (channel: string, senderId: string) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  onUpdateStatus: (id: string, status: 'active' | 'blocked') => Promise<void>;
  onUpdateDisplayName?: (id: string, displayName: string) => Promise<void>;
  t: (key: string, values?: Record<string, string>) => string;
}) {
  const filteredPairings = fixedChannel ? pairings.filter((p) => p.channel === fixedChannel) : pairings;

  const [showForm, setShowForm] = useState(false);
  const [channel, setChannel] = useState<string>(fixedChannel ?? '');
  const [senderId, setSenderId] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ChannelPairing | null>(null);
  const [editingNameId, setEditingNameId] = useState<string | null>(null);
  const [editNameValue, setEditNameValue] = useState('');

  const effectiveChannel = fixedChannel ?? channel;

  const handleAdd = async () => {
    if (!effectiveChannel || !senderId.trim()) return;
    setSubmitting(true);
    try {
      await onAdd(effectiveChannel, senderId.trim());
      setShowForm(false);
      if (!fixedChannel) setChannel('');
      setSenderId('');
    } finally {
      setSubmitting(false);
    }
  };

  const handleStatusChange = async (id: string, status: 'active' | 'blocked') => {
    setUpdatingId(id);
    try {
      await onUpdateStatus(id, status);
    } finally {
      setUpdatingId(null);
    }
  };

  const handleSaveName = async (id: string) => {
    if (!onUpdateDisplayName) return;
    setUpdatingId(id);
    try {
      await onUpdateDisplayName(id, editNameValue.trim());
      setEditingNameId(null);
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
        {filteredPairings.map((p) => {
          const style = STATUS_STYLES[p.status] ?? STATUS_STYLES.active;
          const isUpdating = updatingId === p.id;
          const isEditingName = editingNameId === p.id;
          return (
            <div key={p.id} className="group flex items-center justify-between rounded-lg border bg-card px-4 py-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  {!fixedChannel && <Badge variant="outline">{channelLabel(p.channel, t)}</Badge>}
                  <Badge variant="outline" className={cn('text-[11px]', style.className)}>
                    {t(style.key)}
                  </Badge>
                </div>
                <div className="flex items-center gap-1.5 mt-1">
                  {isEditingName ? (
                    <div className="flex items-center gap-1">
                      <Input
                        value={editNameValue}
                        onChange={(e) => setEditNameValue(e.target.value)}
                        className="h-6 text-sm px-1.5 w-32"
                        placeholder={t('displayNamePlaceholder')}
                        autoFocus
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') handleSaveName(p.id);
                          if (e.key === 'Escape') setEditingNameId(null);
                        }}
                      />
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-5 w-5"
                        disabled={isUpdating}
                        onClick={() => handleSaveName(p.id)}
                      >
                        {isUpdating ? (
                          <IconLoader className="h-3 w-3 animate-spin" />
                        ) : (
                          <IconCheck className="h-3 w-3" />
                        )}
                      </Button>
                      <Button size="icon" variant="ghost" className="h-5 w-5" onClick={() => setEditingNameId(null)}>
                        <IconX className="h-3 w-3" />
                      </Button>
                    </div>
                  ) : (
                    <>
                      {p.display_name ? (
                        <span className="text-sm font-medium truncate">{p.display_name}</span>
                      ) : (
                        <span className="text-xs font-mono text-muted-foreground truncate">{p.sender_id}</span>
                      )}
                      {onUpdateDisplayName && (
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-5 w-5 opacity-0 group-hover:opacity-100 hover:opacity-100 focus:opacity-100"
                          title={t('editDisplayName')}
                          onClick={() => {
                            setEditingNameId(p.id);
                            setEditNameValue(p.display_name ?? '');
                          }}
                        >
                          <IconPencil className="h-3 w-3" />
                        </Button>
                      )}
                    </>
                  )}
                </div>
                {!isEditingName && p.display_name && (
                  <p className="text-xs font-mono text-muted-foreground truncate">{p.sender_id}</p>
                )}
                <p className="text-xs text-muted-foreground mt-0.5">
                  {t('paired')} · {new Date(p.created_at).toLocaleDateString()}
                </p>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                {p.status === 'pending' && (
                  <Button
                    size="sm"
                    variant="ghost"
                    title={t('approveHint')}
                    className="h-8 text-emerald-600 hover:text-emerald-700 hover:bg-emerald-500/10"
                    disabled={isUpdating}
                    onClick={() => handleStatusChange(p.id, 'active')}
                  >
                    {isUpdating ? (
                      <IconLoader className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <IconCheckCircle className="h-3.5 w-3.5 mr-1" />
                    )}
                    {t('approve')}
                  </Button>
                )}
                {p.status === 'active' && (
                  <Button
                    size="sm"
                    variant="ghost"
                    title={t('blockHint')}
                    className="h-8 text-amber-600 hover:text-amber-700 hover:bg-amber-500/10"
                    disabled={isUpdating}
                    onClick={() => handleStatusChange(p.id, 'blocked')}
                  >
                    {isUpdating ? (
                      <IconLoader className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <IconBan className="h-3.5 w-3.5 mr-1" />
                    )}
                    {t('block')}
                  </Button>
                )}
                {p.status === 'blocked' && (
                  <Button
                    size="sm"
                    variant="ghost"
                    title={t('unblockHint')}
                    className="h-8 text-primary hover:bg-primary/10"
                    disabled={isUpdating}
                    onClick={() => handleStatusChange(p.id, 'active')}
                  >
                    {isUpdating ? (
                      <IconLoader className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <IconLock className="h-3.5 w-3.5 mr-1" />
                    )}
                    {t('unblock')}
                  </Button>
                )}
                <Button
                  size="icon"
                  variant="ghost"
                  title={t('deleteHint')}
                  className="h-8 w-8 text-destructive hover:text-destructive shrink-0"
                  onClick={() => setDeleteTarget(p)}
                >
                  <IconTrash className="h-4 w-4" />
                </Button>
              </div>
            </div>
          );
        })}
      </div>

      {showForm && (
        <div className="rounded-lg border bg-card p-4 space-y-3">
          <div className={fixedChannel ? '' : 'grid gap-3 sm:grid-cols-2'}>
            {!fixedChannel && (
              <div>
                <Label className="text-xs">{t('channel')}</Label>
                <Select value={channel} onValueChange={setChannel}>
                  <SelectTrigger>
                    <SelectValue placeholder={t('selectChannel')} />
                  </SelectTrigger>
                  <SelectContent>
                    {CHANNEL_OPTIONS.map((ch) => (
                      <SelectItem key={ch} value={ch}>
                        {channelLabel(ch, t)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            <div>
              <Label className="text-xs">{t('senderId')}</Label>
              <Input
                value={senderId}
                onChange={(e) => setSenderId(e.target.value)}
                placeholder={senderIdPlaceholder(effectiveChannel, t)}
                className="font-mono text-sm"
              />
            </div>
          </div>
          <p className="text-xs text-muted-foreground">{senderIdHint(effectiveChannel, t)}</p>
          {mode !== 'pairing' && <p className="text-xs text-muted-foreground/70 italic">{t('dontKnowIdHint')}</p>}
          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setShowForm(false);
                if (!fixedChannel) setChannel('');
                setSenderId('');
              }}
            >
              {t('cancel')}
            </Button>
            <Button size="sm" onClick={handleAdd} disabled={submitting || !effectiveChannel || !senderId.trim()}>
              {submitting ? t('adding') : t('add')}
            </Button>
          </div>
        </div>
      )}

      {!showForm && (
        <Button variant="outline" size="sm" onClick={() => setShowForm(true)}>
          <IconPlus className="h-3.5 w-3.5 mr-1" />
          {t('addPairing')}
        </Button>
      )}

      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
      >
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
                if (deleteTarget) await onDelete(deleteTarget.id);
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
