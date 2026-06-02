'use client';

import {
  IconLoader,
  IconRefresh,
  IconSearch,
  IconAlertTriangle,
  IconCheckCheck,
} from '@/components/ui/icons/PremiumIcons';
import { Users } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import type { GroupInfo, GroupPolicy } from '@/services/channels';

export const CHANNELS_WITH_GROUPS = new Set(['whatsapp', 'mattermost', 'signal', 'discord']);

interface GroupManagerProps {
  groups: GroupInfo[];
  channelFilter: string;
  channelStatus?: string;
  isChannelConnected?: boolean;
  loading: boolean;
  groupPolicy?: GroupPolicy;
  onToggle: (jid: string, enabled: boolean) => void;
  onRefresh: () => void;
  refreshing: boolean;
  freeResponseChats?: string[];
  onFreeResponseToggle?: (jid: string, enabled: boolean) => void;
  t: (key: string, values?: Record<string, string | number>) => string;
}

export function GroupManager({
  groups,
  channelFilter,
  channelStatus,
  isChannelConnected,
  loading,
  groupPolicy,
  onToggle,
  onRefresh,
  refreshing,
  freeResponseChats = [],
  onFreeResponseToggle,
  t,
}: GroupManagerProps) {
  const [search, setSearch] = useState('');

  const channelGroups = useMemo(() => groups.filter((g) => g.channel === channelFilter), [groups, channelFilter]);

  const enabledCount = useMemo(() => channelGroups.filter((g) => g.is_enabled).length, [channelGroups]);

  const filtered = useMemo(() => {
    if (!search.trim()) return channelGroups;
    const q = search.toLowerCase();
    return channelGroups.filter((g) => g.name.toLowerCase().includes(q) || g.jid.toLowerCase().includes(q));
  }, [channelGroups, search]);

  const groupPolicyActive = groupPolicy && groupPolicy !== 'disabled';
  const showNoGroupWarning = groupPolicyActive && channelGroups.length > 0 && enabledCount === 0;

  const handleEnableAll = () => {
    for (const g of channelGroups) {
      if (!g.is_enabled) onToggle(g.jid, true);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-6">
        <IconLoader className="h-4 w-4 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const isDisconnected =
    isChannelConnected === false ||
    !channelStatus ||
    channelStatus === 'disabled' ||
    channelStatus === 'idle' ||
    channelStatus === 'running_idle';

  return (
    <div className="space-y-3 mt-6 pt-5 border-t border-border/40">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Users className="h-4 w-4 text-muted-foreground" />
          <h4 className="text-sm font-medium">{t('groupsTitle')}</h4>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={onRefresh}
          disabled={refreshing || isDisconnected}
          className="h-7 gap-1.5 text-xs"
        >
          <IconRefresh className={`h-3 w-3 ${refreshing ? 'animate-spin' : ''}`} />
          {t('groupsRefresh')}
        </Button>
      </div>

      <p className="text-xs text-muted-foreground">{t('groupsDesc')}</p>

      {isDisconnected ? (
        <p className="text-xs text-muted-foreground/70 py-3 text-center">{t('groupsConnectFirst')}</p>
      ) : channelGroups.length === 0 ? (
        <p className="text-xs text-muted-foreground/70 py-3 text-center">{t('groupsEmpty')}</p>
      ) : (
        <>
          {showNoGroupWarning && (
            <div className="flex items-start gap-2.5 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3">
              <IconAlertTriangle className="h-4 w-4 shrink-0 text-amber-500 mt-0.5" />
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium text-amber-700 dark:text-amber-400">{t('groupsNoEnabledWarning')}</p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleEnableAll}
                  className="mt-2 h-7 gap-1.5 text-xs border-amber-500/40 text-amber-700 dark:text-amber-400 hover:bg-amber-500/10"
                >
                  <IconCheckCheck className="h-3 w-3" />
                  {t('groupsEnableAll')}
                </Button>
              </div>
            </div>
          )}

          <div className="flex items-center gap-2">
            <div className="relative flex-1">
              <IconSearch className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground/60" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={t('groupsSearchPlaceholder')}
                className="w-full h-8 pl-8 pr-3 text-xs rounded-full border border-border/60 bg-background focus:outline-none focus:ring-1 focus:ring-ring placeholder:text-muted-foreground/50"
              />
            </div>
            <p className="text-xs text-muted-foreground whitespace-nowrap">
              {t('groupsCount', { count: channelGroups.length })}
            </p>
          </div>

          <div className="max-h-72 overflow-y-auto rounded-lg border bg-card/50">
            {filtered.length === 0 ? (
              <p className="text-xs text-muted-foreground/70 py-3 text-center">{t('groupsNoMatch')}</p>
            ) : (
              filtered.map((g, idx) => (
                <div
                  key={g.jid}
                  className={`flex flex-col gap-2 px-3 py-2.5 transition-colors hover:bg-muted/10 ${
                    idx < filtered.length - 1 ? 'border-b border-border/50' : ''
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2.5 min-w-0">
                      <Users className="h-3.5 w-3.5 shrink-0 text-muted-foreground/70" />
                      <span className="text-sm font-medium truncate">{g.name || g.jid}</span>
                    </div>
                    <Switch checked={g.is_enabled} onCheckedChange={(checked) => onToggle(g.jid, checked)} />
                  </div>
                  {g.is_enabled && onFreeResponseToggle && (
                    <div className="flex items-center justify-between ml-6 mt-1 pt-1 border-t border-dashed border-border/30">
                      <div className="flex flex-col">
                        <span className="text-[11px] font-medium text-foreground/80">
                          {t('groupsFreeResponseTitle')}
                        </span>
                        <span className="text-[10px] text-muted-foreground/70">{t('groupsFreeResponseDesc')}</span>
                      </div>
                      <Switch
                        checked={freeResponseChats.includes(g.jid)}
                        onCheckedChange={(checked) => onFreeResponseToggle(g.jid, checked)}
                      />
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </>
      )}
    </div>
  );
}
