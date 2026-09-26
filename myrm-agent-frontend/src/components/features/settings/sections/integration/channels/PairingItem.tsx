'use client';

import { useState } from 'react';
import {
  IconCheckCircle,
  IconBan,
  IconLock,
  IconTrash,
  IconLoader,
  IconPencil,
  IconCheck,
  IconX,
  IconShield,
  IconUser,
} from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { Input } from '@/components/primitives/input';
import type { ChannelPairing } from '@/services/channels';

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

export interface PairingItemProps {
  pairing: ChannelPairing;
  fixedChannel?: string;
  isUpdating: boolean;
  channelLabel: (channel: string) => string;
  onUpdateStatus: (id: string, status: 'active' | 'blocked') => Promise<void>;
  onUpdateDisplayName?: (id: string, displayName: string) => Promise<void>;
  onUpdateRole?: (id: string, role: 'admin' | 'member') => Promise<void>;
  onUpdateDailyQuota?: (id: string, quota: number | null) => Promise<void>;
  onDeleteRequest: (pairing: ChannelPairing) => void;
  t: (key: string, values?: Record<string, string | number>) => string;
}

export function PairingItem({
  pairing: p,
  fixedChannel,
  isUpdating,
  channelLabel,
  onUpdateStatus,
  onUpdateDisplayName,
  onUpdateRole,
  onUpdateDailyQuota,
  onDeleteRequest,
  t,
}: PairingItemProps) {
  const [isEditingName, setIsEditingName] = useState(false);
  const [editNameValue, setEditNameValue] = useState(p.display_name ?? '');
  const [isEditingQuota, setIsEditingQuota] = useState(false);
  const [editQuotaValue, setEditQuotaValue] = useState(p.daily_quota ? String(p.daily_quota) : '');

  const style = STATUS_STYLES[p.status] ?? STATUS_STYLES.active;
  const isAdmin = p.role === 'admin';

  const handleSaveName = async () => {
    if (!onUpdateDisplayName) return;
    await onUpdateDisplayName(p.id, editNameValue.trim());
    setIsEditingName(false);
  };

  const handleSaveQuota = async () => {
    if (!onUpdateDailyQuota) return;
    const trimmed = editQuotaValue.trim();
    const quotaNum = trimmed ? Math.max(1, parseInt(trimmed, 10)) : null;
    await onUpdateDailyQuota(p.id, Number.isNaN(quotaNum) ? null : quotaNum);
    setIsEditingQuota(false);
  };

  const handleToggleRole = async () => {
    if (!onUpdateRole) return;
    const nextRole = isAdmin ? 'member' : 'admin';
    await onUpdateRole(p.id, nextRole);
  };

  return (
    <div className="group flex items-center justify-between rounded-lg border bg-card px-4 py-3">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          {!fixedChannel && <Badge variant="outline">{channelLabel(p.channel)}</Badge>}
          <Badge variant="outline" className={cn('text-[11px]', style.className)}>
            {t(style.key)}
          </Badge>

          {/* Role badge with switch support */}
          <Badge
            variant="outline"
            onClick={onUpdateRole ? handleToggleRole : undefined}
            title={onUpdateRole ? t('switchRole') : undefined}
            className={cn(
              'text-[11px] flex items-center gap-1 transition-colors',
              isAdmin
                ? 'bg-purple-500/10 text-purple-600 border-purple-500/30'
                : 'bg-muted text-muted-foreground border-border',
              onUpdateRole && 'cursor-pointer hover:opacity-80',
            )}
          >
            {isAdmin ? <IconShield className="h-3 w-3" /> : <IconUser className="h-3 w-3" />}
            {isAdmin ? t('roleAdminBadge') : t('roleMemberBadge')}
          </Badge>

          {/* Daily Quota badge */}
          {!isAdmin && (
            <div className="inline-flex items-center">
              {isEditingQuota ? (
                <div className="flex items-center gap-1">
                  <Input
                    type="number"
                    min="1"
                    value={editQuotaValue}
                    onChange={(e) => setEditQuotaValue(e.target.value)}
                    className="h-5 text-xs px-1.5 w-16"
                    placeholder={t('unlimitedQuota')}
                    autoFocus
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleSaveQuota();
                      if (e.key === 'Escape') setIsEditingQuota(false);
                    }}
                  />
                  <Button size="icon" variant="ghost" className="h-5 w-5" onClick={handleSaveQuota} disabled={isUpdating}>
                    <IconCheck className="h-3 w-3" />
                  </Button>
                  <Button size="icon" variant="ghost" className="h-5 w-5" onClick={() => setIsEditingQuota(false)}>
                    <IconX className="h-3 w-3" />
                  </Button>
                </div>
              ) : (
                <Badge
                  variant="outline"
                  onClick={onUpdateDailyQuota ? () => {
                    setIsEditingQuota(true);
                    setEditQuotaValue(p.daily_quota ? String(p.daily_quota) : '');
                  } : undefined}
                  title={onUpdateDailyQuota ? t('editQuota') : undefined}
                  className={cn(
                    'text-[10px] text-muted-foreground',
                    onUpdateDailyQuota && 'cursor-pointer hover:bg-accent',
                  )}
                >
                  {p.daily_quota ? t('dailyQuotaDisplay', { quota: p.daily_quota }) : t('unlimitedQuota')}
                </Badge>
              )}
            </div>
          )}

          {/* Today Usage Watermark & Streamline Progress Bar */}
          {!isAdmin && (
            <div
              className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground"
              title="每日 00:00 UTC (北京时间 08:00) 自动刷新"
            >
              <span>今日用量：{p.today_usage ?? 0} / {p.daily_quota ? String(p.daily_quota) : '∞'} 次</span>
              {p.daily_quota && p.daily_quota > 0 && (() => {
                const todayUsage = p.today_usage ?? 0;
                const quota = p.daily_quota;
                const percent = Math.min(100, Math.round((todayUsage / quota) * 100));
                const isOver = todayUsage >= quota;
                const isWarning = percent >= 70 && !isOver;
                return (
                  <>
                    <div
                      className="w-14 h-1.5 rounded-full bg-muted overflow-hidden flex items-center"
                      role="progressbar"
                      aria-valuenow={percent}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      title={`${percent}%`}
                    >
                      <div
                        className={cn(
                          'h-full rounded-full transition-all duration-300',
                          isOver ? 'bg-destructive' : isWarning ? 'bg-amber-500' : 'bg-emerald-500',
                        )}
                        style={{ width: `${percent}%` }}
                      />
                    </div>
                    {isOver && (
                      <Badge
                        variant="outline"
                        className="text-[9px] px-1 py-0 h-4 bg-destructive/10 text-destructive border-destructive/30"
                      >
                        已超额
                      </Badge>
                    )}
                  </>
                );
              })()}
            </div>
          )}
        </div>

        {/* Display name and sender_id */}
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
                  if (e.key === 'Enter') handleSaveName();
                  if (e.key === 'Escape') setIsEditingName(false);
                }}
              />
              <Button size="icon" variant="ghost" className="h-5 w-5" disabled={isUpdating} onClick={handleSaveName}>
                {isUpdating ? <IconLoader className="h-3 w-3 animate-spin" /> : <IconCheck className="h-3 w-3" />}
              </Button>
              <Button size="icon" variant="ghost" className="h-5 w-5" onClick={() => setIsEditingName(false)}>
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
                    setIsEditingName(true);
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
            onClick={() => onUpdateStatus(p.id, 'active')}
          >
            {isUpdating ? <IconLoader className="h-3.5 w-3.5 animate-spin" /> : <IconCheckCircle className="h-3.5 w-3.5 mr-1" />}
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
            onClick={() => onUpdateStatus(p.id, 'blocked')}
          >
            {isUpdating ? <IconLoader className="h-3.5 w-3.5 animate-spin" /> : <IconBan className="h-3.5 w-3.5 mr-1" />}
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
            onClick={() => onUpdateStatus(p.id, 'active')}
          >
            {isUpdating ? <IconLoader className="h-3.5 w-3.5 animate-spin" /> : <IconLock className="h-3.5 w-3.5 mr-1" />}
            {t('unblock')}
          </Button>
        )}
        <Button
          size="icon"
          variant="ghost"
          title={t('deleteHint')}
          className="h-8 w-8 text-destructive hover:text-destructive shrink-0"
          onClick={() => onDeleteRequest(p)}
        >
          <IconTrash className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
