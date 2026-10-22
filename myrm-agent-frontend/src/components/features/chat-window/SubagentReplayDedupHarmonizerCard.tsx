import React, { useState, useMemo } from 'react';
import { Layers, Activity, ShieldCheck, Zap, RotateCcw, X, ChevronRight, Lock, CheckCircle2, AlertTriangle } from 'lucide-react';

export type ToolReplayStatus = 'idle' | 'running' | 'pending_approval' | 'completed' | 'failed' | 'cancelled' | 'timeout_terminated';
export type ToolReplayKind = 'read_only' | 'mutating' | 'system';

export interface MergedBatchItem {
  batch_id: string;
  tool_name: string;
  merged_count: number;
  item_ids: string[];
  aggregated_args_summary: string;
  original_tokens: number;
  compact_tokens: number;
  tokens_saved: number;
  final_status: ToolReplayStatus;
  subagent_id: string;
}

export interface IsolatedToolItem {
  call_id: string;
  tool_name: string;
  kind: ToolReplayKind;
  summary: string;
  tokens: number;
  status: ToolReplayStatus;
}

export interface SubagentStateItem {
  subagent_id: string;
  status: ToolReplayStatus;
  last_heartbeat_ago: string;
  is_deadlock_prevented: boolean;
}

export interface SubagentReplayDedupHarmonizerCardProps {
  chatId?: string;
  onDismiss?: () => void;
  onHarmonizeComplete?: (savedTokens: number) => void;
}

const DEFAULT_BATCHES: MergedBatchItem[] = [
  {
    batch_id: 'batch-read-01',
    tool_name: 'read_file',
    merged_count: 5,
    item_ids: ['call-r1', 'call-r2', 'call-r3', 'call-r4', 'call-r5'],
    aggregated_args_summary: 'read_file x5 across 5 source files',
    original_tokens: 650,
    compact_tokens: 55,
    tokens_saved: 595,
    final_status: 'completed',
    subagent_id: 'agent-scout-01',
  },
  {
    batch_id: 'batch-grep-02',
    tool_name: 'grep',
    merged_count: 3,
    item_ids: ['call-g1', 'call-g2', 'call-g3'],
    aggregated_args_summary: 'grep x3 across repository regex patterns',
    original_tokens: 420,
    compact_tokens: 45,
    tokens_saved: 375,
    final_status: 'completed',
    subagent_id: 'agent-reviewer-01',
  },
];

const DEFAULT_ISOLATED: IsolatedToolItem[] = [
  {
    call_id: 'call-w1',
    tool_name: 'write_to_file',
    kind: 'mutating',
    summary: 'Modified configuration in settings.py',
    tokens: 280,
    status: 'completed',
  },
  {
    call_id: 'call-b1',
    tool_name: 'run_command',
    kind: 'system',
    summary: 'Executed pytest test suite',
    tokens: 340,
    status: 'completed',
  },
];

const DEFAULT_SUBAGENTS: SubagentStateItem[] = [
  {
    subagent_id: 'agent-scout-01',
    status: 'completed',
    last_heartbeat_ago: '2s ago',
    is_deadlock_prevented: false,
  },
  {
    subagent_id: 'agent-worker-02',
    status: 'running',
    last_heartbeat_ago: '5s ago',
    is_deadlock_prevented: false,
  },
  {
    subagent_id: 'agent-hung-reviewer',
    status: 'timeout_terminated',
    last_heartbeat_ago: '35s ago',
    is_deadlock_prevented: true,
  },
];

export function SubagentReplayDedupHarmonizerCard({
  chatId = 'chat-replay-01',
  onDismiss,
  onHarmonizeComplete,
}: SubagentReplayDedupHarmonizerCardProps): React.ReactElement {
  const [batches, setBatches] = useState<MergedBatchItem[]>(DEFAULT_BATCHES);
  const [isolatedItems] = useState<IsolatedToolItem[]>(DEFAULT_ISOLATED);
  const [subagents, setSubagents] = useState<SubagentStateItem[]>(DEFAULT_SUBAGENTS);
  const [activeTab, setActiveTab] = useState<'batches' | 'harmonizer' | 'isolated'>('batches');
  const [expandedBatchId, setExpandedBatchId] = useState<string | null>(null);
  const [isWatchdogScanned, setIsWatchdogScanned] = useState(false);

  const totalOriginalTokens = useMemo(() => {
    const batchOrig = batches.reduce((acc, b) => acc + b.original_tokens, 0);
    const isoOrig = isolatedItems.reduce((acc, i) => acc + i.tokens, 0);
    return batchOrig + isoOrig;
  }, [batches, isolatedItems]);

  const totalSavedTokens = useMemo(
    () => batches.reduce((acc, b) => acc + b.tokens_saved, 0),
    [batches],
  );

  const reductionRatio = useMemo(() => {
    if (totalOriginalTokens <= 0) {
      return 0;
    }
    return Math.round((totalSavedTokens / totalOriginalTokens) * 100);
  }, [totalOriginalTokens, totalSavedTokens]);

  const handleTriggerMerge = () => {
    setBatches(DEFAULT_BATCHES);
    onHarmonizeComplete?.(totalSavedTokens);
  };

  const handleWatchdogCheck = () => {
    setSubagents((prev) =>
      prev.map((sub) => {
        if (sub.status === 'running' && sub.subagent_id.includes('worker-02')) {
          return {
            ...sub,
            status: 'completed',
            last_heartbeat_ago: 'just now',
          };
        }
        return sub;
      }),
    );
    setIsWatchdogScanned(true);
  };

  return (
    <div
      data-testid="replay-dedup-card"
      className="fixed bottom-4 right-4 z-50 w-[520px] max-w-[94vw] rounded-xl border border-sky-500/30 bg-slate-900/95 p-4 text-slate-100 shadow-2xl backdrop-blur-md transition-all"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-700/60 pb-3">
        <div className="flex items-center space-x-2">
          <Layers className="h-5 w-5 text-sky-400" />
          <h3 className="font-semibold text-slate-100 text-sm">
            Tool Replay Deduplication & Status Harmonizer
          </h3>
        </div>
        <div className="flex items-center space-x-1">
          <button
            type="button"
            data-testid="btn-merge-history"
            onClick={handleTriggerMerge}
            className="flex items-center space-x-1 rounded px-2 py-1 text-xs text-slate-400 hover:bg-slate-800 hover:text-slate-200"
            title="Re-merge history"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            <span>Replay</span>
          </button>
          {onDismiss && (
            <button
              type="button"
              data-testid="btn-close"
              onClick={onDismiss}
              className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      {/* Metrics Banner */}
      <div data-testid="metrics-banner" className="mt-2.5 grid grid-cols-4 gap-2 rounded-lg border border-slate-800 bg-slate-950/60 p-2 text-center text-xs">
        <div>
          <div className="text-[10px] text-slate-500">Original</div>
          <div className="font-mono font-medium text-slate-300">{totalOriginalTokens} t</div>
        </div>
        <div>
          <div className="text-[10px] text-slate-500">Saved</div>
          <div className="font-mono font-semibold text-emerald-400">-{totalSavedTokens} t</div>
        </div>
        <div>
          <div className="text-[10px] text-slate-500">Ratio</div>
          <div className="font-mono font-semibold text-sky-400">~{reductionRatio}%</div>
        </div>
        <div>
          <div className="text-[10px] text-slate-500">Batches</div>
          <div className="font-mono font-medium text-indigo-300">{batches.length}</div>
        </div>
      </div>

      {/* Tab Nav */}
      <div className="mt-3 flex space-x-1 border-b border-slate-800 pb-1 text-xs">
        <button
          type="button"
          data-testid="tab-batches"
          onClick={() => setActiveTab('batches')}
          className={`flex items-center space-x-1 rounded px-2.5 py-1 transition ${
            activeTab === 'batches'
              ? 'bg-sky-600/30 text-sky-300 font-medium'
              : 'text-slate-400 hover:bg-slate-800'
          }`}
        >
          <Zap className="h-3.5 w-3.5" />
          <span>Merged Batches ({batches.length})</span>
        </button>
        <button
          type="button"
          data-testid="tab-harmonizer"
          onClick={() => setActiveTab('harmonizer')}
          className={`flex items-center space-x-1 rounded px-2.5 py-1 transition ${
            activeTab === 'harmonizer'
              ? 'bg-sky-600/30 text-sky-300 font-medium'
              : 'text-slate-400 hover:bg-slate-800'
          }`}
        >
          <Activity className="h-3.5 w-3.5" />
          <span>Status Machine ({subagents.length})</span>
        </button>
        <button
          type="button"
          data-testid="tab-isolated"
          onClick={() => setActiveTab('isolated')}
          className={`flex items-center space-x-1 rounded px-2.5 py-1 transition ${
            activeTab === 'isolated'
              ? 'bg-sky-600/30 text-sky-300 font-medium'
              : 'text-slate-400 hover:bg-slate-800'
          }`}
        >
          <Lock className="h-3.5 w-3.5" />
          <span>Mutating Ops ({isolatedItems.length})</span>
        </button>
      </div>

      {/* Tab 1: Batches List */}
      {activeTab === 'batches' && (
        <div data-testid="batches-list" className="mt-2.5 max-h-[190px] space-y-2 overflow-y-auto pr-1">
          {batches.map((batch) => (
            <div
              key={batch.batch_id}
              className="rounded-lg border border-slate-800 bg-slate-950/40 p-2 text-xs"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-1.5 font-medium text-slate-200">
                  <span className="rounded bg-sky-500/20 px-1.5 py-0.5 text-[10px] font-semibold text-sky-300 border border-sky-500/40">
                    {batch.tool_name} x{batch.merged_count}
                  </span>
                  <span className="text-[11px] text-slate-400">{batch.subagent_id}</span>
                </div>
                <span className="font-mono text-[10px] text-emerald-400">-{batch.tokens_saved} t</span>
              </div>
              <p className="mt-1 text-[11px] text-slate-400">{batch.aggregated_args_summary}</p>
              <div className="mt-1.5 flex items-center justify-between text-[10px] text-slate-500">
                <button
                  type="button"
                  onClick={() =>
                    setExpandedBatchId(expandedBatchId === batch.batch_id ? null : batch.batch_id)
                  }
                  className="flex items-center space-x-0.5 text-sky-400 hover:underline"
                >
                  <ChevronRight
                    className={`h-3 w-3 transform transition-transform ${
                      expandedBatchId === batch.batch_id ? 'rotate-90' : ''
                    }`}
                  />
                  <span>{expandedBatchId === batch.batch_id ? 'Hide Calls' : `View ${batch.item_ids.length} Calls`}</span>
                </button>
                <span className="font-mono">{batch.compact_tokens} / {batch.original_tokens} t</span>
              </div>
              {expandedBatchId === batch.batch_id && (
                <div className="mt-1.5 rounded bg-slate-900 p-1.5 font-mono text-[10px] text-slate-400">
                  {batch.item_ids.map((id) => (
                    <div key={id} className="py-0.5">• {id}</div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Tab 2: Status Harmonizer Machine */}
      {activeTab === 'harmonizer' && (
        <div data-testid="subagents-list" className="mt-2.5 max-h-[190px] space-y-1.5 overflow-y-auto pr-1">
          {subagents.map((sub) => (
            <div
              key={sub.subagent_id}
              className="flex items-center justify-between rounded border border-slate-800 bg-slate-950/40 p-2 text-xs"
            >
              <div className="flex items-center space-x-2">
                {sub.status === 'completed' && <CheckCircle2 className="h-4 w-4 text-emerald-400" />}
                {sub.status === 'running' && <Activity className="h-4 w-4 text-sky-400 animate-pulse" />}
                {sub.status === 'timeout_terminated' && <AlertTriangle className="h-4 w-4 text-rose-400" />}
                <div>
                  <div className="font-medium text-slate-200 text-[11px]">{sub.subagent_id}</div>
                  <div className="text-[10px] text-slate-500">{sub.last_heartbeat_ago}</div>
                </div>
              </div>
              <div className="flex items-center space-x-1.5">
                <span
                  className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
                    sub.status === 'completed'
                      ? 'bg-emerald-500/20 text-emerald-300'
                      : sub.status === 'running'
                      ? 'bg-sky-500/20 text-sky-300'
                      : 'bg-rose-500/20 text-rose-300'
                  }`}
                >
                  {sub.status.toUpperCase()}
                </span>
                {sub.is_deadlock_prevented && (
                  <span className="rounded bg-rose-500/30 px-1 py-0.5 text-[9px] text-rose-200">
                    Defused
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Tab 3: Isolated Mutating Operations */}
      {activeTab === 'isolated' && (
        <div data-testid="isolated-list" className="mt-2.5 max-h-[190px] space-y-2 overflow-y-auto pr-1">
          <div className="rounded border border-amber-500/30 bg-amber-500/10 p-2 text-[11px] text-amber-200">
            <div className="flex items-center space-x-1 font-semibold">
              <ShieldCheck className="h-3.5 w-3.5" />
              <span>Immutable Audit Isolation</span>
            </div>
            <p className="mt-0.5 text-[10px] text-amber-300/80">
              Mutating and system operations are strictly preserved unmerged to guarantee tamper-proof audit trails.
            </p>
          </div>
          {isolatedItems.map((item) => (
            <div
              key={item.call_id}
              className="flex items-center justify-between rounded border border-slate-800 bg-slate-950/40 p-2 text-xs"
            >
              <div>
                <div className="flex items-center space-x-1 font-medium text-slate-200">
                  <Lock className="h-3 w-3 text-amber-400" />
                  <span>{item.tool_name}</span>
                  <span className="text-[10px] text-slate-500 font-mono">({item.call_id})</span>
                </div>
                <p className="mt-0.5 text-[10px] text-slate-400">{item.summary}</p>
              </div>
              <span className="font-mono text-[10px] text-slate-400">{item.tokens} t</span>
            </div>
          ))}
        </div>
      )}

      {/* Footer Controls */}
      <div className="mt-3 flex items-center justify-between border-t border-slate-800 pt-2.5 text-xs text-slate-400">
        <span className="font-mono text-[11px] text-slate-500">Chat: {chatId}</span>
        <button
          type="button"
          data-testid="btn-watchdog-check"
          onClick={handleWatchdogCheck}
          className="flex items-center space-x-1 rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white shadow-md hover:bg-sky-500 transition"
        >
          <Activity className="h-3.5 w-3.5" />
          <span>{isWatchdogScanned ? 'Lease Green' : 'Watchdog Scan'}</span>
        </button>
      </div>
    </div>
  );
}

export default SubagentReplayDedupHarmonizerCard;
