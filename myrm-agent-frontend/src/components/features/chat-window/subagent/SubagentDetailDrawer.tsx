'use client';

/**
 * [INPUT]
 * @/store/chat/useSubagentStore::SubagentNode (POS: Multi-agent execution tree and stream state store)
 * ./SubagentStream::STATUS_ICON_MAP (POS: Status icons for all subagent states and live stream entries)
 * ./SubagentOverviewTab::SubagentOverviewTab (POS: Overview tab of the subagent detail drawer)
 * ./SubagentViewportTab::SubagentViewportTab (POS: Sandboxed browser live peek panel and terminal snapshot view for subagents)
 *
 * [OUTPUT]
 * SubagentDetailDrawer: Detail drawer shell for one subagent node: header, metrics strip, horizontally scrollable keyboard-navigable tablist (Radix Tabs: roving focus, arrow/Home/End keys, tab-to-panel ARIA wiring), and the journal, tools, messages, and replay tabs.
 *
 * [POS]
 * Subagent inspection surface. Owns the active-tab and replay-step state and delegates the overview and viewport tabs to their own components.
 */

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import { Bot, Terminal } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { ScrollArea } from '@/components/primitives/scroll-area';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/primitives/tabs';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/primitives/sheet';
import { Badge } from '@/components/primitives/badge';
import { fmtCost, fmtTokens, extractCostUsd, extractTotalTokens } from '@/lib/utils/subagent/subagentTree';
import type { SubagentNode, StreamEntry, TeammateMessageEntry } from '@/store/chat/useSubagentStore';
import { STATUS_ICON_MAP } from './SubagentStream';
import { SubagentOverviewTab } from './SubagentOverviewTab';
import { SubagentViewportTab } from './SubagentViewportTab';

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

  const tabs: { id: TabType; label: string; testId?: string }[] = [
    { id: 'overview', label: t('detailTabOverview') },
    { id: 'journal', label: t('detailTabJournal', { count: stream.length }) },
    { id: 'tool_calls', label: t('detailTabTools', { count: toolEntries.length }) },
    { id: 'messages', label: t('detailTabMessages', { count: teammateMsgs.length }) },
    { id: 'replay', label: t('detailTabReplay') },
    { id: 'viewport', label: t('detailTabViewport'), testId: 'subagent-drawer-tab-viewport' },
  ];

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="w-full sm:max-w-xl md:max-w-2xl p-0 flex flex-col h-full bg-background border-l border-border"
        data-testid="subagent-detail-drawer"
      >
        {/* `contents` keeps the tabs context out of the flex layout between the header and the scroll area. */}
        <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as TabType)} className="contents">
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

            {/* Navigation Tabs: the focus ring is inset because this scrolling list would clip an outer one */}
            <TabsList className="mt-3 min-h-0 w-full justify-start gap-1 overflow-x-auto rounded-none border-b border-border/40 bg-transparent p-0 pb-1 scrollbar-hide">
              {tabs.map((tab) => (
                <TabsTrigger
                  key={tab.id}
                  value={tab.id}
                  data-testid={tab.testId}
                  className="shrink-0 py-1 text-xs focus-visible:ring-inset focus-visible:ring-offset-0 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground data-[state=active]:shadow-none data-[state=inactive]:hover:bg-muted"
                >
                  {tab.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </SheetHeader>

          <ScrollArea className="flex-1 p-6">
            <TabsContent value="overview" className="mt-0">
              <SubagentOverviewTab node={node} />
            </TabsContent>

            <TabsContent value="journal" className="mt-0">
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
            </TabsContent>

            <TabsContent value="tool_calls" className="mt-0">
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
                            {tool.durationMs < 1000
                              ? `${tool.durationMs}ms`
                              : `${(tool.durationMs / 1000).toFixed(1)}s`}
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
            </TabsContent>

            <TabsContent value="messages" className="mt-0">
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
            </TabsContent>

            <TabsContent value="replay" className="mt-0">
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
            </TabsContent>

            <TabsContent value="viewport" className="mt-0">
              <SubagentViewportTab node={node} chatId={chatId} />
            </TabsContent>
          </ScrollArea>
        </Tabs>
      </SheetContent>
    </Sheet>
  );
};

export default SubagentDetailDrawer;
