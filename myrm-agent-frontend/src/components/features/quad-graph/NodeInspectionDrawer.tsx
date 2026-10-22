/**
 * [INPUT]
 * - quadGraphTypes: NodeInspectionDrawerProps, GraphNode, NodeSteerPayload, NodeStatus
 *
 * [OUTPUT]
 * - NodeInspectionDrawer: Drill-down inspection panel & live steering cockpit
 *
 * [POS]
 * Node inspection & intervention cockpit for QuadGraphMultiLayerExecutionCanvasAndTopologyInspectionHUD (Item 50 P0).
 * Strictly under 280 lines. Zero `any`.
 */

'use client';

import React, { memo, useState, useCallback } from 'react';
import {
  X,
  Play,
  Pause,
  RotateCw,
  Send,
  Clock,
  Code2,
  AlertCircle,
  CheckCircle2,
  HelpCircle,
  Sliders,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import type { NodeInspectionDrawerProps, NodeStatus } from './quadGraphTypes';

const STATUS_ICONS: Record<NodeStatus, React.ComponentType<{ className?: string }>> = {
  pending: HelpCircle,
  running: Play,
  verifying: Clock,
  completed: CheckCircle2,
  failed: AlertCircle,
};

const STATUS_COLORS: Record<NodeStatus, string> = {
  pending: 'bg-slate-700/60 text-slate-300 border-slate-600',
  running: 'bg-blue-500/20 text-blue-400 border-blue-500/40 animate-pulse',
  verifying: 'bg-purple-500/20 text-purple-400 border-purple-500/40',
  completed: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40',
  failed: 'bg-rose-500/20 text-rose-400 border-rose-500/40',
};

export const NodeInspectionDrawer: React.FC<NodeInspectionDrawerProps> = memo(({
  node,
  isOpen,
  onClose,
  onSteerNode,
  className = '',
}) => {
  const t = useTranslations('quadGraph');
  const [steerInput, setSteerInput] = useState('');

  const handleSendSteer = useCallback(() => {
    if (!node || !steerInput.trim() || !onSteerNode) {
      return;
    }
    onSteerNode({
      nodeId: node.id,
      instruction: steerInput.trim(),
      action: 'steer',
    });
    setSteerInput('');
  }, [node, steerInput, onSteerNode]);

  const handleAction = useCallback((action: 'pause' | 'resume' | 'retry') => {
    if (!node || !onSteerNode) {
      return;
    }
    onSteerNode({
      nodeId: node.id,
      instruction: `Action triggered: ${action}`,
      action,
    });
  }, [node, onSteerNode]);

  if (!isOpen || !node) {
    return null;
  }

  const StatusIcon = STATUS_ICONS[node.status] || HelpCircle;
  const statusBadgeStyle = STATUS_COLORS[node.status] || STATUS_COLORS.pending;

  return (
    <div
      data-testid="node-inspection-drawer-root"
      className={`fixed inset-0 z-50 flex justify-end transition-all ${className}`}
    >
      {/* Backdrop */}
      <button
        type="button"
        className="fixed inset-0 bg-black/40 backdrop-blur-2xs cursor-default"
        onClick={onClose}
        aria-label={t('closeDrawer')}
      />

      <aside
        data-testid="node-inspection-drawer"
        aria-label={t('drawerAriaLabel')}
        className="w-[420px] max-w-[90vw] h-full bg-slate-900 border-l border-slate-800 shadow-2xl flex flex-col z-10 animate-in slide-in-from-right duration-200"
      >
        {/* Header */}
        <header className="px-5 py-4 border-b border-slate-800 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2.5 min-w-0">
            <span className={`p-1.5 rounded-lg border text-xs flex items-center gap-1.5 ${statusBadgeStyle}`}>
              <StatusIcon className="w-3.5 h-3.5" />
              <span className="uppercase font-mono text-[10px] font-bold">{node.status}</span>
            </span>
            <div className="min-w-0">
              <h3 className="text-sm font-semibold text-slate-100 truncate" title={node.label}>
                {node.label}
              </h3>
              <p className="text-[11px] text-slate-400 font-mono">ID: {node.id}</p>
            </div>
          </div>

          <button
            type="button"
            data-testid="close-inspection-btn"
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-slate-200 rounded-lg hover:bg-slate-800 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </header>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-5 flex flex-col gap-4 text-xs">
          {/* Metadata Grid */}
          <div className="grid grid-cols-2 gap-2.5 p-3 rounded-xl bg-slate-800/60 border border-slate-700/60">
            <div>
              <span className="text-[10px] text-slate-400 uppercase font-semibold">{t('layerType')}</span>
              <p className="text-slate-200 font-medium capitalize mt-0.5">{node.layer}</p>
            </div>
            {node.role && (
              <div>
                <span className="text-[10px] text-slate-400 uppercase font-semibold">{t('role')}</span>
                <p className="text-slate-200 font-medium mt-0.5">{node.role}</p>
              </div>
            )}
            <div>
              <span className="text-[10px] text-slate-400 uppercase font-semibold">{t('duration')}</span>
              <p className="text-slate-200 font-mono mt-0.5">{node.durationMs || 0} ms</p>
            </div>
            <div>
              <span className="text-[10px] text-slate-400 uppercase font-semibold">{t('dependenciesCount')}</span>
              <p className="text-slate-200 font-mono mt-0.5">{node.dependencies?.length || 0}</p>
            </div>
          </div>

          {/* Quick Actions Control Strip */}
          <div className="flex items-center gap-2">
            {node.status === 'running' ? (
              <button
                type="button"
                data-testid="pause-node-btn"
                onClick={() => {
                  handleAction('pause');
                }}
                className="flex-1 inline-flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-lg bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border border-amber-500/30 font-medium transition-colors"
              >
                <Pause className="w-3.5 h-3.5" />
                <span>{t('pauseNode')}</span>
              </button>
            ) : (
              <button
                type="button"
                data-testid="resume-node-btn"
                onClick={() => {
                  handleAction('resume');
                }}
                className="flex-1 inline-flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-lg bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 font-medium transition-colors"
              >
                <Play className="w-3.5 h-3.5" />
                <span>{t('resumeNode')}</span>
              </button>
            )}

            <button
              type="button"
              data-testid="retry-node-btn"
              onClick={() => {
                handleAction('retry');
              }}
              className="flex-1 inline-flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-lg bg-slate-800 hover:bg-slate-750 text-slate-200 border border-slate-700 font-medium transition-colors"
            >
              <RotateCw className="w-3.5 h-3.5" />
              <span>{t('retryNode')}</span>
            </button>
          </div>

          {/* Input Snapshot */}
          <div className="flex flex-col gap-1.5">
            <span className="text-[11px] font-semibold text-slate-400 flex items-center gap-1.5">
              <Code2 className="w-3.5 h-3.5 text-blue-400" />
              <span>{t('inputSnapshot')}</span>
            </span>
            <div
              data-testid="node-input-snapshot"
              className="p-3 rounded-xl bg-slate-950 border border-slate-800 font-mono text-[11px] text-slate-300 max-h-36 overflow-y-auto"
            >
              {node.inputSnapshot || t('noInputSnapshot')}
            </div>
          </div>

          {/* Output / Receipt */}
          <div className="flex flex-col gap-1.5">
            <span className="text-[11px] font-semibold text-slate-400 flex items-center gap-1.5">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
              <span>{t('outputReceipt')}</span>
            </span>
            <div
              data-testid="node-output-snapshot"
              className="p-3 rounded-xl bg-slate-950 border border-slate-800 font-mono text-[11px] text-slate-300 max-h-36 overflow-y-auto"
            >
              {node.error ? (
                <span className="text-rose-400">{node.error}</span>
              ) : (
                node.outputSnapshot || t('noOutputSnapshot')
              )}
            </div>
          </div>

          {/* Real-time Steering Cockpit */}
          <div className="mt-auto pt-4 border-t border-slate-800 flex flex-col gap-2">
            <span className="text-[11px] font-semibold text-slate-300 flex items-center gap-1.5">
              <Sliders className="w-3.5 h-3.5 text-purple-400" />
              <span>{t('liveSteerCockpit')}</span>
            </span>
            <div className="flex items-center gap-2">
              <input
                type="text"
                data-testid="steer-input"
                value={steerInput}
                onChange={(e) => {
                  setSteerInput(e.target.value);
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    handleSendSteer();
                  }
                }}
                placeholder={t('steerPlaceholder')}
                className="flex-1 px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
              />
              <button
                type="button"
                data-testid="submit-steer-btn"
                onClick={handleSendSteer}
                disabled={!steerInput.trim()}
                className="px-3 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-800 text-white rounded-lg transition-colors shadow-xs"
                title={t('submitSteer')}
              >
                <Send className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      </aside>
    </div>
  );
});

NodeInspectionDrawer.displayName = 'NodeInspectionDrawer';
