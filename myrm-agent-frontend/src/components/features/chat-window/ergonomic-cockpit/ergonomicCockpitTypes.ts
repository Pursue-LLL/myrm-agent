/**
 * 宽屏大视界人体工效学向心聚合驾驶舱与对话流内联步态 HUD 契约定义
 */

export type ViewportMode = 'compact' | 'standard' | 'wide_ergonomic' | 'ultrawide';

export type AgentWaveformState = 'idle' | 'thinking' | 'tool_executing' | 'streaming' | 'completed';

export interface TaskGaitProgress {
  taskId: string;
  agentId: string;
  currentStep: number;
  totalSteps: number;
  stepTitle: string;
  percentage: number;
  isDecoupledFromInput: boolean; // 核心人机工效学保障：步态与输入框彻底解耦
}

export interface InlineAgentPersona {
  agentId: string;
  name: string;
  role: string;
  avatarIconName: string;
  baseModel: string;
  state: AgentWaveformState;
}

export interface ErgonomicCockpitState {
  viewportMode: ViewportMode;
  isSidePanelsCollapsed: boolean;
  activePersona: InlineAgentPersona;
  currentGait: TaskGaitProgress | null;
}
