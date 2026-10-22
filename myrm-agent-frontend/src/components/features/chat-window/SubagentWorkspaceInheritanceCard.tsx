import React, { useState, useMemo } from 'react';
import { Layers, ShieldAlert, Cpu, Sparkles, Copy, Check, RotateCcw, X, FileText, ChevronRight } from 'lucide-react';

export type ContextSourceType = '.rules' | 'AGENTS.md' | 'README.md' | 'custom';
export type RulePriority = 'critical' | 'high' | 'normal' | 'low';
export type SubagentRole = 'worker' | 'reviewer' | 'specialist' | 'coordinator';

export interface ContextRuleSnippetItem {
  source_type: ContextSourceType;
  file_path: string;
  priority: RulePriority;
  title: string;
  content: string;
  token_count: number;
}

export interface InheritanceAuditRecordItem {
  record_id: string;
  timestamp: number;
  role: SubagentRole;
  injected_token_count: number;
  is_compacted: boolean;
  snippet_count: number;
}

export interface SubagentWorkspaceInheritanceCardProps {
  chatId?: string;
  workspaceRoot?: string;
  onDismiss?: () => void;
  onEnrichSuccess?: (enrichedPrompt: string) => void;
}

const DEFAULT_SNIPPETS: ContextRuleSnippetItem[] = [
  {
    source_type: '.rules',
    file_path: '/workspace/.rules',
    priority: 'critical',
    title: 'Code Quality & Lint Guardrails',
    content: 'All code changes must have 0 lint errors, no any types, and file length <= 400 lines.',
    token_count: 65,
  },
  {
    source_type: 'AGENTS.md',
    file_path: '/workspace/AGENTS.md',
    priority: 'high',
    title: 'Subagent Collaboration & Memory Protocol',
    content: 'Worker subagents must yield back to parent orchestrator via structured report FIFO upon completion.',
    token_count: 90,
  },
  {
    source_type: 'README.md',
    file_path: '/workspace/README.md',
    priority: 'normal',
    title: 'Project Architecture Conventions',
    content: 'Fullstack Next.js + FastAPI topology with strict dual-track tool execution and state preservation.',
    token_count: 120,
  },
];

export function SubagentWorkspaceInheritanceCard({
  chatId = 'chat-workspace-01',
  workspaceRoot = '/workspace/project-root',
  onDismiss,
  onEnrichSuccess,
}: SubagentWorkspaceInheritanceCardProps): React.ReactElement {
  const [snippets, setSnippets] = useState<ContextRuleSnippetItem[]>(DEFAULT_SNIPPETS);
  const [selectedRole, setSelectedRole] = useState<SubagentRole>('worker');
  const [tokenBudget, setTokenBudget] = useState<number>(2000);
  const [basePrompt, setBasePrompt] = useState<string>('You are an expert AI subagent responsible for executing tasks.');
  const [enrichedPrompt, setEnrichedPrompt] = useState<string>('');
  const [isCompacted, setIsCompacted] = useState<boolean>(false);
  const [injectedTokens, setInjectedTokens] = useState<number>(0);
  const [isCopied, setIsCopied] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<'rules' | 'preview' | 'audit'>('rules');
  const [auditHistory, setAuditHistory] = useState<InheritanceAuditRecordItem[]>([
    {
      record_id: 'audit-001',
      timestamp: Date.now() - 360000,
      role: 'worker',
      injected_token_count: 275,
      is_compacted: false,
      snippet_count: 3,
    },
  ]);

  const totalRuleTokens = useMemo(
    () => snippets.reduce((acc, s) => acc + s.token_count, 0),
    [snippets],
  );

  const budgetUsagePercent = useMemo(
    () => Math.min(100, Math.round((totalRuleTokens / Math.max(tokenBudget, 10)) * 100)),
    [totalRuleTokens, tokenBudget],
  );

  const handleRescan = () => {
    // Reset to refreshed default snippets and update audit count
    setSnippets(DEFAULT_SNIPPETS);
  };

  const handleEnrichPrompt = () => {
    const compactNeeded = totalRuleTokens > tokenBudget;
    setIsCompacted(compactNeeded);

    const contextHeader = `=== WORKSPACE INHERITED CONTEXT [ROLE: ${selectedRole.toUpperCase()}] ===\n`;
    const rulesBody = snippets
      .map((s) => {
        if (compactNeeded && s.priority === 'normal') {
          return `[${s.source_type} | ${s.priority.toUpperCase()}] ${s.title}: ${s.content.slice(0, 40)}... (compacted)`;
        }
        return `[${s.source_type} | ${s.priority.toUpperCase()}] ${s.title}\n${s.content}`;
      })
      .join('\n\n');
    const synthesized = `${basePrompt}\n\n${contextHeader}${rulesBody}\n=== END WORKSPACE CONTEXT ===`;

    const estimatedTokens = Math.min(totalRuleTokens, tokenBudget);
    setInjectedTokens(estimatedTokens);
    setEnrichedPrompt(synthesized);
    setActiveTab('preview');

    const newRecord: InheritanceAuditRecordItem = {
      record_id: `audit-${Date.now().toString(36)}`,
      timestamp: Date.now(),
      role: selectedRole,
      injected_token_count: estimatedTokens,
      is_compacted: compactNeeded,
      snippet_count: snippets.length,
    };
    setAuditHistory((prev) => [newRecord, ...prev.slice(0, 9)]);
    onEnrichSuccess?.(synthesized);
  };

  const handleCopyPrompt = () => {
    if (!enrichedPrompt) {
      return;
    }
    navigator.clipboard?.writeText(enrichedPrompt);
    setIsCopied(true);
    setTimeout(() => setIsCopied(false), 2000);
  };

  return (
    <div
      data-testid="workspace-inheritance-card"
      className="fixed bottom-4 right-4 z-50 w-[520px] max-w-[94vw] rounded-xl border border-indigo-500/30 bg-slate-900/95 p-4 text-slate-100 shadow-2xl backdrop-blur-md transition-all"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-700/60 pb-3">
        <div className="flex items-center space-x-2">
          <Layers className="h-5 w-5 text-indigo-400" />
          <h3 className="font-semibold text-slate-100 text-sm">
            Workspace Context Inheritance & Prompt Enrichment
          </h3>
        </div>
        <div className="flex items-center space-x-1">
          <button
            type="button"
            data-testid="rescan-btn"
            onClick={handleRescan}
            className="flex items-center space-x-1 rounded px-2 py-1 text-xs text-slate-400 hover:bg-slate-800 hover:text-slate-200"
            title="Rescan rules"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            <span>Scan</span>
          </button>
          {onDismiss && (
            <button
              type="button"
              data-testid="close-btn"
              onClick={onDismiss}
              className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      {/* Path & Meta bar */}
      <div className="mt-2.5 flex items-center justify-between text-[11px] text-slate-400">
        <div className="truncate font-mono" title={workspaceRoot}>
          Root: <span className="text-slate-300">{workspaceRoot}</span>
        </div>
        <span className="shrink-0 text-slate-500">Chat: {chatId}</span>
      </div>

      {/* Budget Meter */}
      <div data-testid="budget-bar" className="mt-2.5 rounded-lg border border-slate-800 bg-slate-950/60 p-2.5">
        <div className="flex items-center justify-between text-xs">
          <span className="flex items-center space-x-1 text-slate-300">
            <Cpu className="h-3.5 w-3.5 text-indigo-400" />
            <span>Token Budget Allocation</span>
          </span>
          <span className="font-mono text-indigo-300">
            {totalRuleTokens} / {tokenBudget} tokens ({budgetUsagePercent}%)
          </span>
        </div>
        <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
          <div
            className={`h-full transition-all duration-300 ${
              budgetUsagePercent > 90 ? 'bg-amber-400' : 'bg-indigo-500'
            }`}
            style={{ width: `${budgetUsagePercent}%` }}
          />
        </div>
        <div className="mt-2 flex items-center justify-between text-[11px] text-slate-400">
          <label htmlFor="budget-slider" className="text-slate-400">Max Budget:</label>
          <input
            id="budget-slider"
            type="range"
            min={100}
            max={4000}
            step={100}
            value={tokenBudget}
            onChange={(e) => setTokenBudget(Number(e.target.value))}
            className="mx-2 h-1 flex-1 accent-indigo-500 cursor-pointer"
          />
          <span className="font-mono text-slate-300">{tokenBudget} t</span>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="mt-3 flex space-x-1 border-b border-slate-800 pb-1 text-xs">
        <button
          type="button"
          onClick={() => setActiveTab('rules')}
          className={`flex items-center space-x-1 rounded px-2.5 py-1 transition ${
            activeTab === 'rules'
              ? 'bg-indigo-600/30 text-indigo-300 font-medium'
              : 'text-slate-400 hover:bg-slate-800'
          }`}
        >
          <FileText className="h-3.5 w-3.5" />
          <span>Inherited Rules ({snippets.length})</span>
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('preview')}
          className={`flex items-center space-x-1 rounded px-2.5 py-1 transition ${
            activeTab === 'preview'
              ? 'bg-indigo-600/30 text-indigo-300 font-medium'
              : 'text-slate-400 hover:bg-slate-800'
          }`}
        >
          <Sparkles className="h-3.5 w-3.5" />
          <span>Enriched Prompt</span>
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('audit')}
          className={`flex items-center space-x-1 rounded px-2.5 py-1 transition ${
            activeTab === 'audit'
              ? 'bg-indigo-600/30 text-indigo-300 font-medium'
              : 'text-slate-400 hover:bg-slate-800'
          }`}
        >
          <ShieldAlert className="h-3.5 w-3.5" />
          <span>Audit Trail ({auditHistory.length})</span>
        </button>
      </div>

      {/* Tab 1: Rules List */}
      {activeTab === 'rules' && (
        <div data-testid="rules-list" className="mt-2.5 max-h-[190px] space-y-2 overflow-y-auto pr-1">
          {snippets.map((snip) => (
            <div
              key={`${snip.source_type}-${snip.title}`}
              className="rounded-lg border border-slate-800 bg-slate-950/40 p-2 text-xs"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-1.5 font-medium text-slate-200">
                  <span
                    className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                      snip.priority === 'critical'
                        ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                        : snip.priority === 'high'
                        ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                        : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                    }`}
                  >
                    {snip.priority.toUpperCase()}
                  </span>
                  <span>{snip.title}</span>
                </div>
                <span className="font-mono text-[10px] text-slate-400">{snip.token_count} tokens</span>
              </div>
              <p className="mt-1 line-clamp-2 text-[11px] text-slate-400">{snip.content}</p>
              <div className="mt-1 text-[10px] text-slate-500 font-mono">{snip.file_path}</div>
            </div>
          ))}
        </div>
      )}

      {/* Tab 2: Enriched Prompt Preview */}
      {activeTab === 'preview' && (
        <div data-testid="prompt-preview" className="mt-2.5">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>
              Injected: <span className="font-mono text-indigo-300">{injectedTokens} t</span>
              {isCompacted && (
                <span className="ml-2 rounded bg-amber-500/20 px-1 py-0.5 text-[10px] text-amber-300">
                  Compacted
                </span>
              )}
            </span>
            {enrichedPrompt && (
              <button
                type="button"
                onClick={handleCopyPrompt}
                className="flex items-center space-x-1 text-slate-400 hover:text-indigo-300"
              >
                {isCopied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                <span className="text-[11px]">{isCopied ? 'Copied' : 'Copy'}</span>
              </button>
            )}
          </div>
          <textarea
            readOnly
            value={enrichedPrompt || 'Click "Enrich Prompt" below to synthesize the enriched system prompt.'}
            className="mt-1.5 h-[160px] w-full resize-none rounded-lg border border-slate-800 bg-slate-950 p-2 font-mono text-[11px] text-slate-300 focus:outline-none"
          />
        </div>
      )}

      {/* Tab 3: Audit Trail */}
      {activeTab === 'audit' && (
        <div data-testid="audit-history" className="mt-2.5 max-h-[190px] space-y-1.5 overflow-y-auto pr-1">
          {auditHistory.map((item) => (
            <div
              key={item.record_id}
              className="flex items-center justify-between rounded border border-slate-800/80 bg-slate-950/30 p-1.5 text-[11px]"
            >
              <div className="flex items-center space-x-1.5">
                <ChevronRight className="h-3 w-3 text-slate-500" />
                <span className="font-mono text-slate-300">[{item.role.toUpperCase()}]</span>
                <span className="text-slate-400">{item.snippet_count} rules</span>
              </div>
              <div className="flex items-center space-x-2">
                <span className="font-mono text-indigo-300">{item.injected_token_count} t</span>
                {item.is_compacted && (
                  <span className="text-[10px] text-amber-400">compacted</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Control Footer */}
      <div className="mt-3 flex items-center justify-between border-t border-slate-800 pt-2.5">
        <div className="flex items-center space-x-2">
          <label htmlFor="role-select" className="text-xs text-slate-400">Role:</label>
          <select
            id="role-select"
            data-testid="role-select"
            value={selectedRole}
            onChange={(e) => setSelectedRole(e.target.value as SubagentRole)}
            className="rounded border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:outline-none"
          >
            <option value="worker">Worker</option>
            <option value="reviewer">Reviewer</option>
            <option value="specialist">Specialist</option>
            <option value="coordinator">Coordinator</option>
          </select>
        </div>
        <button
          type="button"
          data-testid="enrich-btn"
          onClick={handleEnrichPrompt}
          className="flex items-center space-x-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white shadow-md hover:bg-indigo-500 transition"
        >
          <Sparkles className="h-3.5 w-3.5" />
          <span>Enrich Prompt</span>
        </button>
      </div>
    </div>
  );
}

export default SubagentWorkspaceInheritanceCard;
