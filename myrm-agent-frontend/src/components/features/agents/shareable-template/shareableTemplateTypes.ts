/**
 * 智能体公共模板分享、零密钥脱敏与免配置克隆契约定义
 */

export interface BotTemplateEntity {
  id: string;
  slug: string;
  title: string;
  description: string;
  authorHandle: string;
  avatarIconName: string; // Lucide icon name, e.g. "ShieldAlert", "Code2"
  baseModel: string;
  systemPrompt: string;
  requiredSkills: string[];
  environmentKeySlots: string[]; // e.g. ["${SERPER_API_KEY}"]
  createdAt: number;
}

export interface SecretScrubbingAudit {
  isSafe: boolean;
  scrubbedKeysCount: number;
  scrubbedFieldNames: string[];
  sanitizedEntity: BotTemplateEntity;
}

export interface DependencyAlignmentReport {
  modelAvailable: boolean;
  recommendedFallbackModel?: string;
  missingSkills: string[];
  canOneClickClone: boolean;
}

export interface CloneExecutionResult {
  success: boolean;
  clonedAgentId: string;
  agentName: string;
  appliedModel: string;
}

export interface ShareableTemplateState {
  isShareModalOpen: boolean;
  activeTemplate: BotTemplateEntity | null;
  scrubbingAudit: SecretScrubbingAudit | null;
  publishedUrl: string;
  isCloneDeckOpen: boolean;
  previewTemplate: BotTemplateEntity | null;
  dependencyReport: DependencyAlignmentReport | null;
  lastCloneResult: CloneExecutionResult | null;
}
