'use client';

import React from 'react';
import { formatDistanceToNow } from 'date-fns';
import { CheckCircle2, Clock, AlertCircle, FileCode, Wrench, Activity, MessageSquare } from 'lucide-react';
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import type { CatchupBrief } from '@/services/chat';
import { useTranslations } from 'next-intl';

interface CatchupBriefCardProps {
  brief: CatchupBrief;
  onRead: (chatId: string) => void;
  onNavigate: (chatId: string) => void;
}

export const CatchupBriefCard: React.FC<CatchupBriefCardProps> = ({ brief, onRead, onNavigate }) => {
  const t = useTranslations('Catchup');

  const getStatusIcon = () => {
    switch (brief.status) {
      case 'completed':
        return <CheckCircle2 className="w-5 h-5 text-green-500" />;
      case 'waiting_for_approval':
        return <Clock className="w-5 h-5 text-amber-500" />;
      case 'error':
        return <AlertCircle className="w-5 h-5 text-red-500" />;
      case 'running':
        return <Activity className="w-5 h-5 text-blue-500 animate-pulse" />;
      default:
        return <CheckCircle2 className="w-5 h-5 text-green-500" />;
    }
  };

  const getStatusText = () => {
    switch (brief.status) {
      case 'completed':
        return t('statusCompleted', { defaultValue: 'Completed' });
      case 'waiting_for_approval':
        return t('statusWaiting', { defaultValue: 'Waiting for Approval' });
      case 'error':
        return t('statusError', { defaultValue: 'Error' });
      case 'running':
        return t('statusRunning', { defaultValue: 'Running in Background' });
      default:
        return brief.status;
    }
  };

  return (
    <Card className="w-full mb-4 hover:shadow-md transition-shadow border-l-4 border-l-primary/60">
      <CardHeader className="pb-2 pt-4 flex flex-row items-start justify-between">
        <div>
          <CardTitle className="text-lg font-semibold flex items-center gap-2">
            {getStatusIcon()}
            <span className="truncate max-w-[250px]" title={brief.chat_title}>
              {brief.chat_title}
            </span>
          </CardTitle>
          <div className="text-xs text-muted-foreground mt-1">
            {formatDistanceToNow(new Date(brief.updated_at), { addSuffix: true })}
          </div>
        </div>
        <Badge
          variant={
            brief.status === 'error' ? 'destructive' : brief.status === 'waiting_for_approval' ? 'secondary' : 'default'
          }
        >
          {getStatusText()}
        </Badge>
      </CardHeader>

      <CardContent className="pb-3 text-sm space-y-3">
        {/* User Prompt */}
        {brief.last_user_prompt && (
          <div className="bg-muted/50 p-2 rounded-full border border-border/50">
            <div className="font-semibold text-xs text-muted-foreground mb-1 flex items-center gap-1">
              <MessageSquare className="w-3 h-3" /> {t('youAsked', { defaultValue: 'You asked:' })}
            </div>
            <p className="line-clamp-2 text-foreground/90">{brief.last_user_prompt}</p>
          </div>
        )}

        {/* Activity & Tools */}
        <div className="grid grid-cols-2 gap-2">
          {brief.files_touched.length > 0 && (
            <div className="flex flex-col gap-1">
              <div className="font-semibold text-xs text-muted-foreground flex items-center gap-1">
                <FileCode className="w-3 h-3" /> {t('filesChanged', { defaultValue: 'Files Changed' })} (
                {brief.files_touched.length})
              </div>
              <ul className="text-xs text-foreground/80 list-disc pl-4">
                {brief.files_touched.slice(0, 2).map((f) => (
                  <li key={f} className="truncate" title={f}>
                    {f.split('/').pop()}
                  </li>
                ))}
                {brief.files_touched.length > 2 && (
                  <li className="text-muted-foreground">+{brief.files_touched.length - 2} more</li>
                )}
              </ul>
            </div>
          )}

          {Object.keys(brief.tool_counts).length > 0 && (
            <div className="flex flex-col gap-1">
              <div className="font-semibold text-xs text-muted-foreground flex items-center gap-1">
                <Wrench className="w-3 h-3" /> {t('toolsUsed', { defaultValue: 'Tools Used' })}
              </div>
              <div className="flex flex-wrap gap-1">
                {Object.entries(brief.tool_counts)
                  .slice(0, 3)
                  .map(([tool, count]) => (
                    <Badge key={tool} variant="outline" className="text-[10px] px-1 py-0 h-4">
                      {tool.replace('_tool', '')} x{count}
                    </Badge>
                  ))}
              </div>
            </div>
          )}
        </div>

        {/* Needs from user */}
        {brief.needs_from_user && (
          <div className="bg-amber-500/10 text-amber-600 dark:text-amber-400 p-2 rounded-full border border-amber-500/20 text-xs font-medium flex items-start gap-2">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{brief.needs_from_user}</span>
          </div>
        )}
      </CardContent>

      <CardFooter className="pt-0 pb-4 flex justify-end gap-2">
        <Button variant="ghost" size="sm" onClick={() => onRead(brief.chat_id)}>
          {t('markAsRead', { defaultValue: 'Dismiss' })}
        </Button>
        <Button variant="default" size="sm" onClick={() => onNavigate(brief.chat_id)}>
          {t('viewChat', { defaultValue: 'View Chat' })}
        </Button>
      </CardFooter>
    </Card>
  );
};
