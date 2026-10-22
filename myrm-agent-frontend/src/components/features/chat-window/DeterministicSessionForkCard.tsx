'use client';

import { useState, useCallback, useEffect } from 'react';
import {
  GitFork,
  ShieldCheck,
  RotateCcw,
  PlusCircle,
  Copy,
  Layers,
  History,
} from 'lucide-react';

export type ForkScope = 'branch' | 'tree';

export interface ChildSessionLinkData {
  child_session_id: string;
  parent_session_id: string;
  tool_call_id: string;
  fork_scope: ForkScope;
  created_at: number;
  reattach_count: number;
  last_attached_at: number;
}

export interface DeterministicSessionForkCardProps {
  chatId?: string;
  initialChildren?: ChildSessionLinkData[];
  onDismiss?: () => void;
}

export function DeterministicSessionForkCard({
  chatId = 'default-chat-session',
  initialChildren = [],
  onDismiss,
}: DeterministicSessionForkCardProps) {
  const [children, setChildren] = useState<ChildSessionLinkData[]>(initialChildren);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [lastReattached, setLastReattached] = useState<boolean>(false);

  useEffect(() => {
    if (initialChildren.length > 0) {
      setChildren(initialChildren);
    }
  }, [initialChildren]);

  const totalReplays = children.reduce((acc, c) => acc + c.reattach_count, 0);

  const handleForkNewChild = useCallback((scope: ForkScope = 'branch') => {
    const idx = children.length + 1;
    const toolCallId = `call-tool-${idx}`;
    // Simple deterministic hash simulation for UI
    const childId = `child-${Math.abs(
      (chatId + toolCallId).split('').reduce((a, b) => ((a << 5) - a + b.charCodeAt(0)) | 0, 0)
    ).toString(16).substring(0, 8)}`;

    const newLink: ChildSessionLinkData = {
      child_session_id: childId,
      parent_session_id: chatId,
      tool_call_id: toolCallId,
      fork_scope: scope,
      created_at: Date.now() / 1000,
      reattach_count: 0,
      last_attached_at: Date.now() / 1000,
    };

    setChildren((prev) => [newLink, ...prev]);
    setStatusMessage(
      `Forked new child session '${childId}' with scope '${scope}' (idle initial state).`
    );
    setLastReattached(false);
  }, [chatId, children.length]);

  const handleSimulateSafeReplay = useCallback(() => {
    if (children.length === 0) {
      // First create one
      handleForkNewChild('branch');
      return;
    }

    // Pick the most recent child and simulate replay
    const target = children[0];
    if (!target) {
      return;
    }

    setChildren((prev) =>
      prev.map((c) => {
        if (c.child_session_id === target.child_session_id) {
          return {
            ...c,
            reattach_count: c.reattach_count + 1,
            last_attached_at: Date.now() / 1000,
          };
        }
        return c;
      })
    );

    setStatusMessage(
      `Safe Tool Replay: Reattached to '${target.child_session_id}'. Twin child session prevented!`
    );
    setLastReattached(true);
  }, [children, handleForkNewChild]);

  const handleReset = useCallback(() => {
    setChildren([]);
    setStatusMessage('Deterministic session fork repository reset.');
    setLastReattached(false);
  }, []);

  return (
    <dialog
      open
      className="relative flex flex-col w-full max-w-2xl bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-xl shadow-lg p-5 text-zinc-900 dark:text-zinc-100 z-50 overflow-hidden"
      data-testid="deterministic-session-fork-card"
    >
      <div className="flex items-center justify-between pb-3 border-b border-zinc-200 dark:border-zinc-800">
        <div className="flex items-center space-x-2">
          <GitFork className="w-5 h-5 text-cyan-500" />
          <h3 className="font-semibold text-base">Pi Harness v2 Deterministic Subagent Fork</h3>
        </div>
        {onDismiss && (
          <button
            onClick={onDismiss}
            aria-label="Dismiss dialog"
            className="text-xs px-2.5 py-1 rounded bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 dark:hover:bg-zinc-700 text-zinc-600 dark:text-zinc-300 transition-colors"
          >
            Dismiss
          </button>
        )}
      </div>

      <div className="grid grid-cols-3 gap-3 my-4">
        <div className="flex flex-col p-3 rounded-lg bg-cyan-50/60 dark:bg-cyan-950/30 border border-cyan-200/60 dark:border-cyan-800/50">
          <span className="text-xs text-cyan-600 dark:text-cyan-400 font-medium">
            Forked Children
          </span>
          <span className="text-xl font-bold mt-1" data-testid="stat-total-children">
            {children.length}
          </span>
        </div>
        <div className="flex flex-col p-3 rounded-lg bg-emerald-50/60 dark:bg-emerald-950/30 border border-emerald-200/60 dark:border-emerald-800/50">
          <span className="text-xs text-emerald-600 dark:text-emerald-400 font-medium">
            Safe Replays
          </span>
          <span className="text-xl font-bold mt-1" data-testid="stat-total-replays">
            {totalReplays}
          </span>
        </div>
        <div className="flex flex-col p-3 rounded-lg bg-indigo-50/60 dark:bg-indigo-950/30 border border-indigo-200/60 dark:border-indigo-800/50">
          <span className="text-xs text-indigo-600 dark:text-indigo-400 font-medium">
            Prevented Twins
          </span>
          <span className="text-xl font-bold mt-1" data-testid="stat-prevented-twins">
            {totalReplays}
          </span>
        </div>
      </div>

      {statusMessage && (
        <output
          className={`text-xs p-2.5 rounded-lg mb-3 flex items-center space-x-2 border ${
            lastReattached
              ? 'bg-emerald-50 dark:bg-emerald-950/40 border-emerald-300 dark:border-emerald-700/60 text-emerald-800 dark:text-emerald-200'
              : 'bg-zinc-100 dark:bg-zinc-800/60 border-zinc-200 dark:border-zinc-700 text-zinc-700 dark:text-zinc-300'
          }`}
          data-testid="status-message"
        >
          {lastReattached ? (
            <ShieldCheck className="w-4 h-4 text-emerald-500 shrink-0" />
          ) : (
            <Copy className="w-4 h-4 text-cyan-500 shrink-0" />
          )}
          <span>{statusMessage}</span>
        </output>
      )}

      <div className="flex flex-wrap items-center gap-2 mb-4">
        <button
          onClick={() => handleForkNewChild('branch')}
          className="flex items-center space-x-1.5 text-xs px-3 py-1.5 rounded-md bg-cyan-600 hover:bg-cyan-700 text-white font-medium transition-colors"
          data-testid="btn-fork-branch"
        >
          <PlusCircle className="w-3.5 h-3.5" />
          <span>Fork Child (Branch)</span>
        </button>
        <button
          onClick={() => handleForkNewChild('tree')}
          className="flex items-center space-x-1.5 text-xs px-3 py-1.5 rounded-md bg-indigo-600 hover:bg-indigo-700 text-white font-medium transition-colors"
          data-testid="btn-fork-tree"
        >
          <Layers className="w-3.5 h-3.5" />
          <span>Fork Child (Tree)</span>
        </button>
        <button
          onClick={handleSimulateSafeReplay}
          className="flex items-center space-x-1.5 text-xs px-3 py-1.5 rounded-md bg-emerald-600 hover:bg-emerald-700 text-white font-medium transition-colors"
          data-testid="btn-safe-replay"
        >
          <ShieldCheck className="w-3.5 h-3.5" />
          <span>Simulate Safe Replay</span>
        </button>
        <button
          onClick={handleReset}
          className="flex items-center space-x-1.5 text-xs px-2.5 py-1.5 rounded-md bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 dark:hover:bg-zinc-700 text-zinc-600 dark:text-zinc-300 font-medium transition-colors"
          data-testid="btn-reset"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          <span>Reset</span>
        </button>
      </div>

      <div className="space-y-2 mb-4 max-h-48 overflow-y-auto">
        <span className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">
          Deterministic Subagent Sessions Directory
        </span>
        {children.length === 0 ? (
          <div className="text-xs text-zinc-400 py-3 text-center" data-testid="empty-directory">
            No subagent sessions forked yet.
          </div>
        ) : (
          <div className="space-y-1.5" data-testid="children-list">
            {children.map((child) => (
              <div
                key={child.child_session_id}
                className="flex items-center justify-between p-2 rounded-md bg-zinc-50 dark:bg-zinc-800/40 border border-zinc-200 dark:border-zinc-800 text-xs"
                data-testid={`child-item-${child.child_session_id}`}
              >
                <div className="flex items-center space-x-2">
                  <History className="w-3.5 h-3.5 text-zinc-400" />
                  <span className="font-mono font-semibold">{child.child_session_id}</span>
                  <span className="text-zinc-400 font-mono text-[11px]">
                    ({child.tool_call_id})
                  </span>
                </div>
                <div className="flex items-center space-x-3">
                  <span className="text-zinc-400 uppercase text-[10px] tracking-wide">
                    {child.fork_scope}
                  </span>
                  <span
                    className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${
                      child.reattach_count > 0
                        ? 'bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300'
                        : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400'
                    }`}
                  >
                    Replay x{child.reattach_count}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </dialog>
  );
}
