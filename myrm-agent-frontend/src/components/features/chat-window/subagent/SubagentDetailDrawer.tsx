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
  FileText,
  HelpCircle,
  History,
  Layers,
  ListOrdered,
  Play,
  RotateCcw,
  ShieldAlert,
  ShieldCheck,
  Terminal,
  X,
  XCircle,
} from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/primitives/button';
import { ScrollArea } from '@/components/primitives/scroll-area';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/primitives/sheet';
import { Badge } from '@/components/primitives/badge';
import { fmtCost, fmtTokens, extractCostUsd, extractTotalTokens } from '@/lib/utils/subagentTree';
import type { SubagentNode, StreamEntry, TeammateMessageEntry } from '@/store/chat/useSubagentStore';
import { STATUS_ICON_MAP } from './SubagentStream';

interface SubagentDetailDrawerProps {
  node: SubagentNode | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  chatId?: string;
}

type TabType = 'overview' | 'journal' | 'tool_calls' | 'messages' | 'replay';

export const SubagentDetailDrawer: React.FC<SubagentDetailDrawerProps> = ({ node, open, onOpenChange, chatId }) => {
  const t = useTranslations('subagentDashboard');
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

  // Copy helper
  const handleCopy = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    toast.success(`${label} copied to clipboard`);
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
                  <span>{node.agent_type || 'Subagent'}</span>
                  <Badge variant="outline" className="text-[10px] font-mono shrink-0">
                    {node.task_id.slice(0, 8)}
                  </Badge>
                </SheetTitle>
                <SheetDescription className="text-xs text-muted-foreground truncate">
                  {node.description || 'No description provided'}
                </SheetDescription>
              </div>
            </div>

            <div className="flex items-center gap-1.5 shrink-0">
              <div
                className={`flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium border ${statusConfig.className} bg-background/80`}
              >
                <StatusIcon className={`w-3.5 h-3.5 ${statusConfig.spin ? 'animate-spin' : ''}`} />
                <span className="capitalize">{node.status}</span>
              </div>
            </div>
          </div>

          {/* Quick Metrics Strip */}
          <div className="grid grid-cols-4 gap-2 mt-3 pt-3 border-t border-border/50 text-xs text-muted-foreground">
            <div>
              <span className="text-[10px] block opacity-70">Duration</span>
              <span className="font-semibold text-foreground">
                {node.duration_seconds ? `${node.duration_seconds}s` : '—'}
              </span>
            </div>
            <div>
              <span className="text-[10px] block opacity-70">Tokens</span>
              <span className="font-semibold text-foreground">{tokens || '0'}</span>
            </div>
            <div>
              <span className="text-[10px] block opacity-70">Cost</span>
              <span className="font-semibold text-foreground">{cost || '—'}</span>
            </div>
            <div>
              <span className="text-[10px] block opacity-70">Model</span>
              <span className="font-semibold text-foreground truncate block">
                {node.effective_model || 'Inherited'}
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
              Overview
            </button>
            <button
              onClick={() => setActiveTab('journal')}
              className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                activeTab === 'journal' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted'
              }`}
            >
              Run Journal ({stream.length})
            </button>
            <button
              onClick={() => setActiveTab('tool_calls')}
              className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                activeTab === 'tool_calls'
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-muted'
              }`}
            >
              Tools ({toolEntries.length})
            </button>
            <button
              onClick={() => setActiveTab('messages')}
              className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                activeTab === 'messages' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted'
              }`}
            >
              Messages ({teammateMsgs.length})
            </button>
            <button
              onClick={() => setActiveTab('replay')}
              className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                activeTab === 'replay' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted'
              }`}
            >
              Replay
            </button>
          </div>
        </SheetHeader>

        <ScrollArea className="flex-1 p-6">
          {activeTab === 'overview' && (
            <div className="space-y-4">
              {node.error && (
                <div className="p-3 rounded-lg bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900/60 text-red-700 dark:text-red-300 text-xs">
                  <div className="flex items-center gap-1.5 font-bold mb-1">
                    <XCircle className="w-4 h-4" />
                    <span>Error Diagnostic</span>
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
                      <span>Independent Verification: {node.verification.passed ? 'PASSED' : 'FAILED'}</span>
                    </div>
                    <span>
                      Rounds: {node.verification.rounds}/{node.verification.max_rounds}
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
                  Task Specification & Prompt
                </h4>
                <div className="relative p-3 rounded-lg border bg-muted/30 font-mono text-xs leading-relaxed group">
                  <p className="whitespace-pre-wrap break-words">{node.description}</p>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => handleCopy(node.description, 'Task description')}
                    className="absolute top-2 right-2 h-7 px-2 opacity-0 group-hover:opacity-100 transition-opacity"
                  >
                    <Copy className="w-3.5 h-3.5" />
                  </Button>
                </div>
              </div>

              <div>
                <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
                  Metadata & Governance
                </h4>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className="p-2.5 rounded-lg border bg-muted/20">
                    <span className="text-muted-foreground text-[10px] block">Task ID</span>
                    <span className="font-mono text-[11px] truncate block">{node.task_id}</span>
                  </div>
                  <div className="p-2.5 rounded-lg border bg-muted/20">
                    <span className="text-muted-foreground text-[10px] block">Parent Task ID</span>
                    <span className="font-mono text-[11px] truncate block">{node.parent_task_id || 'Root Task'}</span>
                  </div>
                  <div className="p-2.5 rounded-lg border bg-muted/20">
                    <span className="text-muted-foreground text-[10px] block">Role / Scope</span>
                    <span className="font-mono text-[11px] truncate block">
                      {node.role || node.control_scope || 'Standard Leaf'}
                    </span>
                  </div>
                  <div className="p-2.5 rounded-lg border bg-muted/20">
                    <span className="text-muted-foreground text-[10px] block">Progress Status</span>
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
                <div className="py-8 text-center text-xs text-muted-foreground">No run journal entries recorded.</div>
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
                <div className="py-8 text-center text-xs text-muted-foreground">No tool executions recorded.</div>
              ) : (
                toolEntries.map((tool: StreamEntry, idx: number) => (
                  <div key={idx} className="p-3 rounded-lg border bg-muted/20 text-xs">
                    <div className="flex items-center justify-between mb-1.5">
                      <div className="flex items-center gap-1.5 font-bold text-foreground">
                        <Terminal className="w-3.5 h-3.5 text-primary" />
                        <span>Tool Call #{idx + 1}</span>
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
                <div className="py-8 text-center text-xs text-muted-foreground">No teammate messages exchanged.</div>
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
                        <span>{isOutbound ? `Sent to: ${msg.to_task_id}` : `Received from: ${msg.from_task_id}`}</span>
                        <span className="font-mono">{new Date(msg.timestamp).toLocaleTimeString()}</span>
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
                    Step Replay ({stream.length > 0 ? replayStepIndex + 1 : 0}/{stream.length})
                  </span>
                  <div className="flex items-center gap-1">
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 text-xs px-2"
                      disabled={replayStepIndex <= 0}
                      onClick={() => setReplayStepIndex((prev) => Math.max(0, prev - 1))}
                    >
                      Prev
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 text-xs px-2"
                      disabled={replayStepIndex >= stream.length - 1}
                      onClick={() => setReplayStepIndex((prev) => Math.min(stream.length - 1, prev + 1))}
                    >
                      Next
                    </Button>
                  </div>
                </div>

                {stream.length > 0 && stream[replayStepIndex] ? (
                  <div className="p-3 rounded border bg-background text-xs space-y-2">
                    <div className="flex items-center justify-between">
                      <Badge variant="secondary" className="text-[10px]">
                        Kind: {stream[replayStepIndex].kind}
                      </Badge>
                      <span className="font-mono text-[10px] text-muted-foreground">
                        Duration: {stream[replayStepIndex].durationMs || 0}ms
                      </span>
                    </div>
                    <pre className="font-mono text-[11px] whitespace-pre-wrap break-all p-2 bg-muted/40 rounded">
                      {stream[replayStepIndex].text}
                    </pre>
                  </div>
                ) : (
                  <div className="text-center text-xs text-muted-foreground py-4">No steps available to replay.</div>
                )}
              </div>
            </div>
          )}
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
};

export default SubagentDetailDrawer;
