/**
 * 长任务平行支线对话抽屉与非阻塞即时调优套件类型定义
 */

export type SteeringIntentType =
  | 'status_inquiry'
  | 'incremental_feature'
  | 'parameter_override'
  | 'general_note';

export type SteeringStatus =
  | 'instant_answered'
  | 'pending_injection'
  | 'injected_to_main'
  | 'discarded';

export interface SideChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: number;
  intentType?: SteeringIntentType;
  steeringStatus?: SteeringStatus;
  injectedAtStep?: number;
}

export interface SteeringBufferItem {
  id: string;
  sourceMessageId: string;
  intentType: SteeringIntentType;
  content: string;
  priority: number;
  status: 'pending' | 'consumed' | 'cancelled';
  createdAt: number;
  consumedAtStep?: number;
}

export interface MainTaskProgressInfo {
  taskId: string;
  taskName: string;
  status: 'idle' | 'running' | 'paused' | 'completed';
  currentStep: number;
  totalSteps: number;
  currentStepDescription: string;
}

export interface SideChatState {
  isOpen: boolean;
  isDocked: boolean;
  messages: SideChatMessage[];
  steeringQueue: SteeringBufferItem[];
  mainTask: MainTaskProgressInfo;
  unreadCount: number;
}
