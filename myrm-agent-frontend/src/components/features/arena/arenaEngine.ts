import type {
  ArenaModelConfig,
  ArenaModelStream,
} from './arenaTypes';

export const DEFAULT_ARENA_MODELS: readonly ArenaModelConfig[] = [
  {
    id: 'claude-3-7-thinking',
    name: 'Claude 3.7 Sonnet (Thinking)',
    provider: 'Anthropic',
    tier: 'reasoning',
    contextWindow: '200k',
    badgeColor: 'indigo',
  },
  {
    id: 'deepseek-r1',
    name: 'DeepSeek-R1',
    provider: 'DeepSeek',
    tier: 'reasoning',
    contextWindow: '128k',
    badgeColor: 'sky',
  },
  {
    id: 'gpt-4o',
    name: 'GPT-4o',
    provider: 'OpenAI',
    tier: 'pro',
    contextWindow: '128k',
    badgeColor: 'emerald',
  },
  {
    id: 'gemini-2-5-pro',
    name: 'Gemini 2.5 Pro',
    provider: 'Google',
    tier: 'pro',
    contextWindow: '1M',
    badgeColor: 'amber',
  },
];

export function createInitialStreamState(modelId: string): ArenaModelStream {
  return {
    modelId,
    status: 'idle',
    reasoningText: undefined,
    contentText: '',
    latencyMs: 0,
    tokenCount: 0,
    error: undefined,
  };
}

export function buildSynthesizePrompt(
  originalPrompt: string,
  streams: readonly ArenaModelStream[]
): string {
  const modelContents = streams
    .filter((s) => {
      return s.contentText.trim().length > 0;
    })
    .map((s, index) => {
      return `【模型输出 ${index + 1} (${s.modelId})】:\n${s.contentText.trim()}`;
    })
    .join('\n\n---\n\n');

  return `你是一名资深全栈架构师与技术专家。请根据用户的原始提问以及以下各模型给出的不同侧重点方案，进行深度融合：
1. 提炼各模型给出的核心优势与最优算法/观点；
2. 消除冗余与潜在逻辑缺陷；
3. 输出一份结构严谨、可直接落地执行的终极合成方案。

【原始提问】：
${originalPrompt}

${modelContents}`;
}

export function validateLocalProjectPath(path: string): {
  isValid: boolean;
  normalizedPath: string;
  error?: string;
} {
  const trimmed = path.trim();
  if (!trimmed) {
    return {
      isValid: false,
      normalizedPath: '',
      error: '项目路径不能为空',
    };
  }

  // 基础防注入与绝对/用户主目录路径校验
  if (trimmed.includes('..') || trimmed.includes('<') || trimmed.includes('>')) {
    return {
      isValid: false,
      normalizedPath: trimmed,
      error: '路径包含非法遍历或特殊字符',
    };
  }

  const isAbsolute =
    trimmed.startsWith('/') || trimmed.startsWith('~') || /^[a-zA-Z]:\\/.test(trimmed);

  if (!isAbsolute) {
    return {
      isValid: false,
      normalizedPath: trimmed,
      error: '必须提供系统绝对路径或 ~ 用户主目录路径',
    };
  }

  return {
    isValid: true,
    normalizedPath: trimmed.replace(/\\/g, '/'),
  };
}

export function calculateDiffSimilarity(
  contentA: string,
  contentB: string
): { similarityPercentage: number; charDiffCount: number } {
  if (contentA === contentB) {
    return {
      similarityPercentage: 100,
      charDiffCount: 0,
    };
  }

  const lengthA = contentA.length;
  const lengthB = contentB.length;
  const maxLen = Math.max(lengthA, lengthB);

  if (maxLen === 0) {
    return {
      similarityPercentage: 100,
      charDiffCount: 0,
    };
  }

  const diffCount = Math.abs(lengthA - lengthB);
  const similarity = Math.max(0, Math.round(((maxLen - diffCount) / maxLen) * 100));

  return {
    similarityPercentage: similarity,
    charDiffCount: diffCount,
  };
}
