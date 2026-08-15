import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  AlertCircle,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Clock,
  GitCompareArrows,
  MessageSquare,
  PlayCircle,
  RotateCcw,
  ShieldAlert,
  ShieldCheck,
  StopCircle,
  X,
} from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { fetchWithTimeout } from '@/lib/api';
import { ConfirmDialog } from '@/components/features/app-shell/confirm-dialog';
import { Button } from '@/components/primitives/button';
import {
  aggregate,
  extractBudgetTokens,
  extractCostUsd,
  extractMaxCostUsd,
  extractTotalTokens,
  fmtBudgetCost,
  fmtCost,
  fmtTokens,
  type TreeNode,
} from '@/lib/utils/subagentTree';
import { isNodeOvertime, useSubagentStore, type SubagentVerification, type TeammateMessageEntry } from '@/store/chat/useSubagentStore';
import useChatStore from '@/store/useChatStore';
import { NodeStream, STATUS_ICON_MAP, StatusIcon } from './subagent-stream';

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
  if (totalSec < 60) {return `${totalSec}s`;}
  const min = Math.floor(totalSec / 60);
  const sec = totalSec % 60;
  return `${min}m${sec}s`;
}

type DashboardTranslator = (key: string, values?: Record<string, string>) => string;

const VerificationBadge = ({ verification, t }: { verification: SubagentVerification; t: DashboardTranslator }) => {
  const [findingsOpen, setFindingsOpen] = useState(false);
  const findings = verification.findings ?? [];
  const passed = verification.passed;
  const Icon = passed ? ShieldCheck : ShieldAlert;

  const badgeClass = passed
    ? 'bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-400 border-green-200 dark:border-green-800'
    : 'bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-400 border-red-200 dark:border-red-800';

  const title = t(passed ? 'verificationPassedTitle' : 'verificationFailedTitle', {
    rounds: String(verification.rounds),
    maxRounds: String(verification.max_rounds),
    confidence: verification.confidence,
  });

  return (
    <>
      <button
        type="button"
        data-testid="subagent-verification-badge"
        data-verification-passed={passed}
        onClick={() => (findings.length > 0 ? setFindingsOpen((open) => !open) : undefined)}
        className={`inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[10px] font-medium leading-none ${badgeClass} ${
          findings.length > 0 ? 'cursor-pointer' : 'cursor-default'
        }`}
        title={title}
      >
        <Icon className="w-3 h-3 shrink-0" />
        {t(passed ? 'verificationPassed' : 'verificationFailed')}
        {verification.max_rounds > 1 && (
          <span className="tabular-nums opacity-80">
            {verification.rounds}/{verification.max_rounds}
          </span>
        )}
      </button>
      {findingsOpen && findings.length > 0 && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-2 py-1 text-[10px] text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300">
          <div className="mb-0.5 font-medium">{t('verificationFindings')}</div>
          <ul className="flex flex-col gap-0.5">
            {findings.map((finding, index) => (
              <li key={index} className="truncate" title={finding.description}>
                <span className="font-semibold uppercase">{finding.severity}</span>: {finding.description}
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
};

function formatRole(role: string | undefined, t: DashboardTranslator): string {
  if (role === 'orchestrator') {return t('roleOrchestrator');}
  if (role === 'leaf') {return t('roleLeaf');}
  return role || '';
}

function formatScope(scope: string | undefined, t: DashboardTranslator): string {
  if (scope === 'orchestrator') {return t('scopeOrchestrator');}
  if (scope === 'leaf') {return t('scopeLeaf');}
  return scope || '';
}

type TreeNodeProps = {
  node: TreeNode;
  chatId: string;
  setOpen: (open: boolean) => void;
};

export const SubagentTreeNode = ({ node, chatId, setOpen }: TreeNodeProps) => {
  const t = useTranslations('subagentDashboard');
  const [expanded, setExpanded] = useState(true);
  const [steerMessage, setSteerMessage] = useState('');
  const [showSteerInput, setShowSteerInput] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);

  const [elapsedMs, setElapsedMs] = useState(0);
  const isRunningNode = node.status === 'running';
  useEffect(() => {
    if (!isRunningNode || !node.startedAt) {return;}
    setElapsedMs(Date.now() - node.startedAt);
    const timer = setInterval(() => setElapsedMs(Date.now() - node.startedAt!), 1000);
    return () => clearInterval(timer);
  }, [isRunningNode, node.startedAt]);

  const overtime = isNodeOvertime(node);

  const handleCancel = useCallback(async () => {
    try {
      const res = await fetchWithTimeout(`/chats/${chatId}/subagents/${node.task_id}/cancel`, { method: 'POST' });
      if (!res.ok && res.status !== 404) {
        const body = await res.json().catch(() => ({}));
        toast.error(body.message || t('cancelFailed'));
        return;
      }
      // 404 表示该 subagent 已不在后端活跃列表中（已被清理或并发取消），
      // 从用户视角等同于取消成功，应同步前端状态。
      useSubagentStore.getState().completeNode(node.task_id, 'cancelled');
      toast.success(t('cancelSuccess'));
    } catch {
      toast.error(t('cancelNetworkError'));
    }
  }, [chatId, node.task_id, t]);

  const handleSteer = useCallback(async () => {
    if (!steerMessage.trim()) {return;}
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

  const handleReinitiate = useCallback(() => {
    const description = node.description || node.agent_type;
    useChatStore.getState().setInputMessage(description);
    setOpen(false);
    toast.success(t('reinitiateSuccess'));
  }, [node.description, node.agent_type, setOpen, t]);

  const isRunning = node.status === 'running';
  const isCheckpoint = node.status === 'checkpoint';
  const isInterrupted = node.status === 'interrupted';
  const isPendingApproval = node.status === 'pending_approval';
  const hasChildren = !!node.children?.length;

  const handleJumpToApproval = useCallback(() => {
    const cards = document.querySelectorAll(`[data-subagent-task-id="${node.task_id}"]`);
    if (cards && cards.length > 0) {
      const card = cards[cards.length - 1];
      card.scrollIntoView({ behavior: 'smooth', block: 'center' });
      card.classList.add('ring-2', 'ring-primary', 'ring-offset-2', 'transition-all', 'duration-500');
      setTimeout(() => card.classList.remove('ring-2', 'ring-primary', 'ring-offset-2'), 2000);
      setOpen(false);
    } else {
      toast.error(t('approvalCardNotFound'));
    }
  }, [node.task_id, setOpen, t]);

  return (
    <div
      data-subagent-tree-id={node.task_id}
      className="flex flex-col gap-2 my-2 ml-4 border-l pl-2 border-gray-200 dark:border-gray-800"
    >
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
          <span
            className={cn(
              'shrink-0 text-[11px] font-medium',
              STATUS_ICON_MAP[node.status]?.className ?? 'text-muted-foreground',
            )}
          >
            {t(`statusLabel.${node.status}`)}
          </span>
          <div className="flex flex-col flex-1 min-w-0">
            <span className="font-medium truncate" title={node.description || node.agent_type}>
              {node.description || node.agent_type}
              <AggregateBadge node={node} />
            </span>
            <div className="flex items-center gap-2 text-xs text-gray-500 flex-wrap">
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
              {node.verification && (
                <VerificationBadge verification={node.verification} t={t} />
              )}
              {(() => {
                const costUsd = extractCostUsd(node);
                const maxCostUsd = extractMaxCostUsd(node);
                if (costUsd <= 0) {return null;}
                return (
                  <span
                    className="rounded-full bg-green-50 px-1.5 py-0.5 text-[10px] font-medium text-green-700 dark:bg-green-900/30 dark:text-green-400 border border-green-200 dark:border-green-800"
                    title={maxCostUsd > 0 ? t('costBudgetTitle', { used: fmtBudgetCost(costUsd, 0), limit: `$${maxCostUsd.toFixed(2)}` }) : undefined}
                  >
                    {fmtBudgetCost(costUsd, maxCostUsd)}
                  </span>
                );
              })()}
              {node.effective_model && (
                <span className="truncate max-w-[8rem]" title={node.effective_model}>
                  {node.effective_model}
                </span>
              )}
              {(() => {
                const totalTokens = extractTotalTokens(node);
                if (totalTokens <= 0) {return null;}
                const budgetTokens = extractBudgetTokens(node);
                if (budgetTokens > 0) {
                  return (
                    <span className="tabular-nums shrink-0" title={t('tokenBudgetTitle', { used: totalTokens.toLocaleString('en-US'), limit: budgetTokens.toLocaleString('en-US') })}>
                      {fmtTokens(totalTokens)}/{fmtTokens(budgetTokens)} tok
                    </span>
                  );
                }
                return (
                  <span className="tabular-nums shrink-0">
                    {totalTokens.toLocaleString('en-US')} tok
                  </span>
                );
              })()}
              <span className="truncate">{node.last_tool || t('processing')}</span>
              {Number.isFinite(node.progress) && <span>{Math.round(node.progress)}%</span>}
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
              variant="outline"
              size="sm"
              className="h-7 text-xs px-2 border-purple-300 text-purple-600 hover:bg-purple-50 hover:text-purple-700 dark:border-purple-800 dark:text-purple-400 dark:hover:bg-purple-900/20 dark:hover:text-purple-300"
              onClick={handleReinitiate}
              title={t('reinitiateTitle')}
            >
              <RotateCcw className="w-3.5 h-3.5 mr-1" />
              {t('reinitiateAction')}
            </Button>
          )}
          {isPendingApproval && (
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

      {node.stale && !node.staleDismissed && (
        <div className="flex items-start gap-2 p-2 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 rounded-full text-xs text-red-800 dark:text-red-200">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="font-medium">{t('staleTitle')}</p>
            <p className="mt-0.5 text-red-700 dark:text-red-300">
              {t('staleDescription', {
                duration: String(Math.round((node.staleDurationSeconds ?? 0) / 60)),
                tokens: String((node.wastedTokens ?? 0).toLocaleString()),
              })}
            </p>
          </div>
          <button
            onClick={() => useSubagentStore.getState().dismissStale(node.task_id)}
            className="text-red-500 hover:text-red-700 dark:hover:text-red-300 shrink-0 text-xs"
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

      {node.stream && node.stream.length > 0 && (
        <NodeStream stream={node.stream} isRunning={isRunningNode} />
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

const AggregateBadge = ({ node }: { node: TreeNode }) => {
  if (node.children.length === 0) {return null;}
  const agg = aggregate(node);
  if (agg.descendantCount === 0) {return null;}
  const parts: string[] = [`▸ ${agg.descendantCount}`];
  const cost = fmtCost(agg.totalCostUsd);
  if (cost) {parts.push(cost);}
  const tok = agg.totalTokens > 0 ? `${fmtTokens(agg.totalTokens)} tok` : '';
  if (tok) {parts.push(tok);}
  return (
    <span className="ml-1 text-[10px] text-muted-foreground/70 tabular-nums">
      {parts.join(' · ')}
    </span>
  );
};
