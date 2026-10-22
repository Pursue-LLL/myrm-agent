import { create } from 'zustand';
import type {
  BotTemplateEntity,
  CloneExecutionResult,
  DependencyAlignmentReport,
  SecretScrubbingAudit,
  ShareableTemplateState,
} from './shareableTemplateTypes';

const SENSITIVE_KEY_PATTERNS = [
  /api[_-]?key/i,
  /secret/i,
  /token/i,
  /auth/i,
  /password/i,
  /credential/i,
  /bearer/i,
];

export function scrubAgentSecrets(rawAgent: {
  id: string;
  name: string;
  description: string;
  avatarIconName?: string;
  baseModel: string;
  systemPrompt: string;
  skills?: string[];
  env?: Record<string, string>;
}): SecretScrubbingAudit {
  const scrubbedFieldNames: string[] = [];
  const environmentKeySlots: string[] = [];

  if (rawAgent.env) {
    for (const [key] of Object.entries(rawAgent.env)) {
      const isSensitive = SENSITIVE_KEY_PATTERNS.some((pattern) => pattern.test(key));
      if (isSensitive) {
        scrubbedFieldNames.push(key);
        const slotName = `\${${key.toUpperCase().replace(/[^A-Z0-9_]/g, '_')}}`;
        environmentKeySlots.push(slotName);
      }
    }
  }

  // 检查 Prompt 中是否硬编码了明显的 sk- 密钥
  let sanitizedPrompt = rawAgent.systemPrompt;
  const hardcodedSecretPattern = /(?:sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{20,})/g;
  if (hardcodedSecretPattern.test(sanitizedPrompt)) {
    scrubbedFieldNames.push('systemPrompt_hardcoded_secret');
    sanitizedPrompt = sanitizedPrompt.replace(hardcodedSecretPattern, '[REDACTED_SECRET]');
  }

  const slug = rawAgent.name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '') || 'bot';

  const sanitizedEntity: BotTemplateEntity = {
    id: `tpl-${rawAgent.id}`,
    slug: `${slug}-${Math.random().toString(36).slice(2, 8)}`,
    title: rawAgent.name,
    description: rawAgent.description,
    authorHandle: '@developer',
    avatarIconName: rawAgent.avatarIconName ?? 'Bot',
    baseModel: rawAgent.baseModel,
    systemPrompt: sanitizedPrompt,
    requiredSkills: rawAgent.skills ?? [],
    environmentKeySlots,
    createdAt: Date.now(),
  };

  return {
    isSafe: true,
    scrubbedKeysCount: scrubbedFieldNames.length,
    scrubbedFieldNames,
    sanitizedEntity,
  };
}

export function evaluateDependencies(
  template: BotTemplateEntity,
  localAvailableModels: string[],
  localInstalledSkills: string[]
): DependencyAlignmentReport {
  const modelAvailable = localAvailableModels.includes(template.baseModel);
  let recommendedFallbackModel: string | undefined;

  if (!modelAvailable) {
    recommendedFallbackModel =
      localAvailableModels.find((m) => m.includes('qwen') || m.includes('claude') || m.includes('gpt')) ??
      localAvailableModels[0] ??
      'default-local-model';
  }

  const missingSkills = template.requiredSkills.filter(
    (skill) => !localInstalledSkills.includes(skill)
  );

  return {
    modelAvailable,
    recommendedFallbackModel,
    missingSkills,
    canOneClickClone: true,
  };
}

interface ShareableTemplateActions {
  openShareModal: (agent: {
    id: string;
    name: string;
    description: string;
    avatarIconName?: string;
    baseModel: string;
    systemPrompt: string;
    skills?: string[];
    env?: Record<string, string>;
  }) => void;
  closeShareModal: () => void;
  openCloneDeck: (
    template: BotTemplateEntity,
    localModels: string[],
    localSkills: string[]
  ) => void;
  closeCloneDeck: () => void;
  executeClone: (overrideModel?: string) => CloneExecutionResult;
  resetState: () => void;
}

export type ShareableTemplateStore = ShareableTemplateState & ShareableTemplateActions;

const INITIAL_STATE: ShareableTemplateState = {
  isShareModalOpen: false,
  activeTemplate: null,
  scrubbingAudit: null,
  publishedUrl: '',
  isCloneDeckOpen: false,
  previewTemplate: null,
  dependencyReport: null,
  lastCloneResult: null,
};

export const useShareableTemplateStore = create<ShareableTemplateStore>((set, get) => ({
  ...INITIAL_STATE,

  openShareModal: (rawAgent) => {
    const audit = scrubAgentSecrets(rawAgent);
    const publishedUrl = `https://myrmagent.ai/t/${audit.sanitizedEntity.slug}`;
    set({
      isShareModalOpen: true,
      activeTemplate: audit.sanitizedEntity,
      scrubbingAudit: audit,
      publishedUrl,
    });
  },

  closeShareModal: () => {
    set({ isShareModalOpen: false });
  },

  openCloneDeck: (template, localModels, localSkills) => {
    const report = evaluateDependencies(template, localModels, localSkills);
    set({
      isCloneDeckOpen: true,
      previewTemplate: template,
      dependencyReport: report,
      lastCloneResult: null,
    });
  },

  closeCloneDeck: () => {
    set({ isCloneDeckOpen: false });
  },

  executeClone: (overrideModel?: string) => {
    const state = get();
    const template = state.previewTemplate;
    if (!template) {
      throw new Error('未加载待克隆的模板数据');
    }

    const appliedModel =
      overrideModel ||
      (state.dependencyReport?.modelAvailable
        ? template.baseModel
        : state.dependencyReport?.recommendedFallbackModel ?? template.baseModel);

    const clonedAgentId = `agent-cloned-${Date.now()}`;
    const result: CloneExecutionResult = {
      success: true,
      clonedAgentId,
      agentName: `${template.title} (已克隆)`,
      appliedModel,
    };

    set({
      lastCloneResult: result,
    });

    return result;
  },

  resetState: () => {
    set(INITIAL_STATE);
  },
}));
