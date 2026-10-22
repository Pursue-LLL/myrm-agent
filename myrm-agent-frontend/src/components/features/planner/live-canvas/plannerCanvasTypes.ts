/**
 * Live Execution Planner Canvas & Sandbox Preview Types
 * 智能体执行实时规划动态画布、DAG 任务流图谱与沙箱即时预览类型系统
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型定义；
 * 2. 状态机严格受控，覆盖全生命周期阶段；
 * 3. 行数严格受控在 200 行以内。
 */

export type PlannerNodeStatus =
  | 'pending'
  | 'running'
  | 'validating'
  | 'completed'
  | 'failed'
  | 'skipped';

export type SandboxViewportMode = 'desktop' | 'tablet' | 'mobile';

export type CanvasViewMode = 'split' | 'planner-only' | 'sandbox-only';

export interface PlannerToolInvocation {
  toolName: string;
  argumentsSummary?: string;
  durationMs?: number;
}

export interface PlannerArtifactRef {
  artifactId: string;
  title: string;
  type: 'html' | 'react' | 'svg' | 'markdown' | 'code';
  previewUrl?: string;
  rawContent?: string;
}

export interface PlannerDagNode {
  id: string;
  title: string;
  description?: string;
  status: PlannerNodeStatus;
  dependsOn: string[];
  tools?: PlannerToolInvocation[];
  artifact?: PlannerArtifactRef;
  durationMs?: number;
  errorMessage?: string;
}

export interface PlannerLayoutNode extends PlannerDagNode {
  x: number;
  y: number;
  width: number;
  height: number;
  layer: number;
}

export interface PlannerDagEdge {
  from: string;
  to: string;
  fromX: number;
  fromY: number;
  toX: number;
  toY: number;
  pathD: string;
  isActive: boolean;
}

export interface PlannerGraphLayout {
  nodes: PlannerLayoutNode[];
  edges: PlannerDagEdge[];
  canvasWidth: number;
  canvasHeight: number;
}
