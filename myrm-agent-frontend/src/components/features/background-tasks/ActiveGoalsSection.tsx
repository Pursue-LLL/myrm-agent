'use client';

import { Navigation, Target } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { formatDistanceToNow } from 'date-fns';
import { IconStop } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { cn } from '@/lib/utils/classnameUtils';
import { type ActiveGoal, GOAL_STATUS_STYLES } from './backgroundTasksPanel.constants';

interface ActiveGoalsSectionProps {
  goals: ActiveGoal[];
  onNavigateChat: (sessionId: string) => void;
  onGoalAction: (sessionId: string, action: string) => void;
}

export function ActiveGoalsSection({ goals, onNavigateChat, onGoalAction }: ActiveGoalsSectionProps) {
  const t = useTranslations('backgroundTasks');

  if (goals.length === 0) {
    return null;
  }

  return (
    <div className="border-b border-border/30">
      <div className="px-4 py-2 text-xs font-medium text-muted-foreground/70 uppercase tracking-wide">
        <Target className="mr-1 inline h-3 w-3" />
        {t('goalsSection')} ({goals.length})
      </div>
      <div className="divide-y divide-border/20">
        {goals.map((goal) => {
          const style = GOAL_STATUS_STYLES[goal.status] ?? GOAL_STATUS_STYLES.active;
          return (
            <div key={goal.goal_id} className="px-4 py-2.5 transition-colors hover:bg-muted/30">
              <div className="flex items-start gap-2.5">
                <Target className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                <div className="min-w-0 flex-1">
                  <p className="line-clamp-2 text-sm leading-snug text-foreground">{goal.objective}</p>
                  <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                    <span className={cn('h-1.5 w-1.5 rounded-full', style.dotColor)} />
                    <span>{t(style.i18nKey)}</span>
                    <span className="text-border">·</span>
                    <span>{formatDistanceToNow(new Date(goal.created_at), { addSuffix: true })}</span>
                    {goal.tokens_used > 0 && (
                      <>
                        <span className="text-border">·</span>
                        <span>
                          {goal.tokens_used >= 1000
                            ? `${(goal.tokens_used / 1000).toFixed(1)}k`
                            : goal.tokens_used}{' '}
                          tokens
                        </span>
                      </>
                    )}
                  </div>
                  <div className="mt-1.5 flex items-center gap-1.5">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 px-2 text-xs"
                      onClick={() => onNavigateChat(goal.session_id)}
                    >
                      <Navigation className="mr-1 h-3 w-3" />
                      {t('navigate')}
                    </Button>
                    {goal.status === 'active' && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 px-2 text-xs text-amber-600 dark:text-amber-400"
                        onClick={() => onGoalAction(goal.session_id, 'pause')}
                      >
                        {t('goalPause')}
                      </Button>
                    )}
                    {goal.status === 'paused' && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 px-2 text-xs text-emerald-600 dark:text-emerald-400"
                        onClick={() => onGoalAction(goal.session_id, 'resume')}
                      >
                        {t('goalResume')}
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 px-2 text-xs text-destructive hover:text-destructive"
                      onClick={() => onGoalAction(goal.session_id, 'cancel')}
                    >
                      <IconStop className="mr-1 h-3 w-3" />
                      {t('cancel')}
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
