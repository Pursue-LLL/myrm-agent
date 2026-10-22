/**
 * 渐进式延迟配置新手引导、零门槛开箱即聊与多合一整合工作台契约定义
 */

export type OnboardingStage =
  | 'first_chat_ready'           // 默认通用智能体已就绪，免 Key 开箱即聊
  | 'deferred_prompt_triggered'  // 遇到特定高级意图，按需温和触发延迟配置建议
  | 'fully_configured';          // 用户已接入自建模型或订阅

export type OnboardingWorkspaceTab = 'chat' | 'files' | 'approvals' | 'search' | 'settings';

export type AttributionCategory = 'key' | 'url_endpoint' | 'network' | 'quota' | 'unknown';

export interface ConnectionFailureAttribution {
  category: AttributionCategory;
  title: string;
  analogy: string;        // 钥匙 / 地址 / 房间 灵魂类比
  hint: string;           // 针对性解释
  rawError: string;       // 原始异常串
  actionText: string;     // 新手可读的排查指引
}

export interface DoctorProbeResult {
  id: string;
  name: string;
  status: 'ok' | 'warning' | 'error';
  message: string;
  fixActionText?: string;
}

export interface ProgressiveOnboardingState {
  stage: OnboardingStage;
  activeTab: OnboardingWorkspaceTab;
  isFirstChatDispatched: boolean;
  firstChatPrompt: string;
  deferredReason?: string;
  failureAttribution: ConnectionFailureAttribution | null;
  doctorProbes: DoctorProbeResult[];
  isDoctorScanning: boolean;
}
