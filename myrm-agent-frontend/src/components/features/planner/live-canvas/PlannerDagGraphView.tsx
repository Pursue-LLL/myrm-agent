/**
 * Planner DAG Graph View
 * 智能体长程多步规划实时 DAG 流程图与 SVG 贝塞尔曲线连接视图
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 零原生 emoji，全部采用 Lucide 矢量图标；
 * 3. 前端所有 if 显式包裹大括号；
 * 4. 严格遵守 a11y 规范（role, button, aria-selected）；
 * 5. 行数严格受控在 400 行以内。
 */

import React, { useMemo } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Code2,
  FileBox,
  FastForward,
  Loader2,
  Wrench,
} from 'lucide-react';
import { layoutPlannerGraph } from './plannerDagLayoutEngine';
import {
  PlannerLayoutNode,
  PlannerNodeStatus,
} from './plannerCanvasTypes';
import { usePlannerCanvasStore } from './usePlannerCanvasStore';

export interface PlannerDagGraphViewProps {
  className?: string;
}

export const PlannerDagGraphView: React.FC<PlannerDagGraphViewProps> = ({
  className = '',
}) => {
  const { nodes, selectedNodeId, selectNode } = usePlannerCanvasStore();

  const layout = useMemo(() => {
    return layoutPlannerGraph(nodes);
  }, [nodes]);

  const renderStatusIcon = (status: PlannerNodeStatus): React.ReactElement => {
    if (status === 'completed') {
      return <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />;
    }
    if (status === 'running') {
      return <Loader2 className="h-3.5 w-3.5 animate-spin text-indigo-400" />;
    }
    if (status === 'validating') {
      return <Loader2 className="h-3.5 w-3.5 animate-spin text-amber-400" />;
    }
    if (status === 'failed') {
      return <AlertCircle className="h-3.5 w-3.5 text-rose-400" />;
    }
    if (status === 'skipped') {
      return <FastForward className="h-3.5 w-3.5 text-neutral-500" />;
    }
    return <Clock className="h-3.5 w-3.5 text-neutral-500" />;
  };

  const getStatusText = (status: PlannerNodeStatus): string => {
    if (status === 'completed') {
      return '已完成';
    }
    if (status === 'running') {
      return '执行中';
    }
    if (status === 'validating') {
      return '门禁校验';
    }
    if (status === 'failed') {
      return '执行失败';
    }
    if (status === 'skipped') {
      return '已跳过';
    }
    return '排队中';
  };

  const formatDuration = (ms?: number): string => {
    if (!ms || ms <= 0) {
      return '-';
    }
    if (ms < 1000) {
      return `${ms}ms`;
    }
    return `${(ms / 1000).toFixed(2)}s`;
  };

  return (
    <div
      data-testid="planner-dag-graph-view"
      className={`relative overflow-auto rounded-lg border border-neutral-800 bg-neutral-950 p-4 ${className}`}
    >
      <div
        className="relative"
        style={{
          width: Math.max(layout.canvasWidth, 600),
          height: Math.max(layout.canvasHeight, 300),
        }}
      >
        {/* 背景微网格 */}
        <div
          className="absolute inset-0 pointer-events-none opacity-20"
          style={{
            backgroundImage:
              'radial-gradient(circle, #4f46e5 1px, transparent 1px)',
            backgroundSize: '24px 24px',
          }}
        />

        {/* SVG 贝塞尔曲线连线层 */}
        <svg
          data-testid="planner-dag-svg"
          className="absolute inset-0 h-full w-full pointer-events-none"
        >
          <defs>
            <linearGradient id="edge-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#4f46e5" stopOpacity="0.8" />
              <stop offset="100%" stopColor="#818cf8" stopOpacity="0.8" />
            </linearGradient>
          </defs>
          {layout.edges.map((edge) => (
            <path
              key={`${edge.from}->${edge.to}`}
              d={edge.pathD}
              fill="none"
              stroke={edge.isActive ? 'url(#edge-gradient)' : '#27272a'}
              strokeWidth={edge.isActive ? 2.5 : 1.5}
              strokeDasharray={edge.isActive ? undefined : '4 4'}
              className="transition-colors duration-300"
            />
          ))}
        </svg>

        {/* 节点层 */}
        {layout.nodes.map((node: PlannerLayoutNode) => {
          const isSelected = selectedNodeId === node.id;
          const isRunning = node.status === 'running';

          return (
            <button
              type="button"
              key={node.id}
              data-testid={`planner-node-${node.id}`}
              onClick={() => {
                selectNode(node.id);
              }}
              aria-pressed={isSelected}
              style={{
                position: 'absolute',
                left: node.x,
                top: node.y,
                width: node.width,
                height: node.height,
              }}
              className={`flex cursor-pointer flex-col justify-between rounded-lg border p-2.5 text-left text-xs transition-all duration-200 select-none ${
                isSelected
                  ? 'border-indigo-500 bg-indigo-950/40 shadow-lg shadow-indigo-500/10 ring-1 ring-indigo-500'
                  : 'border-neutral-800 bg-neutral-900/80 hover:border-neutral-700 hover:bg-neutral-900'
              } ${isRunning ? 'animate-pulse' : ''}`}
            >
              {/* 头部：标题与状态徽标 */}
              <div className="flex items-center justify-between gap-1.5">
                <span className="truncate font-medium text-neutral-200">
                  {node.title}
                </span>
                <span className="flex items-center gap-1 font-mono text-[10px] text-neutral-400">
                  {renderStatusIcon(node.status)}
                  <span>{getStatusText(node.status)}</span>
                </span>
              </div>

              {/* 描述或错误提示 */}
              <p className="line-clamp-1 text-[11px] text-neutral-400">
                {node.errorMessage ? (
                  <span className="text-rose-400">{node.errorMessage}</span>
                ) : (
                  node.description || '无详细描述'
                )}
              </p>

              {/* 底部信息条：耗时、工具调用、产物标识 */}
              <div className="flex items-center justify-between text-[10px] text-neutral-500 border-t border-neutral-800/60 pt-1">
                <div className="flex items-center gap-1">
                  <Clock className="h-2.5 w-2.5" />
                  <span className="font-mono">{formatDuration(node.durationMs)}</span>
                </div>

                <div className="flex items-center gap-2">
                  {node.tools && node.tools.length > 0 && (
                    <span className="flex items-center gap-0.5 rounded bg-neutral-800 px-1 py-0.2 text-[9px] text-neutral-300">
                      <Wrench className="h-2.5 w-2.5 text-indigo-400" />
                      <span>{node.tools.length}</span>
                    </span>
                  )}

                  {node.artifact && (
                    <span
                      title={`产生交付物: ${node.artifact.title}`}
                      className="flex items-center gap-0.5 rounded bg-emerald-500/10 px-1 py-0.2 text-[9px] text-emerald-400"
                    >
                      {node.artifact.type === 'html' ? (
                        <Code2 className="h-2.5 w-2.5" />
                      ) : (
                        <FileBox className="h-2.5 w-2.5" />
                      )}
                      <span>产物</span>
                    </span>
                  )}
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
};
