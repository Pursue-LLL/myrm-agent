/**
 * Planner Canvas Zustand Store
 * 智能体实时规划画布与沙箱预览状态控制器
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 所有 if 显式包裹大括号；
 * 3. 行数严格受控在 400 行以内；
 * 4. 纯净状态流转，响应式支持沙箱联动与多视口切换。
 */

import { create } from 'zustand';
import {
  CanvasViewMode,
  PlannerArtifactRef,
  PlannerDagNode,
  PlannerNodeStatus,
  SandboxViewportMode,
} from './plannerCanvasTypes';

interface PlannerCanvasState {
  nodes: PlannerDagNode[];
  selectedNodeId: string | null;
  viewportMode: SandboxViewportMode;
  viewMode: CanvasViewMode;
  isAutoCentering: boolean;
  sandboxReloadKey: number;

  // Actions
  setNodes: (nodes: PlannerDagNode[]) => void;
  updateNodeStatus: (
    nodeId: string,
    status: PlannerNodeStatus,
    durationMs?: number,
    errorMessage?: string
  ) => void;
  selectNode: (nodeId: string | null) => void;
  setViewportMode: (mode: SandboxViewportMode) => void;
  setViewMode: (mode: CanvasViewMode) => void;
  triggerSandboxReload: () => void;
  resetToMockPlanner: () => void;
  getSelectedNode: () => PlannerDagNode | undefined;
  getActiveArtifact: () => PlannerArtifactRef | undefined;
}

const DEFAULT_SANDBOX_HTML = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Agent 生成组件预览</title>
  <style>
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #09090b;
      color: #fafafa;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      margin: 0;
      padding: 20px;
      box-sizing: border-box;
    }
    .card {
      background: #18181b;
      border: 1px solid #27272a;
      border-radius: 12px;
      padding: 24px;
      max-width: 420px;
      width: 100%;
      box-shadow: 0 10px 25px rgba(0,0,0,0.5);
    }
    h2 { margin: 0 0 10px 0; font-size: 18px; color: #6366f1; }
    p { font-size: 13px; color: #a1a1aa; line-height: 1.5; margin: 0 0 16px 0; }
    .badge {
      display: inline-block;
      background: rgba(99, 102, 241, 0.15);
      color: #818cf8;
      border-radius: 9999px;
      padding: 4px 10px;
      font-size: 11px;
      font-weight: 600;
      margin-bottom: 12px;
    }
    button {
      background: #4f46e5;
      color: #fff;
      border: none;
      border-radius: 8px;
      padding: 10px 16px;
      font-size: 13px;
      font-weight: 500;
      cursor: pointer;
      width: 100%;
    }
    button:hover { background: #4338ca; }
  </style>
</head>
<body>
  <div class="card">
    <div class="badge">沙箱即时预览视窗</div>
    <h2>实时交互式指标看板</h2>
    <p>该组件由智能体在长程规划执行完成后自动生成并注入隔离沙箱运行。</p>
    <button onclick="alert('组件交互事件正常响应')">点击触发交互测试</button>
  </div>
</body>
</html>`;

export const MOCK_PLANNER_NODES: PlannerDagNode[] = [
  {
    id: 'step-1-analysis',
    title: '意图拆解与依赖分析',
    description: '提取用户业务目标并生成子任务依赖图',
    status: 'completed',
    dependsOn: [],
    durationMs: 420,
    tools: [{ toolName: 'parse_user_intent', durationMs: 120 }],
  },
  {
    id: 'step-2-schema',
    title: '数据模型与状态机定义',
    description: '构建强类型数据字典与事件流规范',
    status: 'completed',
    dependsOn: ['step-1-analysis'],
    durationMs: 780,
    tools: [{ toolName: 'generate_type_schema', durationMs: 250 }],
  },
  {
    id: 'step-3-codegen',
    title: '生成前端 UI 交互组件',
    description: '编写响应式卡片与交互式沙箱宿主页面',
    status: 'running',
    dependsOn: ['step-2-schema'],
    durationMs: 1250,
    tools: [
      { toolName: 'write_to_file', durationMs: 480 },
      { toolName: 'bundle_preview', durationMs: 320 },
    ],
    artifact: {
      artifactId: 'art-preview-01',
      title: '实时指标看板组件',
      type: 'html',
      rawContent: DEFAULT_SANDBOX_HTML,
    },
  },
  {
    id: 'step-4-lint',
    title: '双门禁静态审计与单测',
    description: '执行 oxlint 静态代码检测与 Vitest 全自动化单测',
    status: 'pending',
    dependsOn: ['step-3-codegen'],
    durationMs: 0,
  },
  {
    id: 'step-5-deploy',
    title: '沙箱部署与交付就绪',
    description: '将产物热载入预览环境并更新规划状态',
    status: 'pending',
    dependsOn: ['step-4-lint'],
    durationMs: 0,
  },
];

export const usePlannerCanvasStore = create<PlannerCanvasState>((set, get) => ({
  nodes: MOCK_PLANNER_NODES,
  selectedNodeId: 'step-3-codegen',
  viewportMode: 'desktop',
  viewMode: 'split',
  isAutoCentering: true,
  sandboxReloadKey: 1,

  setNodes: (nodes: PlannerDagNode[]) => {
    set({ nodes });
  },

  updateNodeStatus: (
    nodeId: string,
    status: PlannerNodeStatus,
    durationMs?: number,
    errorMessage?: string
  ) => {
    set((state) => ({
      nodes: state.nodes.map((node) => {
        if (node.id === nodeId) {
          return {
            ...node,
            status,
            durationMs: durationMs !== undefined ? durationMs : node.durationMs,
            errorMessage,
          };
        }
        return node;
      }),
    }));
  },

  selectNode: (nodeId: string | null) => {
    set({ selectedNodeId: nodeId });
  },

  setViewportMode: (mode: SandboxViewportMode) => {
    set({ viewportMode: mode });
  },

  setViewMode: (mode: CanvasViewMode) => {
    set({ viewMode: mode });
  },

  triggerSandboxReload: () => {
    set((state) => ({ sandboxReloadKey: state.sandboxReloadKey + 1 }));
  },

  resetToMockPlanner: () => {
    set({
      nodes: JSON.parse(JSON.stringify(MOCK_PLANNER_NODES)) as PlannerDagNode[],
      selectedNodeId: 'step-3-codegen',
      viewportMode: 'desktop',
      viewMode: 'split',
      sandboxReloadKey: 1,
    });
  },

  getSelectedNode: () => {
    const state = get();
    return state.nodes.find((n) => n.id === state.selectedNodeId);
  },

  getActiveArtifact: () => {
    const selected = get().getSelectedNode();
    if (selected && selected.artifact) {
      return selected.artifact;
    }
    // 回退到第一个拥有产物的节点
    for (const node of get().nodes) {
      if (node.artifact) {
        return node.artifact;
      }
    }
    return undefined;
  },
}));
