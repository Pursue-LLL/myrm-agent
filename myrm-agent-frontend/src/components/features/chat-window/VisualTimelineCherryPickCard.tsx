import React, { useState, useMemo } from 'react';
import {
  History,
  RotateCcw,
  AlertTriangle,
  CheckCircle2,
  Filter,
  Search,
  Code2,
  User,
  Bot,
  Cloud,
  Cpu,
  X,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import type {
  ActorType,
  OperationType,
  RollbackResultItem,
  TimelineNodeItem,
  VisualTimelineCherryPickCardProps,
} from './visual-timeline/types';
import { INITIAL_TIMELINE_NODES } from './visual-timeline/types';

export const VisualTimelineCherryPickCard: React.FC<VisualTimelineCherryPickCardProps> = ({
  sessionId = 'sess-default',
  onDismiss,
  onRollbackComplete,
}) => {
  const [nodes, setNodes] = useState<TimelineNodeItem[]>(INITIAL_TIMELINE_NODES);
  const [selectedActorFilter, setSelectedActorFilter] = useState<string>('all');
  const [selectedOpFilter, setSelectedOpFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [expandedNodeId, setExpandedNodeId] = useState<string | null>(null);
  const [confirmRollbackNodeId, setConfirmRollbackNodeId] = useState<string | null>(null);
  const [isRollingBack, setIsRollingBack] = useState<boolean>(false);
  const [lastResult, setLastResult] = useState<RollbackResultItem | null>(null);

  const filteredNodes = useMemo(() => {
    return nodes.filter((node) => {
      if (selectedActorFilter !== 'all' && node.actorType !== selectedActorFilter) {
        return false;
      }
      if (selectedOpFilter !== 'all' && node.operationType !== selectedOpFilter) {
        return false;
      }
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase();
        const matchesFile = node.filePath.toLowerCase().includes(query);
        const matchesDesc = (node.diffSummary || '').toLowerCase().includes(query);
        const matchesActor = node.actorName.toLowerCase().includes(query);
        if (!matchesFile && !matchesDesc && !matchesActor) {
          return false;
        }
      }
      return true;
    });
  }, [nodes, selectedActorFilter, selectedOpFilter, searchQuery]);

  const handleExecuteRollback = async (targetNode: TimelineNodeItem) => {
    if (targetNode.isRolledBack) {
      return;
    }
    setIsRollingBack(true);
    setLastResult(null);

    try {
      // 检查是否有后续对同一文件的重叠行修改以检测冲突
      const hasConflict = nodes.some(
        (n) =>
          n.filePath === targetNode.filePath &&
          n.timestamp > targetNode.timestamp &&
          !n.isRolledBack &&
          n.lineStart !== undefined &&
          targetNode.lineStart !== undefined &&
          Math.max(n.lineStart, targetNode.lineStart) <=
            Math.min(n.lineEnd || n.lineStart, targetNode.lineEnd || targetNode.lineStart)
      );

      if (hasConflict) {
        const conflictRes: RollbackResultItem = {
          nodeId: targetNode.nodeId,
          status: 'conflict_detected',
          filePath: targetNode.filePath,
          conflictReason: `Subsequent modification overlapped with lines ${targetNode.lineStart}-${targetNode.lineEnd}. Cherry-pick stopped to prevent data corruption.`,
          rollbackTimestamp: Date.now(),
        };
        setLastResult(conflictRes);
        if (onRollbackComplete) {
          onRollbackComplete(conflictRes);
        }
      } else {
        const successRes: RollbackResultItem = {
          nodeId: targetNode.nodeId,
          status: 'success',
          filePath: targetNode.filePath,
          restoredContent: targetNode.beforeContent || '',
          rollbackTimestamp: Date.now(),
        };
        setNodes((prev) =>
          prev.map((n) =>
            n.nodeId === targetNode.nodeId ? { ...n, isRolledBack: true } : n
          )
        );
        setLastResult(successRes);
        if (onRollbackComplete) {
          onRollbackComplete(successRes);
        }
      }
    } finally {
      setIsRollingBack(false);
      setConfirmRollbackNodeId(null);
    }
  };

  const ACTOR_ICONS: Record<ActorType, React.ReactNode> = {
    human_user: <User className="w-3.5 h-3.5 text-blue-400" />,
    local_agent: <Bot className="w-3.5 h-3.5 text-emerald-400" />,
    cloud_agent: <Cloud className="w-3.5 h-3.5 text-cyan-400" />,
    system_orchestrator: <Cpu className="w-3.5 h-3.5 text-purple-400" />,
  };

  const OP_BADGES: Record<OperationType, string> = {
    file_create: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    file_modify: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    file_delete: 'bg-red-500/10 text-red-400 border-red-500/20',
    tool_execution: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    git_commit: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
  };

  return (
    <section
      data-testid="visual-timeline-cherry-pick-card"
      aria-label="Multi-Agent Visual Timeline & Cherry-Pick Rollback"
      className="flex flex-col bg-slate-900 border border-slate-700/80 rounded-xl shadow-2xl overflow-hidden max-w-4xl w-full text-slate-200"
    >
      {/* Header */}
      <header className="flex items-center justify-between px-5 py-3.5 bg-slate-800/80 border-b border-slate-700/80">
        <div className="flex items-center gap-2.5">
          <History className="w-5 h-5 text-indigo-400" />
          <h2 className="text-base font-semibold text-slate-100">
            Multi-Agent Visual Timeline & Cherry-Pick
          </h2>
          <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 font-mono">
            {sessionId}
          </span>
        </div>
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            aria-label="Close"
            className="p-1 rounded-md text-slate-400 hover:text-slate-100 hover:bg-slate-700/60 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </header>

      {/* Filter and Search Bar */}
      <div className="flex flex-wrap items-center gap-3 px-5 py-3 bg-slate-850 border-b border-slate-700/60 text-xs">
        <div className="flex items-center gap-1.5 text-slate-400">
          <Filter className="w-3.5 h-3.5" />
          <span>Filters:</span>
        </div>
        <select
          aria-label="Filter by Actor"
          value={selectedActorFilter}
          onChange={(e) => setSelectedActorFilter(e.target.value)}
          className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-slate-200 focus:outline-none focus:border-indigo-500"
        >
          <option value="all">All Actors</option>
          <option value="human_user">Human Lead</option>
          <option value="local_agent">Local Bot</option>
          <option value="cloud_agent">Cloud Worker</option>
          <option value="system_orchestrator">System</option>
        </select>
        <select
          aria-label="Filter by Operation"
          value={selectedOpFilter}
          onChange={(e) => setSelectedOpFilter(e.target.value)}
          className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-slate-200 focus:outline-none focus:border-indigo-500"
        >
          <option value="all">All Operations</option>
          <option value="file_modify">File Modify</option>
          <option value="file_create">File Create</option>
          <option value="file_delete">File Delete</option>
          <option value="tool_execution">Tool Execution</option>
        </select>
        <div className="flex-1 flex items-center bg-slate-800 border border-slate-700 rounded px-2.5 py-1 min-w-[180px]">
          <Search className="w-3.5 h-3.5 text-slate-400 mr-1.5" />
          <input
            type="text"
            placeholder="Search by file, actor, or diff..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-transparent text-slate-200 placeholder-slate-500 focus:outline-none"
          />
        </div>
      </div>

      {/* Rollback Result Banner */}
      {lastResult && (
        <output
          aria-live="polite"
          className={`flex items-start gap-2.5 px-5 py-2.5 border-b text-xs ${
            lastResult.status === 'success'
              ? 'bg-emerald-950/40 border-emerald-500/30 text-emerald-300'
              : 'bg-amber-950/40 border-amber-500/30 text-amber-300'
          }`}
        >
          {lastResult.status === 'success' ? (
            <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-400 mt-0.5" />
          ) : (
            <AlertTriangle className="w-4 h-4 shrink-0 text-amber-400 mt-0.5" />
          )}
          <div className="flex-1">
            <p className="font-semibold">
              {lastResult.status === 'success'
                ? `Node ${lastResult.nodeId} reverted safely!`
                : `Cherry-pick Conflict Detected on ${lastResult.nodeId}`}
            </p>
            <p className="opacity-90">
              {lastResult.status === 'success'
                ? `Reverted changes in ${lastResult.filePath} while preserving all other collaborators' modifications.`
                : lastResult.conflictReason}
            </p>
          </div>
          <button
            type="button"
            onClick={() => setLastResult(null)}
            className="text-slate-400 hover:text-slate-200"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </output>
      )}

      {/* Timeline Stream */}
      <div className="p-5 overflow-y-auto max-h-[480px] space-y-3.5">
        {filteredNodes.length === 0 ? (
          <div className="text-center py-10 text-slate-500 text-xs">
            No timeline nodes match the selected filters.
          </div>
        ) : (
          filteredNodes.map((node) => {
            const isExpanded = expandedNodeId === node.nodeId;
            const isConfirming = confirmRollbackNodeId === node.nodeId;

            return (
              <article
                key={node.nodeId}
                className={`relative flex flex-col rounded-lg border p-3.5 transition-all ${
                  node.isRolledBack
                    ? 'bg-slate-900/60 border-slate-800 opacity-60'
                    : 'bg-slate-800/60 border-slate-700 hover:border-slate-600'
                }`}
              >
                {/* Node Summary Row */}
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <span className="p-1 rounded bg-slate-700/80">
                      {ACTOR_ICONS[node.actorType]}
                    </span>
                    <span className="font-medium text-xs text-slate-200">
                      {node.actorName}
                    </span>
                    <span
                      className={`text-[10px] px-1.5 py-0.5 rounded border uppercase font-mono ${OP_BADGES[
                        node.operationType
                      ]}`}
                    >
                      {node.operationType.replace('_', ' ')}
                    </span>
                    {node.isRolledBack && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-500/20 text-red-300 font-mono border border-red-500/30">
                        ROLLED BACK
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    <span className="text-[11px] text-slate-400 font-mono">
                      {new Date(node.timestamp).toLocaleTimeString()}
                    </span>
                    <button
                      type="button"
                      onClick={() =>
                        setExpandedNodeId(isExpanded ? null : node.nodeId)
                      }
                      className="text-slate-400 hover:text-slate-200 p-0.5 rounded"
                      aria-label={isExpanded ? 'Collapse Diff' : 'Expand Diff'}
                    >
                      {isExpanded ? (
                        <ChevronUp className="w-4 h-4" />
                      ) : (
                        <ChevronDown className="w-4 h-4" />
                      )}
                    </button>
                  </div>
                </div>

                {/* Target File & Diff Description */}
                <div className="mt-2 text-xs flex flex-col gap-1">
                  <div className="flex items-center gap-1.5 font-mono text-slate-300">
                    <Code2 className="w-3.5 h-3.5 text-indigo-400" />
                    <span>{node.filePath}</span>
                    {node.lineStart !== undefined && (
                      <span className="text-slate-500 text-[11px]">
                        (Lines {node.lineStart}-{node.lineEnd || node.lineStart})
                      </span>
                    )}
                  </div>
                  {node.diffSummary && (
                    <p className="text-slate-400 text-[11px] pl-5">
                      {node.diffSummary}
                    </p>
                  )}
                </div>

                {/* Expanded Diff Preview */}
                {isExpanded && (
                  <div className="mt-3 p-2.5 rounded bg-slate-950/80 border border-slate-800 text-[11px] font-mono space-y-2">
                    {node.beforeContent && (
                      <div>
                        <span className="text-red-400 select-none">- Before:</span>
                        <pre className="text-slate-400 bg-red-950/20 p-1.5 rounded overflow-x-auto whitespace-pre-wrap">
                          {node.beforeContent}
                        </pre>
                      </div>
                    )}
                    {node.afterContent && (
                      <div>
                        <span className="text-emerald-400 select-none">+ After:</span>
                        <pre className="text-slate-300 bg-emerald-950/20 p-1.5 rounded overflow-x-auto whitespace-pre-wrap">
                          {node.afterContent}
                        </pre>
                      </div>
                    )}
                  </div>
                )}

                {/* Cherry-Pick Rollback CTA */}
                {!node.isRolledBack && (
                  <div className="mt-3 pt-2.5 border-t border-slate-700/50 flex items-center justify-end gap-2">
                    {isConfirming ? (
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-amber-300 flex items-center gap-1">
                          <AlertTriangle className="w-3.5 h-3.5" /> Revert this node
                          only?
                        </span>
                        <button
                          type="button"
                          disabled={isRollingBack}
                          onClick={() => handleExecuteRollback(node)}
                          className="px-2.5 py-1 text-xs bg-red-600 hover:bg-red-500 text-white font-medium rounded transition-colors disabled:opacity-50"
                        >
                          {isRollingBack ? 'Reverting...' : 'Confirm'}
                        </button>
                        <button
                          type="button"
                          disabled={isRollingBack}
                          onClick={() => setConfirmRollbackNodeId(null)}
                          className="px-2 py-1 text-xs bg-slate-700 hover:bg-slate-600 text-slate-300 rounded transition-colors"
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        onClick={() => setConfirmRollbackNodeId(node.nodeId)}
                        className="flex items-center gap-1.5 px-2.5 py-1 text-xs bg-slate-700 hover:bg-slate-600 text-slate-200 rounded transition-colors"
                      >
                        <RotateCcw className="w-3 h-3 text-amber-400" />
                        <span>Cherry-Pick Undo</span>
                      </button>
                    )}
                  </div>
                )}
              </article>
            );
          })
        )}
      </div>
    </section>
  );
};

export default VisualTimelineCherryPickCard;
