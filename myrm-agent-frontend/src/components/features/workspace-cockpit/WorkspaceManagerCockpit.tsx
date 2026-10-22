'use client';

/**
 * [INPUT]
 * ./workspaceCockpitTypes (POS: WorkspaceManagerCockpitProps, WorkspaceTaskItem)
 * ./useWorkspaceOfflineDigest (POS: useWorkspaceOfflineDigest)
 * ./WhileYouWereAwayDigest (POS: WhileYouWereAwayDigest)
 * ./GlobalFourSwimlanesDeck (POS: GlobalFourSwimlanesDeck)
 * ./ManagerConversationTray (POS: ManagerConversationTray)
 * @/lib/utils/classnameUtils (POS: cn helper)
 * lucide-react (POS: LayoutDashboard, RefreshCw, Search, Sparkles)
 *
 * [OUTPUT]
 * WorkspaceManagerCockpit: Top-level unified manager cockpit surface with offline digest and four swimlanes deck.
 *
 * [POS]
 * Primary surface for Personal Workspace Cockpit. Aligns with LoopX personal agent workspace console.
 */

import React, { useState, useMemo, useCallback } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { LayoutDashboard, RefreshCw, Search, Sparkles } from 'lucide-react';
import type { WorkspaceManagerCockpitProps } from './workspaceCockpitTypes';
import { useWorkspaceOfflineDigest } from './useWorkspaceOfflineDigest';
import WhileYouWereAwayDigest from './WhileYouWereAwayDigest';
import GlobalFourSwimlanesDeck from './GlobalFourSwimlanesDeck';
import ManagerConversationTray from './ManagerConversationTray';

export const WorkspaceManagerCockpit: React.FC<WorkspaceManagerCockpitProps> = ({
  tasks,
  onNavigateToChat,
  onApproveDecision,
  onRejectDecision,
  onRefresh,
  lastActiveTimestamp,
  className,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [isRefreshing, setIsRefreshing] = useState(false);

  const { summary, shouldShowDigest, dismissDigest } = useWorkspaceOfflineDigest(
    tasks,
    lastActiveTimestamp,
  );

  const filteredTasks = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) {
      return tasks;
    }
    return tasks.filter(
      (t) =>
        t.title.toLowerCase().includes(q) ||
        (t.agentName && t.agentName.toLowerCase().includes(q)) ||
        (t.latestOutputTail && t.latestOutputTail.toLowerCase().includes(q)),
    );
  }, [tasks, searchQuery]);

  const handleRefreshClick = useCallback(() => {
    if (onRefresh) {
      setIsRefreshing(true);
      onRefresh();
      setTimeout(() => setIsRefreshing(false), 500);
    }
  }, [onRefresh]);

  return (
    <div
      data-testid="workspace-manager-cockpit"
      className={cn(
        'relative flex flex-col w-full h-full p-4 md:p-6 bg-background text-foreground overflow-y-auto space-y-5',
        className,
      )}
    >
      {/* Cockpit Top Bar */}
      <header className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-border/60">
        <div className="flex items-center gap-2.5">
          <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-primary/15 text-primary">
            <LayoutDashboard className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-base font-bold text-foreground flex items-center gap-1.5">
              Personal Workspace Cockpit
              <span className="px-1.5 py-0.2 rounded text-[10px] font-semibold bg-primary/10 text-primary border border-primary/20">
                LoopX Engine
              </span>
            </h1>
            <p className="text-xs text-muted-foreground">
              Global mission control across autonomous agents, background probes, and scheduled runs.
            </p>
          </div>
        </div>

        {/* Search & Refresh Actions */}
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-muted-foreground absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              data-testid="cockpit-search-input"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Filter tasks, agents..."
              className="pl-8 pr-3 py-1.5 rounded-lg border border-input bg-background text-xs w-48 sm:w-60 focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>

          <button
            type="button"
            data-testid="cockpit-refresh-btn"
            onClick={handleRefreshClick}
            disabled={isRefreshing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border bg-background hover:bg-muted text-xs font-medium text-foreground transition-colors disabled:opacity-50"
            aria-label="Refresh workspace cockpit"
          >
            <RefreshCw className={cn('w-3.5 h-3.5', isRefreshing && 'animate-spin text-primary')} />
            <span className="hidden sm:inline">Refresh</span>
          </button>
        </div>
      </header>

      {/* "While You Were Away" Offline Digest Card */}
      {shouldShowDigest && (
        <WhileYouWereAwayDigest
          summary={summary}
          onDismiss={dismissDigest}
          onNavigateToTask={onNavigateToChat}
        />
      )}

      {/* 4 Swimlanes Mission Control Deck */}
      <main className="flex-1">
        <GlobalFourSwimlanesDeck
          tasks={filteredTasks}
          onNavigateToChat={onNavigateToChat}
          onApproveDecision={onApproveDecision}
          onRejectDecision={onRejectDecision}
        />
      </main>

      {/* Floating Manager Conversation Tray */}
      <ManagerConversationTray />
    </div>
  );
};

export default React.memo(WorkspaceManagerCockpit);
