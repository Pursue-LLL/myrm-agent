/**
 * [INPUT]
 * - quadGraphTypes: QuadGraphExecutionCanvasProps, GraphLayerType, GraphNode, GraphEdge
 * - useQuadGraphStore: useQuadGraphStore
 * - GraphViewportSwitcher: GraphViewportSwitcher
 * - NodeInspectionDrawer: NodeInspectionDrawer
 *
 * [OUTPUT]
 * - QuadGraphExecutionCanvas: Dynamic reactive topological execution canvas with node inspection and live steering
 *
 * [POS]
 * Quad-layer topology visualizer for QuadGraphMultiLayerExecutionCanvasAndTopologyInspectionHUD (Item 50 P0).
 * Strictly under 340 lines. Zero `any`.
 */

'use client';

import React, { memo, useMemo, useState, useCallback } from 'react';
import {
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Sparkles,
  Layers,
  ArrowRight,
  Activity,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import type {
  GraphLayerType,
  GraphNode,
  QuadGraphExecutionCanvasProps,
} from './quadGraphTypes';
import { useQuadGraphStore } from './useQuadGraphStore';
import { GraphViewportSwitcher } from './GraphViewportSwitcher';
import { NodeInspectionDrawer } from './NodeInspectionDrawer';

export const QuadGraphExecutionCanvas: React.FC<QuadGraphExecutionCanvasProps> = memo(({
  model,
  activeLayer: propActiveLayer,
  className = '',
  onSteerNode,
}) => {
  const t = useTranslations('quadGraph');
  const store = useQuadGraphStore();

  const [zoomLevel, setZoomLevel] = useState(1);

  // Active layer fallback
  const currentLayer = propActiveLayer || store.activeLayer;

  // Use provided model nodes/edges or fallback to store demo model
  const activeNodes = useMemo(() => {
    const sourceNodes = model?.nodes || store.nodes;
    return sourceNodes.filter((n) => n.layer === currentLayer);
  }, [model, store.nodes, currentLayer]);

  const activeEdges = useMemo(() => {
    const sourceEdges = model?.edges || store.edges;
    return sourceEdges.filter((e) => e.layer === currentLayer);
  }, [model, store.edges, currentLayer]);

  const nodeCountsByLayer = useMemo(() => {
    const sourceNodes = model?.nodes || store.nodes;
    const counts: Record<GraphLayerType, number> = {
      task: 0,
      workflow: 0,
      team: 0,
      communication: 0,
    };
    sourceNodes.forEach((n) => {
      counts[n.layer] = (counts[n.layer] || 0) + 1;
    });
    return counts;
  }, [model, store.nodes]);

  const selectedNode = useMemo(() => {
    if (!store.selectedNodeId) {
      return null;
    }
    const sourceNodes = model?.nodes || store.nodes;
    return sourceNodes.find((n) => n.id === store.selectedNodeId) || null;
  }, [store.selectedNodeId, model, store.nodes]);

  const handleSelectLayer = useCallback((layer: GraphLayerType) => {
    store.setActiveLayer(layer);
  }, [store]);

  const handleNodeClick = useCallback((node: GraphNode) => {
    store.selectNode(node.id);
  }, [store]);

  const handleZoom = useCallback((delta: number) => {
    setZoomLevel((prev) => {
      const next = Math.round((prev + delta) * 100) / 100;
      return Math.min(Math.max(next, 0.6), 1.8);
    });
  }, []);

  const handleResetZoom = useCallback(() => {
    setZoomLevel(1);
  }, []);

  const summary = store.getSummary();

  return (
    <div
      data-testid="quad-graph-canvas-root"
      className={`relative flex flex-col h-full w-full bg-slate-950 text-slate-100 overflow-hidden select-none border border-slate-800 rounded-xl ${className}`}
    >
      {/* Top HUD Control Strip */}
      <header className="absolute top-4 left-4 right-4 z-20 flex items-center justify-between pointer-events-none gap-2 flex-wrap">
        <div className="pointer-events-auto">
          <GraphViewportSwitcher
            activeLayer={currentLayer}
            onSelectLayer={handleSelectLayer}
            nodeCountsByLayer={nodeCountsByLayer}
          />
        </div>

        {/* Zoom & Canvas Tool Strip */}
        <div className="pointer-events-auto inline-flex items-center gap-1 p-1 bg-slate-900/90 border border-slate-800 rounded-xl shadow-lg backdrop-blur-md">
          <button
            type="button"
            data-testid="zoom-in-btn"
            onClick={() => {
              handleZoom(0.15);
            }}
            title={t('zoomIn')}
            className="p-1.5 text-slate-400 hover:text-slate-200 rounded-lg hover:bg-slate-800 transition-colors"
          >
            <ZoomIn className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            data-testid="zoom-out-btn"
            onClick={() => {
              handleZoom(-0.15);
            }}
            title={t('zoomOut')}
            className="p-1.5 text-slate-400 hover:text-slate-200 rounded-lg hover:bg-slate-800 transition-colors"
          >
            <ZoomOut className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            data-testid="zoom-reset-btn"
            onClick={handleResetZoom}
            title={t('resetZoom')}
            className="p-1.5 text-slate-400 hover:text-slate-200 rounded-lg hover:bg-slate-800 transition-colors text-xs font-mono"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
        </div>
      </header>

      {/* Main Graph Stage */}
      <div
        data-testid="graph-stage-viewport"
        className="flex-1 w-full h-full overflow-auto flex items-center justify-center p-12 bg-radial from-slate-900 via-slate-950 to-slate-950"
      >
        <div
          data-testid="graph-transform-container"
          style={{ transform: `scale(${zoomLevel})` }}
          className="transition-transform duration-150 flex flex-col items-center justify-center gap-8 min-w-[600px] py-12"
        >
          {activeNodes.length === 0 ? (
            <div
              data-testid="empty-layer-view"
              className="p-8 text-center text-slate-500 text-xs flex flex-col items-center gap-2"
            >
              <Layers className="w-8 h-8 text-slate-600 stroke-[1.5]" />
              <p>{t('noNodesInLayer')}</p>
            </div>
          ) : (
            <div className="w-full max-w-2xl flex flex-col gap-5">
              {activeNodes.map((node, idx) => {
                const isSelected = store.selectedNodeId === node.id;
                const isHovered = store.hoveredNodeId === node.id;
                const isRunning = node.status === 'running';
                const isCompleted = node.status === 'completed';
                const isVerifying = node.status === 'verifying';
                const isFailed = node.status === 'failed';

                return (
                  <div key={node.id} className="flex flex-col items-center gap-3">
                    {/* Node Card */}
                    <button
                      type="button"
                      data-testid={`graph-node-${node.id}`}
                      onClick={() => {
                        handleNodeClick(node);
                      }}
                      onMouseEnter={() => {
                        store.setHoveredNodeId(node.id);
                      }}
                      onMouseLeave={() => {
                        store.setHoveredNodeId(null);
                      }}
                      className={`w-full p-4 rounded-xl border transition-all cursor-pointer shadow-lg backdrop-blur-sm flex items-center justify-between gap-3 text-left ${
                        isSelected
                          ? 'ring-2 ring-blue-500 border-blue-400 bg-slate-800'
                          : isHovered
                          ? 'border-slate-600 bg-slate-850'
                          : 'border-slate-800 bg-slate-900/80'
                      } ${
                        isRunning
                          ? 'shadow-blue-500/10 border-blue-500/50'
                          : isVerifying
                          ? 'shadow-purple-500/10 border-purple-500/50'
                          : isCompleted
                          ? 'border-emerald-500/40'
                          : isFailed
                          ? 'border-rose-500/40'
                          : ''
                      }`}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        {/* Status Halo Dot */}
                        <span
                          className={`w-3 h-3 rounded-full shrink-0 ${
                            isRunning
                              ? 'bg-blue-400 shadow-md shadow-blue-400 animate-pulse'
                              : isVerifying
                              ? 'bg-purple-400 shadow-md shadow-purple-400'
                              : isCompleted
                              ? 'bg-emerald-400 shadow-sm shadow-emerald-400'
                              : isFailed
                              ? 'bg-rose-400 shadow-md shadow-rose-400'
                              : 'bg-slate-600'
                          }`}
                        />
                        <div className="min-w-0">
                          <h4 className="text-xs font-semibold text-slate-100 truncate">
                            {node.label}
                          </h4>
                          <div className="flex items-center gap-2 mt-0.5 text-[10px] text-slate-400 font-mono">
                            <span>ID: {node.id}</span>
                            {node.role && <span>· {node.role}</span>}
                            {node.durationMs ? <span>· {node.durationMs}ms</span> : null}
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-1.5 shrink-0">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-mono uppercase font-bold ${
                            isRunning
                              ? 'bg-blue-500/20 text-blue-400'
                              : isVerifying
                              ? 'bg-purple-500/20 text-purple-400'
                              : isCompleted
                              ? 'bg-emerald-500/20 text-emerald-400'
                              : isFailed
                              ? 'bg-rose-500/20 text-rose-400'
                              : 'bg-slate-800 text-slate-400'
                          }`}
                        >
                          {node.status}
                        </span>
                      </div>
                    </button>

                    {/* Edge Connection Pointer */}
                    {idx < activeNodes.length - 1 && (
                      <div
                        data-testid={`graph-edge-connector-${idx}`}
                        className="flex flex-col items-center text-slate-600 -my-1.5"
                      >
                        <div className="w-0.5 h-3.5 bg-slate-800" />
                        <ArrowRight className="w-3 h-3 rotate-90 text-slate-600" />
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Footer Metrics Banner */}
      <footer className="px-4 py-2 border-t border-slate-800 bg-slate-950/80 text-[11px] text-slate-400 flex items-center justify-between shrink-0 font-mono">
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1 text-slate-300">
            <Activity className="w-3 h-3 text-blue-400" />
            <span>{t('nodesCount', { count: activeNodes.length })}</span>
          </span>
          <span>·</span>
          <span>{t('edgesCount', { count: activeEdges.length })}</span>
        </div>

        <div className="flex items-center gap-2">
          <span className="flex items-center gap-1 text-emerald-400">
            <Sparkles className="w-3 h-3" />
            <span>{t('completedCount', { count: summary.completedNodes })}</span>
          </span>
          <span>·</span>
          <span className="text-blue-400">{t('runningCount', { count: summary.runningNodes })}</span>
        </div>
      </footer>

      {/* Drill-down Inspection & Steering Drawer */}
      <NodeInspectionDrawer
        node={selectedNode}
        isOpen={store.isInspectionOpen}
        onClose={() => {
          store.setInspectionOpen(false);
        }}
        onSteerNode={(payload) => {
          store.steerNode(payload);
          if (onSteerNode) {
            onSteerNode(payload);
          }
        }}
      />
    </div>
  );
});

QuadGraphExecutionCanvas.displayName = 'QuadGraphExecutionCanvas';
