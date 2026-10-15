'use client';

/**
 * One chat's Catchup card.
 *
 * [INPUT]
 * - services/chat::CatchupBrief (POS: bounded, closed-vocabulary summary from the server)
 * - next-intl `Catchup` namespace (POS: localized status, need and count copy)
 *
 * [OUTPUT]
 * - CatchupBriefCard: status, what was asked, the reply opening, changed files, tool call count, and what the user must do
 *
 * [POS]
 * Presentation only. Running and approval-blocked chats offer no dismissal, since they would be listed again at once.
 */

import React from 'react';
import { formatRelativeTime } from '@/lib/utils/relativeTime';
import { CheckCircle2, Clock, AlertCircle, FileCode, Wrench, Activity, MessageSquare, CircleStop } from 'lucide-react';
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '@/components/primitives/card';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import type { CatchupBrief, CatchupNeed, CatchupStatus } from '@/services/chat';
import { useLocale, useTranslations } from 'next-intl';

interface CatchupBriefCardProps {
  brief: CatchupBrief;
  onRead: (chatId: string) => void;
  onNavigate: (chatId: string) => void;
}

const MAX_LISTED_FILES = 2;

const STATUS_VIEW: Record<
  CatchupStatus,
  { icon: React.ElementType; iconClass: string; labelKey: string; badge: 'default' | 'secondary' | 'destructive' }
> = {
  completed: { icon: CheckCircle2, iconClass: 'text-green-500', labelKey: 'statusCompleted', badge: 'default' },
  running: { icon: Activity, iconClass: 'text-blue-500 animate-pulse', labelKey: 'statusRunning', badge: 'default' },
  waiting_for_approval: { icon: Clock, iconClass: 'text-amber-500', labelKey: 'statusWaiting', badge: 'secondary' },
  error: { icon: AlertCircle, iconClass: 'text-red-500', labelKey: 'statusError', badge: 'destructive' },
  stopped: { icon: CircleStop, iconClass: 'text-muted-foreground', labelKey: 'statusStopped', badge: 'secondary' },
};

const NEED_LABEL_KEY: Record<CatchupNeed, string> = {
  approval: 'needsApproval',
  error: 'needsError',
  question: 'needsQuestion',
};

/** Running and blocked chats are still in flight: dismissing them would only bring them back. */
const DISMISSIBLE: ReadonlySet<CatchupStatus> = new Set(['completed', 'error', 'stopped']);

export const CatchupBriefCard: React.FC<CatchupBriefCardProps> = ({ brief, onRead, onNavigate }) => {
  const t = useTranslations('Catchup');
  const locale = useLocale();

  const view = STATUS_VIEW[brief.status];
  const StatusIcon = view.icon;
  const title = brief.chat_title || t('untitledChat');
  const toolCallCount = Object.values(brief.tool_counts).reduce((sum, count) => sum + count, 0);
  const hiddenFileCount = brief.files_touched.length - MAX_LISTED_FILES;

  return (
    <Card className="w-full mb-4 hover:shadow-md transition-shadow border-l-4 border-l-primary/60">
      <CardHeader className="pb-2 pt-4 flex flex-row items-start justify-between gap-2">
        <div className="min-w-0">
          <CardTitle className="text-lg font-semibold flex items-center gap-2">
            <StatusIcon className={`w-5 h-5 shrink-0 ${view.iconClass}`} />
            <span className="truncate" title={title}>
              {title}
            </span>
          </CardTitle>
          <div className="text-xs text-muted-foreground mt-1">{formatRelativeTime(brief.updated_at, locale)}</div>
        </div>
        <Badge variant={view.badge} className="shrink-0">
          {t(view.labelKey)}
        </Badge>
      </CardHeader>

      <CardContent className="pb-3 text-sm space-y-3">
        {brief.last_user_prompt && (
          <div className="bg-muted/50 p-2 rounded-xl border border-border/50">
            <div className="font-semibold text-xs text-muted-foreground mb-1 flex items-center gap-1">
              <MessageSquare className="w-3 h-3" /> {t('youAsked')}
            </div>
            <p className="line-clamp-2 break-words text-foreground/90">{brief.last_user_prompt}</p>
          </div>
        )}

        {brief.result_preview && (
          <div className="p-2 rounded-xl border border-border/50">
            <div className="font-semibold text-xs text-muted-foreground mb-1">{t('latestReply')}</div>
            <p className="line-clamp-3 break-words text-foreground/90">{brief.result_preview}</p>
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {brief.files_touched.length > 0 && (
            <div className="flex flex-col gap-1 min-w-0">
              <div className="font-semibold text-xs text-muted-foreground flex items-center gap-1">
                <FileCode className="w-3 h-3" /> {t('filesChanged')} ({brief.files_touched.length})
              </div>
              <ul className="text-xs text-foreground/80 list-disc pl-4">
                {brief.files_touched.slice(0, MAX_LISTED_FILES).map((f) => (
                  <li key={f} className="truncate" title={f}>
                    {f.split('/').pop()}
                  </li>
                ))}
                {hiddenFileCount > 0 && (
                  <li className="text-muted-foreground">{t('moreFiles', { count: hiddenFileCount })}</li>
                )}
              </ul>
            </div>
          )}

          {toolCallCount > 0 && (
            <div className="flex flex-col gap-1">
              <div className="font-semibold text-xs text-muted-foreground flex items-center gap-1">
                <Wrench className="w-3 h-3" /> {t('toolsUsed')}
              </div>
              <div className="text-xs text-foreground/80">{t('toolCalls', { count: toolCallCount })}</div>
            </div>
          )}
        </div>

        {brief.needs_from_user && (
          <div className="bg-amber-500/10 text-amber-600 dark:text-amber-400 p-2 rounded-xl border border-amber-500/20 text-xs font-medium flex items-start gap-2">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{t(NEED_LABEL_KEY[brief.needs_from_user])}</span>
          </div>
        )}
      </CardContent>

      <CardFooter className="pt-0 pb-4 flex justify-end gap-2">
        {DISMISSIBLE.has(brief.status) && (
          <Button variant="ghost" size="sm" onClick={() => onRead(brief.chat_id)}>
            {t('markAsRead')}
          </Button>
        )}
        <Button variant="default" size="sm" onClick={() => onNavigate(brief.chat_id)}>
          {t('viewChat')}
        </Button>
      </CardFooter>
    </Card>
  );
};
