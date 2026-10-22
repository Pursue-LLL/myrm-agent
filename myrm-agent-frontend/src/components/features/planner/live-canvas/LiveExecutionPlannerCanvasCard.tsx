/**
 * Live Execution Planner Canvas Card
 * 智能体执行实时规划动态画布、DAG 任务流图谱与沙箱即时预览联动顶层卡片
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 零原生 emoji，全部采用 Lucide 矢量图标；
 * 3. 前端所有 if 显式包裹大括号；
 * 4. 严格遵守 a11y 规范与响应式布局；
 * 5. 行数严格受控在 400 行以内。
 */

import React from 'react';
import {
  Columns2,
  GitBranch,
  Layers,
  LayoutGrid,
  RotateCcw,
  Sparkles,
} from 'lucide-react';
import { CanvasViewMode } from './plannerCanvasTypes';
import { PlannerDagGraphView } from './PlannerDagGraphView';
import { SandboxLivePreviewView } from './SandboxLivePreviewView';
import { usePlannerCanvasStore } from './usePlannerCanvasStore';

export interface LiveExecutionPlannerCanvasCardProps {
  className?: string;
}

export const LiveExecutionPlannerCanvasCard: React.FC<
  LiveExecutionPlannerCanvasCardProps
> = ({ className = '' }) => {
  const {
    nodes,
    viewMode,
    selectedNodeId,
    setViewMode,
    resetToMockPlanner,
    getSelectedNode,
  } = usePlannerCanvasStore();

  const selectedNode = getSelectedNode();

  const completedCount = nodes.filter((n) => n.status === 'completed').length;
  const runningNode = nodes.find((n) => n.status === 'running');

  return (
    <div
      data-testid="live-execution-planner-canvas-card"
      className={`flex flex-col gap-4 rounded-xl border border-neutral-800 bg-neutral-950 p-5 text-neutral-100 ${className}`}
    >
      {/* 头部：标题、进度与视图模式控制器 */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-neutral-800/80 pb-3.5">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-indigo-500/30 bg-indigo-950/40 text-indigo-400">
            <GitBranch className="h-4 w-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-neutral-100">
                实时执行规划动态画布 & 沙箱预览
              </h3>
              <span
                data-testid="planner-progress-badge"
                className="inline-flex items-center gap-1 rounded bg-indigo-500/20 px-2 py-0.5 text-[10px] font-medium text-indigo-300"
              >
                <Sparkles className="h-3 w-3" />
                <span>
                  进度 {completedCount}/{nodes.length}
                </span>
              </span>
            </div>
            <p className="text-xs text-neutral-400">
              打破纯文本黑盒限制，动态追踪长程 DAG 任务链与前端产物沙箱即时热预览
            </p>
          </div>
        </div>

        {/* 视图模式与控制动作 */}
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1 rounded-lg border border-neutral-800 bg-neutral-900 p-0.5 text-xs">
            <button
              type="button"
              onClick={() => {
                setViewMode('split');
              }}
              data-testid="viewmode-btn-split"
              className={`flex items-center gap-1 rounded px-2 py-1 text-xs transition-colors ${
                viewMode === 'split'
                  ? 'bg-indigo-950 font-medium text-indigo-300'
                  : 'text-neutral-400 hover:text-neutral-200'
              }`}
              title="双栏分屏联动"
            >
              <Columns2 className="h-3 w-3" />
              <span>分屏</span>
            </button>

            <button
              type="button"
              onClick={() => {
                setViewMode('planner-only');
              }}
              data-testid="viewmode-btn-planner"
              className={`flex items-center gap-1 rounded px-2 py-1 text-xs transition-colors ${
                viewMode === 'planner-only'
                  ? 'bg-indigo-950 font-medium text-indigo-300'
                  : 'text-neutral-400 hover:text-neutral-200'
              }`}
              title="仅展示 DAG 规划画布"
            >
              <LayoutGrid className="h-3 w-3" />
              <span>画布</span>
            </button>

            <button
              type="button"
              onClick={() => {
                setViewMode('sandbox-only');
              }}
              data-testid="viewmode-btn-sandbox"
              className={`flex items-center gap-1 rounded px-2 py-1 text-xs transition-colors ${
                viewMode === 'sandbox-only'
                  ? 'bg-indigo-950 font-medium text-indigo-300'
                  : 'text-neutral-400 hover:text-neutral-200'
              }`}
              title="仅展示沙箱预览视窗"
            >
              <Layers className="h-3 w-3" />
              <span>沙箱</span>
            </button>
          </div>

          <button
            type="button"
            onClick={resetToMockPlanner}
            data-testid="reset-planner-btn"
            className="flex items-center gap-1 rounded-lg border border-neutral-800 bg-neutral-900 px-2.5 py-1.5 text-xs text-neutral-400 hover:text-neutral-200"
            title="重置模拟执行规划数据"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            <span>重置</span>
          </button>
        </div>
      </div>

      {/* 进行中状态提示条 */}
      {runningNode && (
        <div
          data-testid="running-node-banner"
          className="flex items-center justify-between rounded-lg border border-indigo-500/30 bg-indigo-950/20 px-3 py-2 text-xs text-indigo-300"
        >
          <div className="flex items-center gap-2">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-indigo-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-indigo-500" />
            </span>
            <span>
              正在执行第 {nodes.findIndex((n) => n.id === runningNode.id) + 1} 步：
              <strong className="text-neutral-200 ml-1">{runningNode.title}</strong>
            </span>
          </div>
          {runningNode.durationMs ? (
            <span className="font-mono text-[11px] text-neutral-400">
              已耗时 {runningNode.durationMs}ms
            </span>
          ) : null}
        </div>
      )}

      {/* 主工作区：根据 viewMode 动态排版 */}
      <div
        className={`grid gap-4 ${
          viewMode === 'split'
            ? 'grid-cols-1 lg:grid-cols-12'
            : 'grid-cols-1'
        }`}
      >
        {/* 左侧/上方：DAG 动态规划画布 */}
        {(viewMode === 'split' || viewMode === 'planner-only') && (
          <div
            className={viewMode === 'split' ? 'lg:col-span-7' : 'w-full'}
          >
            <PlannerDagGraphView className="h-[360px]" />
          </div>
        )}

        {/* 右侧/下方：沙箱即时预览视窗 */}
        {(viewMode === 'split' || viewMode === 'sandbox-only') && (
          <div
            className={viewMode === 'split' ? 'lg:col-span-5' : 'w-full'}
          >
            <SandboxLivePreviewView className="h-[360px]" />
          </div>
        )}
      </div>

      {/* 底部：当前选中的节点细节详情卡 */}
      {selectedNode && (
        <div
          data-testid="selected-node-details"
          className="rounded-lg border border-neutral-800 bg-neutral-900/60 p-3 text-xs"
        >
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-neutral-800 pb-2">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-neutral-200">
                {selectedNode.title}
              </span>
              <span className="rounded bg-neutral-800 px-1.5 py-0.5 text-[10px] font-mono text-neutral-400">
                ID: {selectedNode.id}
              </span>
            </div>

            {selectedNode.dependsOn.length > 0 && (
              <span className="text-[11px] text-neutral-500">
                前置依赖: {selectedNode.dependsOn.join(', ')}
              </span>
            )}
          </div>

          <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-neutral-400">
            <p className="text-[11px]">{selectedNode.description}</p>
            {selectedNode.tools && selectedNode.tools.length > 0 && (
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] text-neutral-500">工具调用:</span>
                {selectedNode.tools.map((tool) => (
                  <span
                    key={tool.toolName}
                    className="rounded bg-neutral-800 px-1.5 py-0.5 font-mono text-[10px] text-indigo-300"
                  >
                    {tool.toolName} ({tool.durationMs}ms)
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
