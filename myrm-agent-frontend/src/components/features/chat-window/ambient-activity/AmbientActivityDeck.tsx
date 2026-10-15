import React from 'react';
import {
  Activity,
  Bot,
  ChevronDown,
  ChevronUp,
  Cpu,
  Eye,
  Sparkles,
} from 'lucide-react';
import {
  aggregateAmbientActivities,
  formatMicroActivitySummary,
} from './ambientActivityEngine';
import { BotActivityItem } from './ambientActivityTypes';
import { useAmbientActivityStore } from './useAmbientActivityStore';

interface AmbientActivityDeckProps {
  className?: string;
}

export const AmbientActivityDeck: React.FC<AmbientActivityDeckProps> = ({
  className = '',
}) => {
  const activitiesMap = useAmbientActivityStore((state) => state.activities);
  const isDeckCollapsed = useAmbientActivityStore(
    (state) => state.isDeckCollapsed,
  );
  const toggleDeckCollapse = useAmbientActivityStore(
    (state) => state.toggleDeckCollapse,
  );
  const toggleInspectionDrawer = useAmbientActivityStore(
    (state) => state.toggleInspectionDrawer,
  );
  const setSelectedActivity = useAmbientActivityStore(
    (state) => state.setSelectedActivity,
  );

  const activitiesList = Object.values(activitiesMap).sort(
    (a, b) => b.timestamp - a.timestamp,
  );
  const summary = aggregateAmbientActivities(activitiesList);

  if (activitiesList.length === 0) {
    return null;
  }

  const handleOpenAudit = (item?: BotActivityItem) => {
    if (item) {
      setSelectedActivity(item.id);
    }
    toggleInspectionDrawer(true);
  };

  return (
    <div
      data-testid="ambient-activity-deck"
      className={`mx-auto my-2 w-full max-w-2xl rounded-xl border border-primary/20 bg-background/80 p-3 text-xs shadow-xs backdrop-blur-md dark:bg-muted/20 ${className}`}
    >
      {/* 头部标题与控制区 */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-md bg-primary/10 text-primary">
            <Bot className="h-3.5 w-3.5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-foreground">
                环境态协同活动流
              </span>
              <span className="flex items-center gap-1 rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">
                <Activity className="h-2.5 w-2.5 animate-pulse" />
                <span>
                  {summary.activeAgentsCount} 个智能体后台协同中
                </span>
              </span>
            </div>
            <p className="mt-0.5 text-[11px] text-muted-foreground">
              共完成 {summary.totalExchangesCount} 次微通信 · 累计消耗{' '}
              {summary.totalTokenCost} Tokens · 机器互聊已自动免打扰静默折叠
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => {
              handleOpenAudit();
            }}
            aria-label="查看完整通信审计"
            className="flex items-center gap-1 rounded-md border border-border/60 bg-background/60 px-2 py-1 text-[11px] text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
          >
            <Eye className="h-3 w-3" />
            <span>穿透审计</span>
          </button>

          <button
            type="button"
            onClick={() => {
              toggleDeckCollapse();
            }}
            aria-label={isDeckCollapsed ? '展开活动流' : '折叠活动流'}
            className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
          >
            {isDeckCollapsed ? (
              <ChevronDown className="h-3.5 w-3.5" />
            ) : (
              <ChevronUp className="h-3.5 w-3.5" />
            )}
          </button>
        </div>
      </div>

      {/* 展开时的微日志列表 */}
      {!isDeckCollapsed && (
        <div className="mt-2.5 space-y-1.5 border-t border-border/30 pt-2">
          {activitiesList.slice(0, 5).map((act) => {
            let statusDot = 'bg-blue-500';
            if (act.status === 'completed') {
              statusDot = 'bg-emerald-500';
            } else if (act.status === 'failed') {
              statusDot = 'bg-red-500';
            }

            return (
              <button
                key={act.id}
                type="button"
                onClick={() => {
                  handleOpenAudit(act);
                }}
                className="group flex w-full cursor-pointer items-center justify-between rounded-lg px-2 py-1 hover:bg-muted/50 transition-colors text-left"
              >
                <div className="flex min-w-0 flex-1 items-center gap-2">
                  <span
                    className={`h-1.5 w-1.5 shrink-0 rounded-full ${statusDot}`}
                  />
                  <span className="truncate font-mono text-[11px] text-foreground/90">
                    {formatMicroActivitySummary(act)}
                  </span>
                </div>

                <div className="flex shrink-0 items-center gap-2 text-[10px] text-muted-foreground opacity-70 group-hover:opacity-100">
                  <span>{act.tokenCost} tok</span>
                  <Eye className="h-3 w-3 text-muted-foreground" />
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
};
