import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { ArrowUpDown, Filter, ListTree, Loader2, Network, PauseCircle, PlayCircle, StopCircle } from 'lucide-react';
import { toast } from 'sonner';
import { fetchWithTimeout } from '@/lib/api';
import { ConfirmDialog } from '@/components/features/app-shell/confirm-dialog';
import { Button } from '@/components/primitives/button';
import { ScrollArea } from '@/components/primitives/scroll-area';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from '@/components/primitives/sheet';
import { normalizeTeammateEntry } from '@/lib/utils/teammateMessage';
import {
  buildTree,
  filterNodes,
  flattenTree,
  fmtCost,
  sortNodes,
  treeTotals,
  type FilterMode,
  type SortMode,
  type TreeNode,
} from '@/lib/utils/subagentTree';
import { useSubagentStore, type SubagentNode } from '@/store/chat/useSubagentStore';
import useChatStore from '@/store/useChatStore';
import { AgentToolDiagnostics } from '../AgentToolDiagnostics';
import AgentWorkMap from './AgentWorkMap';
import { MiniGantt } from './subagent-gantt';
import { SubagentTreeNode } from './subagent-tree';

// ── Sort/Filter Controls ─────────────────────────────────────────────

const SORT_OPTIONS: { value: SortMode; labelKey: string }[] = [
  { value: 'spawn', labelKey: 'sortSpawn' },
  { value: 'busiest', labelKey: 'sortBusiest' },
  { value: 'slowest', labelKey: 'sortSlowest' },
  { value: 'status', labelKey: 'sortStatus' },
];

const FILTER_OPTIONS: { value: FilterMode; labelKey: string }[] = [
  { value: 'all', labelKey: 'filterAll' },
  { value: 'running', labelKey: 'filterRunning' },
  { value: 'failed', labelKey: 'filterFailed' },
  { value: 'leaf', labelKey: 'filterLeaf' },
];

const SortFilterBar = ({
  sort, onSortChange, filter, onFilterChange, t,
}: {
  sort: SortMode;
  onSortChange: (s: SortMode) => void;
  filter: FilterMode;
  onFilterChange: (f: FilterMode) => void;
  t: (key: string) => string;
}) => (
  <div className="flex items-center gap-1.5 flex-wrap">
    <ArrowUpDown className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
    {SORT_OPTIONS.map((opt) => (
      <button
        key={opt.value}
        onClick={() => onSortChange(opt.value)}
        className={`px-2 py-0.5 text-[11px] rounded-full border transition-colors ${
          sort === opt.value
            ? 'bg-primary text-primary-foreground border-primary'
            : 'bg-transparent text-muted-foreground border-border/50 hover:bg-muted'
        }`}
      >
        {t(opt.labelKey)}
      </button>
    ))}
    <span className="mx-1 text-border">|</span>
    <Filter className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
    {FILTER_OPTIONS.map((opt) => (
      <button
        key={opt.value}
        onClick={() => onFilterChange(opt.value)}
        className={`px-2 py-0.5 text-[11px] rounded-full border transition-colors ${
          filter === opt.value
            ? 'bg-primary text-primary-foreground border-primary'
            : 'bg-transparent text-muted-foreground border-border/50 hover:bg-muted'
        }`}
      >
        {t(opt.labelKey)}
      </button>
    ))}
  </div>
);

// ── Header Summary ───────────────────────────────────────────────────

const HeaderSummary = ({ nodes, t }: { nodes: TreeNode[]; t: (key: string) => string }) => {
  const totals = useMemo(() => treeTotals(nodes), [nodes]);
  if (totals.totalAgents === 0) return null;

  const parts: string[] = [];
  parts.push(`${totals.totalAgents} ${t('agents')}`);
  if (totals.activeCount > 0) parts.push(`${totals.activeCount} ${t('active')}`);
  if (totals.failedCount > 0) parts.push(`${totals.failedCount} ${t('failed')}`);
  const cost = fmtCost(totals.totalCostUsd);
  if (cost) parts.push(cost);
  if (totals.modelMix.length > 0) {
    parts.push(totals.modelMix.map((m) => `${m.model}×${m.count}`).join(' '));
  }

  return (
    <div className="text-[11px] text-muted-foreground mt-0.5">
      {parts.join(' · ')}
    </div>
  );
};

// ── View Tabs ───────────────────────────────────────────────────────

const ViewTab = ({
  active,
  onClick,
  icon: Icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: typeof Network;
  label: string;
}) => (
  <button
    onClick={onClick}
    className={`flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-full border transition-colors ${
      active
        ? 'bg-primary text-primary-foreground border-primary'
        : 'bg-transparent text-muted-foreground border-border/50 hover:bg-muted'
    }`}
  >
    <Icon className="w-3.5 h-3.5" />
    {label}
  </button>
);

export const SubagentDashboard = ({ chatId: chatIdProp }: { chatId?: string }) => {
  const t = useTranslations('subagentDashboard');
  const [open, setOpen] = useState(false);
  const [stopAllOpen, setStopAllOpen] = useState(false);
  const [delegationPaused, setDelegationPaused] = useState(false);
  const [sortMode, setSortMode] = useState<SortMode>('spawn');
  const [filterMode, setFilterMode] = useState<FilterMode>('all');
  const [viewMode, setViewMode] = useState<'tree' | 'canvas'>('tree');

  const handleCanvasNodeClick = useCallback(
    (taskId: string) => {
      setViewMode('tree');
      requestAnimationFrame(() => {
        const el = document.querySelector(`[data-subagent-tree-id="${taskId}"]`);
        if (el instanceof HTMLElement) {
          el.scrollIntoView({ behavior: 'smooth', block: 'center' });
          el.classList.add('ring-2', 'ring-primary', 'ring-offset-2', 'rounded-lg', 'transition-all');
          setTimeout(() => el.classList.remove('ring-2', 'ring-primary', 'ring-offset-2', 'rounded-lg'), 2000);
        } else {
          toast.error(t('canvasLocateFail'));
        }
      });
    },
    [t],
  );
  const nodes = useSubagentStore((s) => s.nodes);
  const fissionBatch = useSubagentStore((s) => s.fissionBatch);
  const storeChatId = useChatStore((s) => s.chatId);
  const chatId = chatIdProp ?? storeChatId;
  const treeNodes = useMemo(() => buildTree(nodes), [nodes]);

  const displayNodes = useMemo(() => {
    const sorted = sortNodes(treeNodes, sortMode);
    return filterNodes(sorted, filterMode);
  }, [treeNodes, sortMode, filterMode]);

  const flatNodes = useMemo(() => flattenTree(treeNodes), [treeNodes]);

  const runningCount = useMemo(() => Object.values(nodes).filter((n) => n.status === 'running').length, [nodes]);

  const fetchSubagents = useCallback(async () => {
    if (!chatId) return;
    try {
      const res = await fetchWithTimeout(`/chats/${chatId}/subagents`);
      const json = await res.json();
      if (json.data && Array.isArray(json.data)) {
        useSubagentStore.getState().setNodes(json.data);
      }
    } catch (e) {
      console.error(t('fetchFailed'), e);
    }
  }, [chatId, t]);

  const fetchDelegationPauseStatus = useCallback(async () => {
    if (!chatId) return;
    try {
      const res = await fetchWithTimeout(`/chats/${chatId}/subagents/delegation/status`);
      const json = await res.json();
      setDelegationPaused(Boolean(json.data?.paused));
    } catch {
      // non-blocking
    }
  }, [chatId]);

  const handleToggleDelegationPause = useCallback(async () => {
    if (!chatId) return;
    const endpoint = delegationPaused ? 'resume' : 'pause';
    try {
      const res = await fetchWithTimeout(`/chats/${chatId}/subagents/delegation/${endpoint}`, { method: 'POST' });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        toast.error(body.message || t(delegationPaused ? 'delegationResumeFailed' : 'delegationPauseFailed'));
        return;
      }
      setDelegationPaused(!delegationPaused);
      toast.success(t(delegationPaused ? 'delegationResumeSuccess' : 'delegationPauseSuccess'));
    } catch {
      toast.error(t(delegationPaused ? 'delegationResumeNetworkError' : 'delegationPauseNetworkError'));
    }
  }, [chatId, delegationPaused, t]);

  const handleStopAll = useCallback(async () => {
    if (!chatId) return;
    try {
      const res = await fetchWithTimeout(`/chats/${chatId}/subagents/cancel-all`, { method: 'POST' });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        toast.error(body.message || t('stopAllFailed'));
        return;
      }
      const runningIds = Object.values(useSubagentStore.getState().nodes)
        .filter((node) => node.status === 'running')
        .map((node) => node.task_id);
      for (const taskId of runningIds) {
        useSubagentStore.getState().completeNode(taskId, 'cancelled');
      }
      toast.success(t('stopAllSuccess'));
    } catch {
      toast.error(t('stopAllNetworkError'));
    }
  }, [chatId, t]);

  const prevChatIdRef = useRef(chatId);
  useEffect(() => {
    const prev = prevChatIdRef.current;
    if (prev !== chatId) {
      if (prev && chatId && prev !== chatId) {
        useSubagentStore.getState().clear();
      }
      prevChatIdRef.current = chatId;
    }
  }, [chatId]);

  useEffect(() => {
    if (!chatId) return;
    const handleSseEvent = (event: Event) => {
      const customEvent = event as CustomEvent<{ chat_id?: string; tree?: SubagentNode[] }>;
      if (customEvent.detail?.chat_id && customEvent.detail.chat_id !== chatId) {
        return;
      }
      if (Array.isArray(customEvent.detail?.tree)) {
        useSubagentStore.getState().setNodes(customEvent.detail.tree);
        return;
      }
      void fetchSubagents();
    };
    const handleTeammateEvent = (event: Event) => {
      const customEvent = event as CustomEvent<{
        chat_id?: string;
        message?: Record<string, string | number>;
      }>;
      if (customEvent.detail?.chat_id !== chatId) return;
      const msg = customEvent.detail?.message;
      if (!msg?.from_task_id || !msg?.to_task_id) return;
      useSubagentStore.getState().appendTeammateMessage(normalizeTeammateEntry(msg as Record<string, string | number>));
    };
    window.addEventListener('subagents_updated', handleSseEvent);
    window.addEventListener('teammate_message', handleTeammateEvent);
    return () => {
      window.removeEventListener('subagents_updated', handleSseEvent);
      window.removeEventListener('teammate_message', handleTeammateEvent);
    };
  }, [chatId]);

  useEffect(() => {
    if (!chatId) return;
    void fetchDelegationPauseStatus();
  }, [chatId, open, fetchDelegationPauseStatus]);

  useEffect(() => {
    if (!chatId) return;
    void fetchSubagents();
    const poll = window.setInterval(() => {
      if (Object.keys(useSubagentStore.getState().nodes).length > 0) {
        window.clearInterval(poll);
        return;
      }
      void fetchSubagents();
    }, 2000);
    const stopPoll = window.setTimeout(() => window.clearInterval(poll), 30_000);
    return () => {
      window.clearInterval(poll);
      window.clearTimeout(stopPoll);
    };
  }, [chatId, open, fetchSubagents]);

  if (treeNodes.length === 0 && !(fissionBatch && fissionBatch.total > 0)) return null;

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button
          data-testid="subagent-dashboard-trigger"
          variant={runningCount > 0 ? 'default' : 'outline'}
          size="sm"
          className="fixed top-16 right-4 z-50 shadow-md gap-2 max-sm:left-4 max-sm:right-4 max-sm:w-[calc(100vw-2rem)]"
        >
          {runningCount > 0 ? <Loader2 className="w-4 h-4 animate-spin" /> : <Network className="w-4 h-4" />}
          <span>{runningCount > 0 ? t('activeCount', { count: runningCount }) : t('dashboardButton')}</span>
        </Button>
      </SheetTrigger>
      <SheetContent
        data-testid="subagent-dashboard-panel"
        className="flex w-full max-w-[100vw] flex-col p-0 sm:w-[540px] sm:max-w-[540px]"
      >
        <SheetHeader className="p-6 pb-2 border-b">
          <div className="flex items-start justify-between gap-3">
            <div>
              <SheetTitle className="flex items-center gap-2">
                <Network className="w-5 h-5 text-primary" />
                {t('title')}
                <div className="ml-2 border-l pl-2 border-border/50 h-5 flex items-center">
                  <AgentToolDiagnostics agentId="base_agent" />
                </div>
              </SheetTitle>
              <SheetDescription>{t('description')}</SheetDescription>
              <HeaderSummary nodes={treeNodes} t={t} />
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <Button
                variant={delegationPaused ? 'secondary' : 'outline'}
                size="sm"
                className="gap-2"
                onClick={() => void handleToggleDelegationPause()}
                data-testid="delegation-pause-toggle"
              >
                {delegationPaused ? <PlayCircle className="w-4 h-4" /> : <PauseCircle className="w-4 h-4" />}
                {delegationPaused ? t('delegationResumeButton') : t('delegationPauseButton')}
              </Button>
              {runningCount > 0 && (
              <Button variant="destructive" size="sm" className="gap-2" onClick={() => setStopAllOpen(true)}>
                <StopCircle className="w-4 h-4" />
                {t('stopAll')}
              </Button>
              )}
            </div>
          </div>
        </SheetHeader>
        <div className="flex items-center gap-1.5 px-4 pt-3 pb-2 border-b border-border/30">
          <ViewTab active={viewMode === 'tree'} onClick={() => setViewMode('tree')} icon={ListTree} label={t('treeTab')} />
          <ViewTab active={viewMode === 'canvas'} onClick={() => setViewMode('canvas')} icon={Network} label={t('canvasTab')} />
        </div>
        {viewMode === 'canvas' ? (
          <div className="flex-1 min-h-0">
            <AgentWorkMap chatId={chatId || undefined} onNodeClick={handleCanvasNodeClick} />
          </div>
        ) : (
        <ScrollArea className="flex-1 p-4">
          <div className="flex flex-col pb-10">
            {Object.keys(nodes).length > 1 && (
              <div className="mb-3 pb-2 border-b border-border/30">
                <SortFilterBar
                  sort={sortMode}
                  onSortChange={setSortMode}
                  filter={filterMode}
                  onFilterChange={setFilterMode}
                  t={t}
                />
              </div>
            )}
            <MiniGantt nodes={flatNodes} t={t} />
            {fissionBatch && fissionBatch.total > 0 && (
              <div
                className={`mb-4 rounded-lg border p-3 text-sm ${
                  fissionBatch.failed > 0 ? 'border-amber-500/30 bg-amber-500/5' : 'border-primary/20 bg-primary/5'
                }`}
              >
                <div className="font-medium text-foreground">{t('swarmFissionGroup')}</div>
                <div className="mt-1 text-muted-foreground">
                  {fissionBatch.partial
                    ? t('swarmFissionPartialProgress', {
                        completed: String(fissionBatch.completed),
                        failed: String(fissionBatch.failed),
                        total: String(fissionBatch.total),
                      })
                    : t('swarmFissionProgress', {
                        completed: String(fissionBatch.completed),
                        total: String(fissionBatch.total),
                      })}
                  {fissionBatch.active ? (
                    <Loader2 className="ml-2 inline h-3.5 w-3.5 animate-spin text-primary" />
                  ) : null}
                </div>
              </div>
            )}
            {displayNodes.map((node) => (
              <SubagentTreeNode key={node.task_id} node={node} chatId={chatId || ''} setOpen={setOpen} />
            ))}
          </div>
        </ScrollArea>
        )}
      </SheetContent>
      <ConfirmDialog
        open={stopAllOpen}
        onOpenChange={setStopAllOpen}
        title={t('stopAllConfirmTitle')}
        description={t('stopAllConfirmDescription')}
        confirmText={t('stopAllConfirmAction')}
        cancelText={t('cancelConfirmCancel')}
        loadingText={t('stopAllConfirmLoading')}
        variant="destructive"
        onConfirm={handleStopAll}
      />
    </Sheet>
  );
};

export default SubagentDashboard;
