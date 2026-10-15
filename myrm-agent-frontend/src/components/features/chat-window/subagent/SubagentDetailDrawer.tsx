'use client';

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  AlertCircle,
  Bot,
  CheckCircle2,
  Clock,
  Code2,
  Coins,
  Copy,
  ExternalLink,
  FileCheck,
  FileText,
  HelpCircle,
  History,
  Layers,
  Link as LinkIcon,
  ListOrdered,
  Package,
  Play,
  RotateCcw,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Terminal,
  X,
  XCircle,
} from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/primitives/button';
import { ScrollArea } from '@/components/primitives/scroll-area';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/primitives/sheet';
import { Badge } from '@/components/primitives/badge';
import { fmtCost, fmtTokens, extractCostUsd, extractTotalTokens } from '@/lib/utils/subagent/subagentTree';
import type { SubagentNode, StreamEntry, TeammateMessageEntry } from '@/store/chat/useSubagentStore';
import { STATUS_ICON_MAP } from './SubagentStream';
import { SubagentViewportTab } from './SubagentViewportTab';
import { cn } from '@/lib/utils/classnameUtils';
import { REVEAL_ON_HOVER } from '@/lib/utils/a11y';

interface SubagentDetailDrawerProps {
  node: SubagentNode | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  chatId?: string;
}

type TabType = 'overview' | 'journal' | 'tool_calls' | 'messages' | 'replay' | 'viewport';

export const SubagentDetailDrawer: React.FC<SubagentDetailDrawerProps> = ({ node, open, onOpenChange, chatId }) => {
  const t = useTranslations('subagentDashboard');
  const commonT = useTranslations('common');
  const [activeTab, setActiveTab] = useState<TabType>('overview');
  const [replayStepIndex, setReplayStepIndex] = useState<number>(0);

  if (!node) {
    return null;
  }

  const statusConfig = STATUS_ICON_MAP[node.status] ?? STATUS_ICON_MAP.running;
  const StatusIcon = statusConfig.icon;
  const cost = fmtCost(extractCostUsd(node));
  const tokens = fmtTokens(extractTotalTokens(node));
  const stream = node.stream || [];
  const teammateMsgs = node.teammateMessages || node.teammate_messages || [];

  // Filter out tool calls
  const toolEntries = stream.filter((s: StreamEntry) => s.kind === 'tool');

  const handleCopy = (text: string, copiedMessage: string) => {
    navigator.clipboard.writeText(text);
    toast.success(copiedMessage);
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="w-full sm:max-w-xl md:max-w-2xl p-0 flex flex-col h-full bg-background border-l border-border"
        data-testid="subagent-detail-drawer"
      >
        <SheetHeader className="px-6 py-4 border-b border-border bg-muted/20">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="p-2 rounded-lg bg-primary/10 border border-primary/20 shrink-0">
                <Bot className="w-5 h-5 text-primary" />
              </div>
              <div className="min-w-0">
                <SheetTitle className="text-base font-bold truncate flex items-center gap-2">
                  <span>{node.agent_type || t('detailFallbackAgentType')}</span>
                  <Badge variant="outline" className="text-[10px] font-mono shrink-0">
                    {node.task_id.slice(0, 8)}
                  </Badge>
                </SheetTitle>
                <SheetDescription className="text-xs text-muted-foreground truncate">
                  {node.description || t('detailNoDescription')}
                </SheetDescription>
              </div>
            </div>

            <div className="flex items-center gap-1.5 shrink-0">
              <div
                className={`flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium border ${statusConfig.className} bg-background/80`}
              >
                <StatusIcon className={`w-3.5 h-3.5 ${statusConfig.spin ? 'animate-spin' : ''}`} />
                <span>{t(`statusLabel.${node.status}`)}</span>
              </div>
            </div>
          </div>

          {/* Quick Metrics Strip */}
          <div className="grid grid-cols-4 gap-2 mt-3 pt-3 border-t border-border/50 text-xs text-muted-foreground">
            <div>
              <span className="text-[10px] block opacity-70">{t('detailDuration')}</span>
              <span className="font-semibold text-foreground">
                {node.duration_seconds ? `${node.duration_seconds}s` : '—'}
              </span>
            </div>
            <div>
              <span className="text-[10px] block opacity-70">{t('detailTokens')}</span>
              <span className="font-semibold text-foreground">{tokens || '0'}</span>
            </div>
            <div>
              <span className="text-[10px] block opacity-70">{t('detailCost')}</span>
              <span className="font-semibold text-foreground">{cost || '—'}</span>
            </div>
            <div>
              <span className="text-[10px] block opacity-70">{commonT('model')}</span>
              <span className="font-semibold text-foreground truncate block">
                {node.effective_model || t('detailModelInherited')}
              </span>
            </div>
          </div>

          {/* Navigation Tabs */}
          <div className="flex items-center gap-1 mt-3 border-b border-border/40 pb-1">
            <button
              onClick={() => setActiveTab('overview')}
              className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                activeTab === 'overview' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted'
              }`}
            >
              {t('detailTabOverview')}
            </button>
            <button
              onClick={() => setActiveTab('journal')}
              className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                activeTab === 'journal' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted'
              }`}
            >
              {t('detailTabJournal', { count: stream.length })}
            </button>
            <button
              onClick={() => setActiveTab('tool_calls')}
              className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                activeTab === 'tool_calls'
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-muted'
              }`}
            >
              {t('detailTabTools', { count: toolEntries.length })}
            </button>
            <button
              onClick={() => setActiveTab('messages')}
              className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                activeTab === 'messages' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted'
              }`}
            >
              {t('detailTabMessages', { count: teammateMsgs.length })}
            </button>
            <button
              onClick={() => setActiveTab('replay')}
              className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                activeTab === 'replay' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted'
              }`}
            >
              {t('detailTabReplay')}
            </button>
            <button
              onClick={() => setActiveTab('viewport')}
              data-testid="subagent-drawer-tab-viewport"
              className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                activeTab === 'viewport' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted'
              }`}
            >
              {t('detailTabViewport')}
            </button>
          </div>
        </SheetHeader>

        <ScrollArea className="flex-1 p-6">
          {activeTab === 'overview' && (
            <div className="space-y-4">
              {node.handover_state && (
                <div className="p-3.5 rounded-lg border bg-blue-50/20 dark:bg-blue-950/20 border-blue-200/60 dark:border-blue-900/40 text-xs space-y-3">
                  <div className="flex items-center justify-between font-bold text-blue-950 dark:text-blue-200">
                    <div className="flex items-center gap-1.5">
                      <Sparkles className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                      <span>{t('detailHandoverTitle')}</span>
                    </div>
                    <Badge variant="outline" className="text-[10px] font-mono border-blue-300 dark:border-blue-800">
                      {t('detailHandoverBadge')}
                    </Badge>
                  </div>

                  {node.handover_state.summary && (
                    <div className="bg-background/80 dark:bg-background/40 p-2.5 rounded-md border border-border/50">
                      <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground block mb-1">
                        {t('detailExecutiveSummary')}
                      </span>
                      <p className="text-[12px] leading-relaxed text-foreground whitespace-pre-wrap">
                        {node.handover_state.summary}
                      </p>
                    </div>
                  )}

                  {node.handover_state.findings && node.handover_state.findings.length > 0 && (
                    <div>
                      <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground block mb-1.5">
                        {t('detailKeyFindings', { count: node.handover_state.findings.length })}
                      </span>
                      <div className="space-y-1.5">
                        {node.handover_state.findings.map((f, i) => {
                          const conf = (f.confidence || 'high').toLowerCase();
                          const confColor =
                            conf === 'high'
                              ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/20'
                              : conf === 'medium'
                                ? 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/20'
                                : 'bg-slate-500/10 text-slate-700 dark:text-slate-300 border-slate-500/20';

                          return (
                            <div
                              key={i}
                              className="p-2 rounded-md border bg-background/60 dark:bg-background/30 text-[11px] flex flex-col gap-1"
                            >
                              <div className="flex items-start justify-between gap-2">
                                <span className="font-medium text-foreground">{f.finding}</span>
                                <span
                                  className={`px-1.5 py-0.5 rounded text-[9px] uppercase font-mono font-bold border shrink-0 ${confColor}`}
                                >
                                  {f.confidence || 'HIGH'}
                                </span>
                              </div>
                              {f.evidence && (
                                <div className="flex items-center gap-1 font-mono text-[10px] text-muted-foreground bg-muted/40 px-1.5 py-0.5 rounded">
                                  <FileCheck className="w-3 h-3 text-muted-foreground shrink-0" />
                                  <span className="truncate">{f.evidence}</span>
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {((node.handover_state.artifact_refs && node.handover_state.artifact_refs.length > 0) ||
                    (node.handover_state.citations && node.handover_state.citations.length > 0)) && (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
                      {node.handover_state.artifact_refs && node.handover_state.artifact_refs.length > 0 && (
                        <div className="p-2 rounded-md border bg-background/50 dark:bg-background/20">
                          <span className="text-[10px] font-semibold text-muted-foreground flex items-center gap-1 mb-1">
                            <Package className="w-3 h-3 text-primary" /> {t('detailArtifacts')}
                          </span>
                          <div className="space-y-1">
                            {node.handover_state.artifact_refs.map((ref, idx) => (
                              <div
                                key={idx}
                                className="flex items-center justify-between gap-1 font-mono text-[10px] text-foreground bg-muted/30 px-1.5 py-0.5 rounded group"
                              >
                                <span className="truncate">{ref}</span>
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  aria-label={t('detailCopy')}
                                  onClick={() => handleCopy(ref, t('detailCopiedArtifactPath'))}
                                  className="h-5 px-1 opacity-60 group-hover:opacity-100"
                                >
                                  <Copy className="w-2.5 h-2.5" />
                                </Button>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {node.handover_state.citations && node.handover_state.citations.length > 0 && (
                        <div className="p-2 rounded-md border bg-background/50 dark:bg-background/20">
                          <span className="text-[10px] font-semibold text-muted-foreground flex items-center gap-1 mb-1">
                            <LinkIcon className="w-3 h-3 text-primary" /> {t('detailCitations')}
                          </span>
                          <div className="space-y-1">
                            {node.handover_state.citations.map((cite, idx) => (
                              <div
                                key={idx}
                                className="flex items-center justify-between gap-1 font-mono text-[10px] text-foreground bg-muted/30 px-1.5 py-0.5 rounded group"
                              >
                                <span className="truncate">{cite}</span>
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  aria-label={t('detailCopy')}
                                  onClick={() => handleCopy(cite, t('detailCopiedCitationUrl'))}
                                  className="h-5 px-1 opacity-60 group-hover:opacity-100"
                                >
                                  <Copy className="w-2.5 h-2.5" />
                                </Button>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {node.handover_state.task_completed && node.handover_state.task_completed.length > 0 && (
                    <div>
                      <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground block mb-1">
                        {t('detailCompletedChecklist')}
                      </span>
                      <ul className="space-y-0.5 list-disc list-inside text-[11px] text-muted-foreground">
                        {node.handover_state.task_completed.map((task, i) => (
                          <li key={i} className="text-foreground">
                            {task}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}

              {node.error && (
                <div className="p-3 rounded-lg bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900/60 text-red-700 dark:text-red-300 text-xs">
                  <div className="flex items-center gap-1.5 font-bold mb-1">
                    <XCircle className="w-4 h-4" />
                    <span>{t('detailErrorDiagnostic')}</span>
                  </div>
                  <pre className="font-mono text-[11px] whitespace-pre-wrap break-all overflow-x-auto bg-black/5 dark:bg-black/30 p-2 rounded">
                    {node.error}
                  </pre>
                </div>
              )}

              {node.verification && (
                <div
                  className={`p-3 rounded-lg border text-xs ${
                    node.verification.passed
                      ? 'bg-green-50 dark:bg-green-950/30 border-green-200 text-green-700 dark:text-green-300'
                      : 'bg-red-50 dark:bg-red-950/30 border-red-200 text-red-700 dark:text-red-300'
                  }`}
                >
                  <div className="flex items-center justify-between font-bold mb-1">
                    <div className="flex items-center gap-1.5">
                      {node.verification.passed ? (
                        <ShieldCheck className="w-4 h-4" />
                      ) : (
                        <ShieldAlert className="w-4 h-4" />
                      )}
                      <span>
                        {node.verification.passed ? t('detailVerificationPassed') : t('detailVerificationFailed')}
                      </span>
                    </div>
                    <span>
                      {t('detailVerificationRounds', {
                        rounds: node.verification.rounds,
                        maxRounds: node.verification.max_rounds,
                      })}
                    </span>
                  </div>
                  {node.verification.findings && node.verification.findings.length > 0 && (
                    <ul className="mt-2 space-y-1 list-disc list-inside text-[11px]">
                      {node.verification.findings.map((f, i) => (
                        <li key={i}>
                          <span className="font-semibold uppercase">{f.severity}</span>: {f.description}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              <div>
                <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
                  {t('detailTaskSpec')}
                </h4>
                <div className="relative p-3 rounded-lg border bg-muted/30 font-mono text-xs leading-relaxed group">
                  <p className="whitespace-pre-wrap break-words">{node.description}</p>
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={t('detailCopy')}
                    onClick={() => handleCopy(node.description, t('detailCopiedTaskDescription'))}
                    className={cn('absolute top-2 right-2 h-7 px-2 transition-opacity', REVEAL_ON_HOVER)}
                  >
                    <Copy className="w-3.5 h-3.5" />
                  </Button>
                </div>
              </div>

              <div>
                <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
                  {t('detailMetadata')}
                </h4>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className="p-2.5 rounded-lg border bg-muted/20">
                    <span className="text-muted-foreground text-[10px] block">{t('detailTaskId')}</span>
                    <span className="font-mono text-[11px] truncate block">{node.task_id}</span>
                  </div>
                  <div className="p-2.5 rounded-lg border bg-muted/20">
                    <span className="text-muted-foreground text-[10px] block">{t('detailParentTaskId')}</span>
                    <span className="font-mono text-[11px] truncate block">
                      {node.parent_task_id || t('detailRootTask')}
                    </span>
                  </div>
                  <div className="p-2.5 rounded-lg border bg-muted/20">
                    <span className="text-muted-foreground text-[10px] block">{t('detailRoleScope')}</span>
                    <span className="font-mono text-[11px] truncate block">
                      {node.role || node.control_scope || t('detailStandardLeaf')}
                    </span>
                  </div>
                  <div className="p-2.5 rounded-lg border bg-muted/20">
                    <span className="text-muted-foreground text-[10px] block">{t('detailProgress')}</span>
                    <span className="font-mono text-[11px] truncate block">
                      {node.progress}% ({node.status})
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'journal' && (
            <div className="space-y-2">
              {stream.length === 0 ? (
                <div className="py-8 text-center text-xs text-muted-foreground">{t('detailJournalEmpty')}</div>
              ) : (
                stream.map((entry: StreamEntry, idx: number) => (
                  <div
                    key={idx}
                    className={`p-2.5 rounded-lg border text-xs flex items-start gap-2 ${
                      entry.isError
                        ? 'bg-red-50/50 dark:bg-red-950/20 border-red-200'
                        : entry.kind === 'tool'
                          ? 'bg-blue-50/30 dark:bg-blue-950/10 border-blue-200/50'
                          : 'bg-muted/30 border-border/60'
                    }`}
                  >
                    <span className="font-mono text-[10px] text-muted-foreground/60 shrink-0 mt-0.5">#{idx + 1}</span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2 mb-0.5">
                        <span className="font-semibold capitalize text-[10px] text-primary">{entry.kind}</span>
                        {entry.durationMs && (
                          <span className="text-[10px] text-muted-foreground font-mono">
                            {entry.durationMs < 1000
                              ? `${entry.durationMs}ms`
                              : `${(entry.durationMs / 1000).toFixed(1)}s`}
                          </span>
                        )}
                      </div>
                      <p className="font-mono text-[11px] break-words whitespace-pre-wrap">{entry.text}</p>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}

          {activeTab === 'tool_calls' && (
            <div className="space-y-2">
              {toolEntries.length === 0 ? (
                <div className="py-8 text-center text-xs text-muted-foreground">{t('detailToolsEmpty')}</div>
              ) : (
                toolEntries.map((tool: StreamEntry, idx: number) => (
                  <div key={idx} className="p-3 rounded-lg border bg-muted/20 text-xs">
                    <div className="flex items-center justify-between mb-1.5">
                      <div className="flex items-center gap-1.5 font-bold text-foreground">
                        <Terminal className="w-3.5 h-3.5 text-primary" />
                        <span>{t('detailToolCall', { index: idx + 1 })}</span>
                      </div>
                      {tool.durationMs && (
                        <span className="text-[10px] font-mono text-muted-foreground">
                          {tool.durationMs < 1000 ? `${tool.durationMs}ms` : `${(tool.durationMs / 1000).toFixed(1)}s`}
                        </span>
                      )}
                    </div>
                    <pre className="font-mono text-[11px] bg-black/5 dark:bg-black/30 p-2 rounded overflow-x-auto whitespace-pre-wrap break-all">
                      {tool.text}
                    </pre>
                  </div>
                ))
              )}
            </div>
          )}

          {activeTab === 'messages' && (
            <div className="space-y-2">
              {teammateMsgs.length === 0 ? (
                <div className="py-8 text-center text-xs text-muted-foreground">{t('detailMessagesEmpty')}</div>
              ) : (
                teammateMsgs.map((msg: TeammateMessageEntry, idx: number) => {
                  const isOutbound = msg.from_task_id === node.task_id;
                  return (
                    <div
                      key={idx}
                      className={`p-2.5 rounded-lg border text-xs ${
                        isOutbound
                          ? 'bg-primary/5 border-primary/20 text-foreground ml-4'
                          : 'bg-muted/40 border-border mr-4'
                      }`}
                    >
                      <div className="flex items-center justify-between text-[10px] text-muted-foreground mb-1">
                        <span>
                          {isOutbound
                            ? t('teammateOutbound', { to: msg.to_task_id })
                            : t('teammateInbound', { from: msg.from_task_id })}
                        </span>
                        <span className="font-mono">{new Date(msg.created_at).toLocaleTimeString()}</span>
                      </div>
                      <p className="whitespace-pre-wrap break-words">{msg.body}</p>
                    </div>
                  );
                })
              )}
            </div>
          )}

          {activeTab === 'replay' && (
            <div className="space-y-4">
              <div className="p-3 rounded-lg border bg-muted/30">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold">
                    {t('detailReplayStep', {
                      current: stream.length > 0 ? replayStepIndex + 1 : 0,
                      total: stream.length,
                    })}
                  </span>
                  <div className="flex items-center gap-1">
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 text-xs px-2"
                      disabled={replayStepIndex <= 0}
                      onClick={() => setReplayStepIndex((prev) => Math.max(0, prev - 1))}
                    >
                      {commonT('previous')}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 text-xs px-2"
                      disabled={replayStepIndex >= stream.length - 1}
                      onClick={() => setReplayStepIndex((prev) => Math.min(stream.length - 1, prev + 1))}
                    >
                      {commonT('next')}
                    </Button>
                  </div>
                </div>

                {stream.length > 0 && stream[replayStepIndex] ? (
                  <div className="p-3 rounded border bg-background text-xs space-y-2">
                    <div className="flex items-center justify-between">
                      <Badge variant="secondary" className="text-[10px]">
                        {t('detailReplayKind', { kind: stream[replayStepIndex].kind })}
                      </Badge>
                      <span className="font-mono text-[10px] text-muted-foreground">
                        {t('detailReplayDuration', { ms: stream[replayStepIndex].durationMs || 0 })}
                      </span>
                    </div>
                    <pre className="font-mono text-[11px] whitespace-pre-wrap break-all p-2 bg-muted/40 rounded">
                      {stream[replayStepIndex].text}
                    </pre>
                  </div>
                ) : (
                  <div className="text-center text-xs text-muted-foreground py-4">{t('detailReplayEmpty')}</div>
                )}
              </div>
            </div>
          )}

          {activeTab === 'viewport' && <SubagentViewportTab node={node} chatId={chatId} />}
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
};

export default SubagentDetailDrawer;
