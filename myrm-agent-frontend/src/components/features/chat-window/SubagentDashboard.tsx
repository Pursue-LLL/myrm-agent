import React, { useState, useCallback, useRef, useMemo, useEffect } from 'react';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from '@/components/primitives/sheet';
import { Button } from '@/components/primitives/button';
import { ConfirmDialog } from '@/components/features/app-shell/confirm-dialog';
import { ScrollArea } from '@/components/primitives/scroll-area';
import {
  useSubagentStore,
  isNodeOvertime,
  type SubagentNode,
  type SubagentStatus,
} from '@/store/chat/useSubagentStore';
import useChatStore from '@/store/useChatStore';
import { useTranslations } from 'next-intl';
import {
  Network,
  PlayCircle,
  CheckCircle2,
  XCircle,
  AlertCircle,
  AlertTriangle,
  Loader2,
  MessageSquare,
  StopCircle,
  ChevronRight,
  ChevronDown,
  Clock,
  ShieldCheck,
  X,
  GitCompareArrows,
} from 'lucide-react';
import { toast } from 'sonner';
import { fetchWithTimeout } from '@/lib/api';
import { normalizeTeammateEntry } from '@/lib/utils/teammateMessage';
import type { TeammateMessageEntry } from '@/store/chat/useSubagentStore';
import { AgentToolDiagnostics } from './AgentToolDiagnostics';

const STATUS_ICON_MAP: Record<SubagentStatus, { icon: typeof Loader2; className: string; spin?: boolean }> = {
  running: { icon: Loader2, className: 'text-blue-500', spin: true },
  verifying: { icon: ShieldCheck, className: 'text-amber-500', spin: true },
  completed: { icon: CheckCircle2, className: 'text-green-500' },
  failed: { icon: XCircle, className: 'text-red-500' },
  timed_out: { icon: AlertCircle, className: 'text-yellow-500' },
  cancelled: { icon: StopCircle, className: 'text-gray-500' },
  checkpoint: { icon: PlayCircle, className: 'text-purple-500' },
  interrupted: { icon: AlertTriangle, className: 'text-orange-500' },
};

const StatusIcon = ({ status }: { status: SubagentStatus }) => {
  const config = STATUS_ICON_MAP[status] ?? STATUS_ICON_MAP.running;
  const Icon = config.icon;
  return <Icon className={`w-4 h-4 ${config.className} ${config.spin ? 'animate-spin' : ''}`} />;
};

type TreeNodeProps = {
  node: SubagentNode & { children?: SubagentNode[] };
  chatId: string;
  setOpen: (open: boolean) => void;
};

type TeammateRowProps = {
  entry: TeammateMessageEntry;
  nodeTaskId: string;
  t: DashboardTranslator;
};

const TeammateMessageRow = ({ entry, nodeTaskId, t }: TeammateRowProps) => {
  const isOutbound = entry.from_task_id === nodeTaskId;
  const label = isOutbound
    ? t('teammateOutbound', { to: entry.to_task_id })
    : t('teammateInbound', { from: entry.from_task_id });
  return (
    <li className="truncate text-foreground/90" title={entry.body}>
      <span className="text-muted-foreground">{label}</span>
      <span className="ml-1">{entry.body}</span>
    </li>
  );
};

function formatElapsed(ms: number): string {
  const totalSec = Math.floor(ms / 1000);
  if (totalSec < 60) return `${totalSec}s`;
  const min = Math.floor(totalSec / 60);
  const sec = totalSec % 60;
  return `${min}m${sec}s`;
}

type DashboardTranslator = (key: string, values?: Record<string, string>) => string;

function formatRole(role: string | undefined, t: DashboardTranslator): string {
  if (role === 'orchestrator') return t('roleOrchestrator');
  if (role === 'leaf') return t('roleLeaf');
  return role || '';
}

function formatScope(scope: string | undefined, t: DashboardTranslator): string {
  if (scope === 'orchestrator') return t('scopeOrchestrator');
  if (scope === 'leaf') return t('scopeLeaf');
  return scope || '';
}

const SubagentTreeNode = ({ node, chatId, setOpen }: TreeNodeProps) => {
  const t = useTranslations('subagentDashboard');
  const [expanded, setExpanded] = useState(true);
  const [steerMessage, setSteerMessage] = useState('');
  const [showSteerInput, setShowSteerInput] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);

  const [elapsedMs, setElapsedMs] = useState(0);
  const isRunningNode = node.status === 'running';
  useEffect(() => {
    if (!isRunningNode || !node.startedAt) return;
    setElapsedMs(Date.now() - node.startedAt);
    const timer = setInterval(() => setElapsedMs(Date.now() - node.startedAt!), 1000);
    return () => clearInterval(timer);
  }, [isRunningNode, node.startedAt]);

  const overtime = isNodeOvertime(node);

  const handleCancel = useCallback(async () => {
    try {
      const res = await fetchWithTimeout(`/chats/${chatId}/subagents/${node.task_id}/cancel`, { method: 'POST' });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        toast.error(body.message || t('cancelFailed'));
        return;
      }
      useSubagentStore.getState().completeNode(node.task_id, 'cancelled');
      toast.success(t('cancelSuccess'));
    } catch {
      toast.error(t('cancelNetworkError'));
    }
  }, [chatId, node.task_id, t]);

  const handleSteer = useCallback(async () => {
    if (!steerMessage.trim()) return;
    try {
      const res = await fetchWithTimeout(`/chats/${chatId}/subagents/${node.task_id}/steer`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: steerMessage }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        toast.error(body.message || t('steerFailed'));
        return;
      }
      setSteerMessage('');
      setShowSteerInput(false);
      toast.success(t('steerSuccess'));
    } catch {
      toast.error(t('steerNetworkError'));
    }
  }, [chatId, node.task_id, steerMessage, t]);

  const handleResume = useCallback(async () => {
    try {
      const res = await fetchWithTimeout(`/chats/${chatId}/subagents/${node.task_id}/resume`, { method: 'POST' });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        toast.error(body.message || t('resumeFailed'));
        return;
      }
      useSubagentStore.getState().upsertNode({ task_id: node.task_id, status: 'running' });
      toast.success(t('resumeSuccess'));
    } catch {
      toast.error(t('resumeNetworkError'));
    }
  }, [chatId, node.task_id, t]);

  const isRunning = node.status === 'running';
  const isCheckpoint = node.status === 'checkpoint';
  const isInterrupted = node.status === 'interrupted';
  const hasChildren = !!node.children?.length;

  const handleJumpToApproval = useCallback(() => {
    // Find all approval cards for this task and jump to the last one (the most recent)
    const cards = document.querySelectorAll(`[data-subagent-task-id="${node.task_id}"]`);
    if (cards && cards.length > 0) {
      const card = cards[cards.length - 1];
      card.scrollIntoView({ behavior: 'smooth', block: 'center' });
      // Add a brief highlight effect
      card.classList.add('ring-2', 'ring-primary', 'ring-offset-2', 'transition-all', 'duration-500');
      setTimeout(() => card.classList.remove('ring-2', 'ring-primary', 'ring-offset-2'), 2000);
      setOpen(false); // Close dashboard
    } else {
      toast.error(t('approvalCardNotFound'));
    }
  }, [node.task_id, setOpen, t]);

  return (
    <div className="flex flex-col gap-2 my-2 ml-4 border-l pl-2 border-gray-200 dark:border-gray-800">
      <div className="flex items-center justify-between p-2 bg-gray-50 dark:bg-gray-900 rounded-full border text-sm">
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <button
            onClick={() => setExpanded(!expanded)}
            className="p-1 hover:bg-gray-200 dark:hover:bg-gray-800 rounded shrink-0"
            disabled={!hasChildren}
          >
            {hasChildren ? (
              expanded ? (
                <ChevronDown className="w-3 h-3" />
              ) : (
                <ChevronRight className="w-3 h-3" />
              )
            ) : (
              <div className="w-3 h-3" />
            )}
          </button>
          <StatusIcon status={node.status} />
          <div className="flex flex-col flex-1 min-w-0">
            <span className="font-medium truncate" title={node.description || node.agent_type}>
              {node.description || node.agent_type}
            </span>
            <div className="flex items-center gap-2 text-xs text-gray-500">
              {node.role && (
                <span className="rounded border border-gray-200 px-1.5 py-0.5 text-[10px] leading-none dark:border-gray-700">
                  {formatRole(node.role, t)}
                </span>
              )}
              {node.control_scope && (
                <span className="rounded border border-gray-200 px-1.5 py-0.5 text-[10px] leading-none dark:border-gray-700">
                  {formatScope(node.control_scope, t)}
                </span>
              )}
              {node.budget?.cost_usd !== undefined && 
               (typeof node.budget.cost_usd === 'number' || (typeof node.budget.cost_usd === 'string' && !isNaN(Number(node.budget.cost_usd)))) && (
                <span className="rounded-full bg-green-50 px-1.5 py-0.5 text-[10px] font-medium text-green-700 dark:bg-green-900/30 dark:text-green-400 border border-green-200 dark:border-green-800">
                  ${Number(node.budget.cost_usd).toFixed(3)}
                </span>
              )}
              <span className="truncate">{node.last_tool || t('processing')}</span>
              <span>{Math.round(node.progress)}%</span>
              {isRunningNode && node.startedAt && (
                <span className="flex items-center gap-0.5 shrink-0">
                  <Clock className="w-3 h-3" />
                  {formatElapsed(elapsedMs)}
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1 ml-2 shrink-0">
          {isRunning && (
            <>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 text-blue-500 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20"
                onClick={() => setShowSteerInput(!showSteerInput)}
                title={t('steerTitle')}
              >
                <MessageSquare className="w-4 h-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 text-red-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20"
                onClick={() => setCancelOpen(true)}
                title={t('cancelTitle')}
                data-testid="subagent-cancel-btn"
                data-task-id={node.task_id}
              >
                <StopCircle className="w-4 h-4" />
              </Button>
            </>
          )}
          {isCheckpoint && (
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 text-green-500 hover:text-green-600 hover:bg-green-50 dark:hover:bg-green-900/20"
              onClick={handleResume}
              title={t('resumeTitle')}
            >
              <PlayCircle className="w-4 h-4" />
            </Button>
          )}
          {isInterrupted && (
            <Button
              variant="default"
              size="sm"
              className="h-7 text-xs px-2 bg-amber-500 hover:bg-amber-600 text-white"
              onClick={handleJumpToApproval}
            >
              {t('reviewAction')}
            </Button>
          )}
        </div>
      </div>

      {overtime && (
        <div className="flex items-start gap-2 p-2 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 rounded-full text-xs text-amber-800 dark:text-amber-200">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="font-medium">{t('overtimeTitle')}</p>
            <p className="mt-0.5 text-amber-700 dark:text-amber-300">{t('overtimeDescription')}</p>
          </div>
          <button
            onClick={() => useSubagentStore.getState().dismissOvertime(node.task_id)}
            className="text-amber-500 hover:text-amber-700 dark:hover:text-amber-300 shrink-0 text-xs"
            title={t('dismiss')}
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {node.teammateMessages && node.teammateMessages.length > 0 && (
        <div className="mx-2 rounded-full border border-border/60 bg-muted/30 px-2 py-1.5 text-xs">
          <div className="mb-1 flex items-center gap-1.5 font-medium text-muted-foreground">
            <GitCompareArrows className="h-3.5 w-3.5 shrink-0" />
            {t('teammateMessagesTitle')}
          </div>
          <ul className="flex max-h-28 flex-col gap-1 overflow-y-auto">
            {node.teammateMessages.map((entry, idx) => (
              <TeammateMessageRow
                key={entry.message_id ?? `${entry.created_at}-${idx}`}
                entry={entry}
                nodeTaskId={node.task_id}
                t={t}
              />
            ))}
          </ul>
        </div>
      )}

      {node.policy_reason && (
        <div
          className="rounded-full border border-red-200 bg-red-50 px-2 py-1 text-xs text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300"
          title={node.policy_details || node.policy_reason}
        >
          {t('policyDenied')}: {node.policy_reason}
        </div>
      )}

      {showSteerInput && isRunning && (
        <div className="flex gap-2 items-center px-2">
          <input
            type="text"
            className="flex-1 text-sm bg-white dark:bg-gray-950 border border-gray-300 dark:border-gray-700 rounded-full px-2 py-1"
            placeholder={t('steerPlaceholder')}
            value={steerMessage}
            onChange={(e) => setSteerMessage(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSteer()}
            autoFocus
          />
          <Button size="sm" onClick={handleSteer}>
            {t('send')}
          </Button>
        </div>
      )}

      <ConfirmDialog
        open={cancelOpen}
        onOpenChange={setCancelOpen}
        title={t('cancelConfirmTitle')}
        description={t('cancelConfirmDescription')}
        confirmText={t('cancelConfirmAction')}
        cancelText={t('cancelConfirmCancel')}
        loadingText={t('cancelConfirmLoading')}
        variant="destructive"
        onConfirm={handleCancel}
      />

      {expanded && hasChildren && (
        <div className="flex flex-col">
          {node.children!.map((child) => (
            <SubagentTreeNode key={child.task_id} node={child} chatId={chatId} setOpen={setOpen} />
          ))}
        </div>
      )}
    </div>
  );
};

function buildTree(nodes: Record<string, SubagentNode>) {
  const entries = Object.values(nodes);
  if (entries.length === 0) return [];
  const rootNodes: (SubagentNode & { children: SubagentNode[] })[] = [];
  const map: Record<string, SubagentNode & { children: SubagentNode[] }> = {};
  entries.forEach((n) => {
    map[n.task_id] = { ...n, children: [] };
  });
  entries.forEach((n) => {
    if (n.parent_task_id && map[n.parent_task_id]) {
      map[n.parent_task_id].children.push(map[n.task_id]);
    } else {
      rootNodes.push(map[n.task_id]);
    }
  });
  return rootNodes;
}

export const SubagentDashboard = () => {
  const t = useTranslations('subagentDashboard');
  const [open, setOpen] = useState(false);
  const [stopAllOpen, setStopAllOpen] = useState(false);
  const nodes = useSubagentStore((s) => s.nodes);
  const fissionBatch = useSubagentStore((s) => s.fissionBatch);
  const chatId = useChatStore((s) => s.chatId);
  const treeNodes = useMemo(() => buildTree(nodes), [nodes]);

  const runningCount = useMemo(() => Object.values(nodes).filter((n) => n.status === 'running').length, [nodes]);

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
  React.useEffect(() => {
    if (prevChatIdRef.current !== chatId) {
      prevChatIdRef.current = chatId;
      useSubagentStore.getState().clear();
    }
  }, [chatId]);

  React.useEffect(() => {
    if (!chatId) return;
    const handleSseEvent = (event: Event) => {
      const customEvent = event as CustomEvent<{ chat_id?: string; tree?: SubagentNode[] }>;
      if (customEvent.detail?.chat_id === chatId && Array.isArray(customEvent.detail?.tree)) {
        useSubagentStore.getState().setNodes(customEvent.detail.tree);
      }
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

  React.useEffect(() => {
    if (!chatId || !open) return;
    const fetchSubagents = async () => {
      try {
        const res = await fetchWithTimeout(`/chats/${chatId}/subagents`);
        const json = await res.json();
        if (json.data && Array.isArray(json.data)) {
          useSubagentStore.getState().setNodes(json.data);
        }
      } catch (e) {
        console.error(t('fetchFailed'), e);
      }
    };
    fetchSubagents();
  }, [chatId, open, t]);

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
            </div>
            {runningCount > 0 && (
              <Button variant="destructive" size="sm" className="shrink-0 gap-2" onClick={() => setStopAllOpen(true)}>
                <StopCircle className="w-4 h-4" />
                {t('stopAll')}
              </Button>
            )}
          </div>
        </SheetHeader>
        <ScrollArea className="flex-1 p-4">
          <div className="flex flex-col pb-10">
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
            {treeNodes.map((node) => (
              <SubagentTreeNode key={node.task_id} node={node} chatId={chatId || ''} setOpen={setOpen} />
            ))}
          </div>
        </ScrollArea>
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
