'use client';

import { memo, useCallback, useMemo, useRef, useState } from 'react';
import { IconChevronDown, IconChevronUp } from '@/components/ui/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/ui/button';
import ChannelIcon from './ChannelIcon';

const DEFAULT_VISIBLE_COUNT = 10;

export interface ChannelEntry {
  id: string;
  label: string;
}

export function buildChannelEntries(t: (key: string) => string): ChannelEntry[] {
  return [
    { id: 'whatsapp', label: 'WhatsApp' },
    { id: 'wechat', label: t('wechatTitle') },
    { id: 'telegram', label: 'Telegram' },
    { id: 'discord', label: 'Discord' },
    { id: 'slack', label: 'Slack' },
    { id: 'feishu', label: t('feishuTitle') },
    { id: 'dingtalk', label: t('dingtalkTitle') },
    { id: 'wecom_aibot', label: t('wecomAibotTitle') },
    { id: 'wecom', label: t('wecomTitle') },
    { id: 'qq', label: 'QQ (Official)' },
    { id: 'onebot', label: 'QQ (NapCat/OneBot)' },
    { id: 'teams', label: 'MS Teams' },
    { id: 'email', label: 'Email' },
    { id: 'matrix', label: 'Matrix' },
    { id: 'googlechat', label: 'Google Chat' },
    { id: 'mattermost', label: 'Mattermost' },
    { id: 'voice', label: t('voiceTitle') },
    { id: 'sms', label: t('smsTitle') },
    { id: 'signal', label: 'Signal' },
    { id: 'line', label: 'LINE' },
    { id: 'imessage', label: 'iMessage' },
    { id: 'irc', label: 'IRC' },
    { id: 'zalo', label: 'Zalo' },
  ];
}

export interface ChannelActivityInfo {
  last_active_at: number | null;
}

function formatRelativeTime(
  epochSec: number | null,
  t: (key: string, values?: Record<string, string | number>) => string,
): string {
  if (!epochSec) return t('lastActiveNever');
  const deltaSec = Math.max(0, Math.floor(Date.now() / 1000 - epochSec));
  if (deltaSec < 60) return t('justNow');
  if (deltaSec < 3600) return t('minutesAgo', { count: Math.floor(deltaSec / 60) });
  if (deltaSec < 86400) return t('hoursAgo', { count: Math.floor(deltaSec / 3600) });
  return t('daysAgo', { count: Math.floor(deltaSec / 86400) });
}

interface ChannelListProps {
  channels: ChannelEntry[];
  selectedId: string;
  onSelect: (id: string) => void;
  statuses?: Record<string, string>;
  activities?: Record<string, ChannelActivityInfo>;
  issueCountByChannel?: Record<string, number>;
  groupCountByChannel?: Record<string, number>;
  renderDetail?: (channelId: string) => React.ReactNode;
  t: (key: string, values?: Record<string, string | number>) => string;
}

const STATUS_DOT: Record<string, string> = {
  running: 'bg-green-500 shadow-green-500/50',
  running_idle: 'bg-orange-400 shadow-orange-400/50',
  error: 'bg-red-500 shadow-red-500/50',
  warning: 'bg-yellow-500 shadow-yellow-500/50',
  disabled: 'bg-muted-foreground/40',
};

const ChannelList = memo<ChannelListProps>(
  ({
    channels,
    selectedId,
    onSelect,
    statuses,
    activities,
    issueCountByChannel,
    groupCountByChannel,
    renderDetail,
    t,
  }) => {
    const selectedInHidden = useMemo(
      () => channels.findIndex((ch) => ch.id === selectedId) >= DEFAULT_VISIBLE_COUNT,
      [channels, selectedId],
    );
    const [expanded, setExpanded] = useState(selectedInHidden);
    const itemRefs = useRef<Record<string, HTMLDivElement | null>>({});

    const handleSelect = useCallback(
      (id: string) => {
        onSelect(id);
        requestAnimationFrame(() => {
          itemRefs.current[id]?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        });
      },
      [onSelect],
    );

    const visibleChannels = expanded ? channels : channels.slice(0, DEFAULT_VISIBLE_COUNT);
    const hiddenCount = channels.length - DEFAULT_VISIBLE_COUNT;

    return (
      <div className="flex flex-col space-y-1">
        {visibleChannels.map((ch) => {
          const status = statuses?.[ch.id];
          const hasIssues = (issueCountByChannel?.[ch.id] ?? 0) > 0;
          const dotKey = status === 'running' && hasIssues ? 'warning' : status;
          const dotClass = dotKey ? STATUS_DOT[dotKey] : undefined;
          const activity = activities?.[ch.id];
          const showActivity = (status === 'running' || status === 'running_idle') && activity;

          const isSelected = selectedId === ch.id;
          return (
            <div
              key={ch.id}
              ref={(el) => {
                itemRefs.current[ch.id] = el;
              }}
            >
              <button
                type="button"
                onClick={() => handleSelect(ch.id)}
                className={cn(
                  'w-full flex items-center justify-between gap-2 px-3 py-2.5 rounded-lg text-left transition-all duration-200',
                  isSelected
                    ? 'bg-primary/10 border border-primary/30'
                    : 'hover:bg-accent/50 border border-transparent',
                )}
              >
                <div className="flex flex-col gap-0.5 min-w-0">
                  <div className="flex items-center gap-2.5">
                    <ChannelIcon channelId={ch.id} size={18} />
                    <span
                      className={cn('text-sm font-medium truncate', isSelected ? 'text-primary' : 'text-foreground')}
                    >
                      {ch.label}
                    </span>
                  </div>
                  {showActivity && (
                    <span className="text-[10px] text-muted-foreground pl-[26px] leading-tight">
                      {formatRelativeTime(activity.last_active_at, t)}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  {(groupCountByChannel?.[ch.id] ?? 0) > 0 && (
                    <span className="text-[10px] leading-none px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground font-medium">
                      {groupCountByChannel?.[ch.id]}
                    </span>
                  )}
                  {dotClass && <span className={cn('h-2 w-2 rounded-full', dotClass)} />}
                  {renderDetail && (
                    <IconChevronDown
                      className={cn(
                        'h-3.5 w-3.5 text-muted-foreground transition-transform duration-200 lg:hidden',
                        isSelected && 'rotate-180 text-primary',
                      )}
                    />
                  )}
                </div>
              </button>
              {isSelected && renderDetail && (
                <div className="lg:hidden mt-1 mb-1 rounded-lg border border-border/60 bg-card/50 p-4 animate-in fade-in">
                  {renderDetail(ch.id)}
                </div>
              )}
            </div>
          );
        })}

        {hiddenCount > 0 && (
          <div className="pt-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setExpanded((prev) => !prev)}
              className="w-full h-8 text-xs gap-1.5"
            >
              {expanded ? (
                <>
                  <IconChevronUp className="h-3.5 w-3.5" />
                  {t('hideChannels')}
                </>
              ) : (
                <>
                  <IconChevronDown className="h-3.5 w-3.5" />
                  {t('showAllChannels', { count: hiddenCount })}
                </>
              )}
            </Button>
          </div>
        )}
      </div>
    );
  },
);

ChannelList.displayName = 'ChannelList';

export default ChannelList;
