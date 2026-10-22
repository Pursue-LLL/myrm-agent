'use client';

import React, { useState, useId, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import {
  Clock,
  CheckCircle2,
  AlertCircle,
  Loader2,
  CornerDownLeft,
  ChevronRight,
  ChevronDown,
  Zap,
  X,
  Layers,
  RefreshCw,
  Cpu,
} from 'lucide-react';
import { useTaskInspectorStore } from './useTaskInspectorStore';
import type { TimelineStepNode } from './taskInspectorTypes';

export const TaskExecutionTimelineDrawer: React.FC = () => {
  const t = useTranslations('taskInspector');
  const modalId = useId();

  const isOpen = useTaskInspectorStore((s) => s.isOpen);
  const activeTaskId = useTaskInspectorStore((s) => s.activeTaskId);
  const viewMode = useTaskInspectorStore((s) => s.viewMode);
  const timelineData = useTaskInspectorStore((s) => s.timelineData);
  const isLoading = useTaskInspectorStore((s) => s.isLoading);
  const isInterrupting = useTaskInspectorStore((s) => s.isInterrupting);
  const selectedNodeId = useTaskInspectorStore((s) => s.selectedNodeId);
  const expandedNodeIds = useTaskInspectorStore((s) => s.expandedNodeIds);
  const error = useTaskInspectorStore((s) => s.error);

  const closeInspector = useTaskInspectorStore((s) => s.closeInspector);
  const setViewMode = useTaskInspectorStore((s) => s.setViewMode);
  const selectNode = useTaskInspectorStore((s) => s.selectNode);
  const toggleExpand = useTaskInspectorStore((s) => s.toggleExpand);
  const fetchTimeline = useTaskInspectorStore((s) => s.fetchTimeline);
  const interruptTask = useTaskInspectorStore((s) => s.interruptTask);

  const [bargeInInstruction, setBargeInInstruction] = useState('');

  // Keyboard shortcut: Escape to close
  useEffect(() => {
    if (!isOpen) {
      return;
    }
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        closeInspector();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, closeInspector]);

  if (!isOpen) {
    return null;
  }

  const nodes = viewMode === 'tree' ? timelineData?.tree ?? [] : timelineData?.waterfall ?? [];
  const summary = timelineData?.summary;

  const selectedNode =
    timelineData?.waterfall.find((n) => n.node_id === selectedNodeId) ?? null;

  const handleInterrupt = async () => {
    if (!bargeInInstruction.trim()) {
      return;
    }
    try {
      await interruptTask('user_barge_in', bargeInInstruction.trim());
      setBargeInInstruction('');
    } catch {
      // Handled in store
    }
  };

  const renderNodeRow = (node: TimelineStepNode, depth = 0) => {
    const isSelected = selectedNodeId === node.node_id;
    const isExpanded = expandedNodeIds.includes(node.node_id);
    const hasChildren = node.children && node.children.length > 0;

    return (
      <div key={node.node_id} className="flex flex-col">
        <div
          style={{ paddingLeft: `${depth * 16 + 12}px` }}
          className={`flex items-center justify-between py-2 pr-3 text-xs rounded-lg transition-colors ${
            isSelected
              ? 'bg-amber-500/15 border border-amber-500/30 text-amber-200'
              : 'hover:bg-surface-800/60 text-surface-200 border border-transparent'
          }`}
        >
          <div className="flex items-center gap-2 min-w-0 flex-1">
            {hasChildren ? (
              <button
                type="button"
                aria-label={isExpanded ? 'Collapse step' : 'Expand step'}
                onClick={(e) => {
                  e.stopPropagation();
                  toggleExpand(node.node_id);
                }}
                className="p-0.5 text-surface-400 hover:text-surface-100 shrink-0"
              >
                {isExpanded ? (
                  <ChevronDown className="w-3.5 h-3.5" />
                ) : (
                  <ChevronRight className="w-3.5 h-3.5" />
                )}
              </button>
            ) : (
              <span className="w-3.5 h-3.5 shrink-0" />
            )}

            <button
              type="button"
              onClick={() => selectNode(node.node_id)}
              className="flex items-center gap-2 min-w-0 flex-1 text-left"
            >
              {/* Status Icon */}
              {node.status === 'running' && (
                <Loader2 className="w-3.5 h-3.5 text-amber-400 animate-spin shrink-0" />
              )}
              {node.status === 'completed' && (
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
              )}
              {node.status === 'failed' && (
                <AlertCircle className="w-3.5 h-3.5 text-rose-400 shrink-0" />
              )}
              {node.status === 'interrupted' && (
                <Clock className="w-3.5 h-3.5 text-purple-400 shrink-0" />
              )}

              <span className="font-mono font-medium truncate">{node.step_name}</span>
              <span className="px-1.5 py-0.5 text-[10px] rounded bg-surface-800 text-surface-400 font-mono shrink-0">
                {node.node_type}
              </span>
              {node.metrics.cache_hit && (
                <span className="flex items-center gap-0.5 text-[10px] text-emerald-400 bg-emerald-500/10 px-1.5 py-0.5 rounded shrink-0">
                  <Zap className="w-2.5 h-2.5" />
                  {t('cacheHit')}
                </span>
              )}
            </button>
          </div>

          <span className="font-mono text-surface-400 text-[11px] shrink-0 ml-2">
            {node.duration_ms !== null ? `${Math.round(node.duration_ms)}ms` : 'running...'}
          </span>
        </div>

        {/* Nested Children in Tree mode */}
        {viewMode === 'tree' && isExpanded && hasChildren && (
          <div className="flex flex-col">
            {node.children.map((child) => renderNodeRow(child, depth + 1))}
          </div>
        )}
      </div>
    );
  };

  return (
    <dialog
      id={modalId}
      open
      aria-labelledby={`${modalId}-title`}
      className="fixed inset-0 z-50 flex items-center justify-end w-full h-full p-0 bg-black/60 backdrop-blur-sm"
    >
      <div className="relative flex flex-col w-full max-w-2xl h-full bg-surface-900 border-l border-surface-800 shadow-2xl overflow-hidden animate-in slide-in-from-right duration-200">
        {/* Header */}
        <header className="flex items-center justify-between px-6 py-4 border-b border-surface-800 bg-surface-900/95">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              <Layers className="w-4 h-4" />
            </div>
            <div>
              <h2 id={`${modalId}-title`} className="text-sm font-semibold text-surface-100">
                {t('title')}
              </h2>
              <p className="text-xs text-surface-400">{activeTaskId || t('subtitle')}</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={isLoading || !activeTaskId}
              onClick={() => {
                if (activeTaskId) {
                  void fetchTimeline(activeTaskId);
                }
              }}
              title={t('refresh')}
              className="p-1.5 text-surface-400 hover:text-surface-100 hover:bg-surface-800 rounded-lg transition-colors"
            >
              <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
            </button>
            <button
              type="button"
              onClick={closeInspector}
              title={t('close')}
              className="p-1.5 text-surface-400 hover:text-surface-100 hover:bg-surface-800 rounded-lg transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </header>

        {/* Summary Metric Ribbon & View Toggle */}
        <div className="flex items-center justify-between px-6 py-2.5 border-b border-surface-800/60 bg-surface-950/40">
          <div className="flex items-center gap-2">
            <span className="flex items-center gap-1 text-xs text-surface-300 font-mono">
              <Clock className="w-3.5 h-3.5 text-amber-400" />
              {t('totalDuration', { ms: summary?.total_duration_ms ?? 0 })}
            </span>
            <span className="flex items-center gap-1 text-xs text-surface-400 font-mono">
              <Cpu className="w-3.5 h-3.5 text-indigo-400" />
              {t('totalTokens', { tokens: summary?.total_tokens ?? 0 })}
            </span>
          </div>

          <div className="flex items-center gap-1 bg-surface-800/60 p-0.5 rounded-lg border border-surface-700/40">
            <button
              type="button"
              onClick={() => setViewMode('tree')}
              className={`px-2.5 py-1 text-xs font-medium rounded transition-colors ${
                viewMode === 'tree' ? 'bg-indigo-500/20 text-indigo-300' : 'text-surface-400'
              }`}
            >
              {t('treeView')}
            </button>
            <button
              type="button"
              onClick={() => setViewMode('waterfall')}
              className={`px-2.5 py-1 text-xs font-medium rounded transition-colors ${
                viewMode === 'waterfall' ? 'bg-indigo-500/20 text-indigo-300' : 'text-surface-400'
              }`}
            >
              {t('waterfallView')}
            </button>
          </div>
        </div>

        {/* Step List / Waterfall Canvas */}
        <main className="flex-1 flex flex-col min-h-0 overflow-hidden">
          <section className="flex-1 p-4 overflow-y-auto border-b border-surface-800/80">
            {nodes.length === 0 ? (
              <p className="text-xs text-surface-500 italic text-center py-12">
                {isLoading ? t('loading') : t('noSteps')}
              </p>
            ) : (
              <div className="space-y-1">
                {nodes.map((node) => renderNodeRow(node))}
              </div>
            )}
          </section>

          {/* Node Inspector Detail Panel */}
          {selectedNode && (
            <aside className="h-48 p-4 overflow-y-auto bg-surface-950/60 border-t border-surface-800 text-xs space-y-3">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-surface-200">{t('nodeDetailTitle')}: {selectedNode.step_name}</span>
                <span className="font-mono text-surface-400">ID: {selectedNode.node_id}</span>
              </div>

              {selectedNode.input_payload && (
                <div>
                  <p className="font-medium text-surface-400 mb-1">{t('inputPayload')}</p>
                  <pre className="p-2 bg-surface-900 border border-surface-800 rounded font-mono text-[11px] text-surface-300 overflow-x-auto">
                    {JSON.stringify(selectedNode.input_payload, null, 2)}
                  </pre>
                </div>
              )}

              {selectedNode.output_payload && (
                <div>
                  <p className="font-medium text-surface-400 mb-1">{t('outputPayload')}</p>
                  <pre className="p-2 bg-surface-900 border border-surface-800 rounded font-mono text-[11px] text-surface-300 overflow-x-auto">
                    {JSON.stringify(selectedNode.output_payload, null, 2)}
                  </pre>
                </div>
              )}

              {selectedNode.error_message && (
                <div className="p-2 bg-rose-500/10 border border-rose-500/20 rounded text-rose-300">
                  <p className="font-medium mb-0.5">{t('errorMessage')}</p>
                  <p className="font-mono text-[11px]">{selectedNode.error_message}</p>
                </div>
              )}
            </aside>
          )}

          {error && (
            <div className="p-3 bg-rose-500/10 border-t border-rose-500/20 text-xs text-rose-300">
              {error}
            </div>
          )}
        </main>

        {/* Footer: Barge-In Steering Bar */}
        <footer className="p-4 border-t border-surface-800 bg-surface-900/95 space-y-2">
          <label htmlFor={`${modalId}-barge-in`} className="text-[11px] font-medium text-surface-400 flex items-center gap-1.5">
            <CornerDownLeft className="w-3.5 h-3.5 text-amber-400" />
            <span>{t('bargeInTitle')}</span>
          </label>
          <div className="flex items-center gap-2">
            <input
              id={`${modalId}-barge-in`}
              type="text"
              value={bargeInInstruction}
              onChange={(e) => setBargeInInstruction(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  void handleInterrupt();
                }
              }}
              placeholder={t('bargeInPlaceholder')}
              className="flex-1 px-3 py-1.5 text-xs text-surface-100 bg-surface-800 border border-surface-700 rounded-lg focus:outline-none focus:border-amber-500/50"
            />
            <button
              type="button"
              disabled={isInterrupting || !bargeInInstruction.trim()}
              onClick={() => void handleInterrupt()}
              className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-amber-950 bg-amber-400 hover:bg-amber-300 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors shrink-0"
            >
              {isInterrupting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CornerDownLeft className="w-3.5 h-3.5" />}
              <span>{isInterrupting ? t('bargeInInterrupting') : t('bargeInButton')}</span>
            </button>
          </div>
        </footer>
      </div>
    </dialog>
  );
};
