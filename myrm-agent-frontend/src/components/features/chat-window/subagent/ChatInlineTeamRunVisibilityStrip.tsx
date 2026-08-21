'use client';

import React, { useMemo, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { ChevronRight, ExternalLink, Users } from 'lucide-react';
import { useSubagentStore, type SubagentNode } from '@/store/chat/useSubagentStore';
import { AgentAvatar } from '@/components/agent/AgentAvatar';
import { STATUS_ICON_MAP } from './SubagentStream';
import { cn } from '@/lib/utils';

interface ChatInlineTeamRunVisibilityStripProps {
  className?: string;
  onOpenDashboard?: () => void;
}

export function ChatInlineTeamRunVisibilityStrip({
  className,
  onOpenDashboard,
}: ChatInlineTeamRunVisibilityStripProps) {
  const t = useTranslations('subagentDashboard');
  const nodes = useSubagentStore((s) => s.nodes);

  const nodeList = useMemo(() => Object.values(nodes), [nodes]);

  const activeNodes = useMemo(
    () =>
      nodeList.filter(
        (n) => n.status === 'running' || n.status === 'verifying' || n.status === 'pending_approval',
      ),
    [nodeList],
  );

  const totalCount = nodeList.length;
  const activeCount = activeNodes.length;

  const handleOpen = useCallback(() => {
    if (onOpenDashboard) {
      onOpenDashboard();
    } else {
      window.dispatchEvent(new CustomEvent('open_subagent_dashboard'));
    }
  }, [onOpenDashboard]);

  if (activeCount === 0 && totalCount === 0) {
    return null;
  }

  // If no active nodes but have completed/failed, only show when there are active nodes to minimize intrusion,
  // or show summary if there are active nodes.
  if (activeCount === 0) {
    return null;
  }

  const visibleAvatars = activeNodes.slice(0, 3);
  const remainingCount = activeCount - visibleAvatars.length;

  // Find latest active step or description
  const primaryActiveNode = activeNodes[activeNodes.length - 1];
  const activeStepText =
    primaryActiveNode?.last_tool ||
    primaryActiveNode?.description ||
    primaryActiveNode?.agent_type ||
    t('inlineStripRunning');

  return (
    <div
      data-testid="chat-inline-team-run-visibility-strip"
      onClick={handleOpen}
      className={cn(
        'group flex items-center justify-between gap-3 px-3 py-2 mb-2 rounded-xl border border-border/80 bg-background/80 hover:bg-accent/40 backdrop-blur-md cursor-pointer transition-all duration-200 shadow-sm hover:shadow',
        className,
      )}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          handleOpen();
        }
      }}
      title={t('inlineStripOpenTooltip')}
    >
      <div className="flex items-center gap-2.5 min-w-0 flex-1">
        {/* Avatar Stack */}
        <div className="flex items-center -space-x-2 shrink-0">
          {visibleAvatars.map((node) => {
            const statusConfig = STATUS_ICON_MAP[node.status] ?? STATUS_ICON_MAP.running;
            return (
              <div
                key={node.task_id}
                className="relative inline-flex items-center justify-center ring-2 ring-background rounded-full"
                title={`${node.agent_type || node.role || 'Agent'} (${t(`statusLabel.${node.status}`)})`}
              >
                <AgentAvatar
                  name={node.agent_type || node.role || 'Agent'}
                  agentId={node.agent_type}
                  size="sm"
                  className="w-6 h-6 text-[10px]"
                />
                <span
                  className={cn(
                    'absolute -bottom-0.5 -right-0.5 w-2 h-2 rounded-full ring-1 ring-background',
                    statusConfig.className.replace('text-', 'bg-'),
                    statusConfig.spin ? 'animate-pulse' : '',
                  )}
                />
              </div>
            );
          })}
          {remainingCount > 0 && (
            <div className="flex items-center justify-center w-6 h-6 rounded-full bg-muted text-[10px] font-semibold text-muted-foreground ring-2 ring-background">
              +{remainingCount}
            </div>
          )}
        </div>

        {/* Text Details */}
        <div className="flex items-center gap-2 min-w-0 flex-1 text-xs">
          <span className="font-medium text-foreground shrink-0 flex items-center gap-1">
            <Users className="w-3.5 h-3.5 text-primary" />
            {t('inlineStripActiveSummary', { count: activeCount })}
          </span>
          <span className="text-muted-foreground/60 shrink-0">·</span>
          <span className="text-muted-foreground truncate" title={activeStepText}>
            {activeStepText}
          </span>
        </div>
      </div>

      {/* Right Action Hint */}
      <div className="flex items-center gap-1 text-xs text-muted-foreground group-hover:text-primary transition-colors shrink-0">
        <span className="hidden sm:inline font-medium">{t('inlineStripViewLive')}</span>
        <ChevronRight className="w-3.5 h-3.5" />
      </div>
    </div>
  );
}

export default ChatInlineTeamRunVisibilityStrip;
