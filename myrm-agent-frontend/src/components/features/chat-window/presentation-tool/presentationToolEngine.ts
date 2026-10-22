import {
  PositionalResolutionResult,
  PresentationPayload,
  SuggestionChipItem,
} from './presentationToolTypes';

/**
 * 文本防注入清洗
 */
export function sanitizePresentationText(text: string): string {
  if (!text) {
    return '';
  }
  return text
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
    .replace(/<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>/gi, '')
    .replace(/<\/?[^>]+(>|$)/g, '')
    .trim();
}

/**
 * 结构化建议芯片强校验网关 (强制单次最多 4 个，文本不超过 32 字符)
 */
export function validateSuggestionChipsPayload(rawChips: unknown): {
  valid: boolean;
  chips: SuggestionChipItem[];
  error?: string;
} {
  if (!Array.isArray(rawChips)) {
    return {
      valid: false,
      chips: [],
      error: '建议芯片载荷必须为数组类型',
    };
  }

  if (rawChips.length === 0) {
    return { valid: true, chips: [] };
  }

  if (rawChips.length > 4) {
    return {
      valid: false,
      chips: [],
      error: `单次展示建议芯片数量最多为 4 个，当前传入 ${rawChips.length} 个`,
    };
  }

  const result: SuggestionChipItem[] = [];
  for (let i = 0; i < rawChips.length; i += 1) {
    const raw = rawChips[i];
    if (typeof raw !== 'object' || raw === null) {
      return {
        valid: false,
        chips: [],
        error: `第 ${i + 1} 个芯片必须为对象结构`,
      };
    }

    const obj = raw as Record<string, unknown>;
    const rawLabel = String(obj.label ?? '').trim();
    if (!rawLabel) {
      return {
        valid: false,
        chips: [],
        error: `第 ${i + 1} 个芯片 label 不能为空`,
      };
    }

    const sanitizedLabel = sanitizePresentationText(rawLabel);
    if (sanitizedLabel.length > 32) {
      return {
        valid: false,
        chips: [],
        error: `芯片「${sanitizedLabel}」文本超出 32 字符上限限制`,
      };
    }

    const id = String(obj.id ?? `chip-${Date.now()}-${i + 1}`);
    const actionQuery = String(obj.actionQuery ?? sanitizedLabel).trim();
    const position = i + 1;

    result.push({
      id,
      label: sanitizedLabel,
      actionQuery,
      position,
    });
  }

  return { valid: true, chips: result };
}

/**
 * 自然语言视差上下文对齐解析器 (Positional Context Grounding)
 * 支持识别“第2个”、“左边那个”、“最后一个”等指代
 */
export function resolvePositionalReference(
  utterance: string,
  presentation: PresentationPayload,
): PositionalResolutionResult {
  const text = utterance.trim().toLowerCase();
  const items = presentation.items;

  if (!text || items.length === 0) {
    return {
      matchedItem: null,
      position: null,
      confidence: 0,
      rationale: '输入文本为空或无可用展示列表',
    };
  }

  let targetPos: number | null = null;
  let rationale = '';

  // 1. 显式中文/英文序号匹配
  if (text.includes('第1个') || text.includes('第一个') || text.includes('第 1 个') || text.includes('first')) {
    targetPos = 1;
    rationale = '精准匹配第 1 项序号指代';
  } else if (text.includes('第2个') || text.includes('第二个') || text.includes('第 2 个') || text.includes('second')) {
    targetPos = 2;
    rationale = '精准匹配第 2 项序号指代';
  } else if (text.includes('第3个') || text.includes('第三个') || text.includes('第 3 个') || text.includes('third')) {
    targetPos = 3;
    rationale = '精准匹配第 3 项序号指代';
  } else if (text.includes('第4个') || text.includes('第四个') || text.includes('第 4 个') || text.includes('fourth')) {
    targetPos = 4;
    rationale = '精准匹配第 4 项序号指代';
  } else if (text.includes('左边') || text.includes('最左') || text.includes('left')) {
    targetPos = 1;
    rationale = '识别左侧首项空间指代';
  } else if (text.includes('右边') || text.includes('最右') || text.includes('最后') || text.includes('right') || text.includes('last')) {
    targetPos = items.length;
    rationale = '识别末尾/右侧空间指代';
  } else if (text.includes('中间') || text.includes('middle')) {
    targetPos = Math.ceil(items.length / 2);
    rationale = '识别中间项空间指代';
  }

  if (targetPos !== null) {
    const matched = items.find((it) => it.position === targetPos);
    if (matched) {
      return {
        matchedItem: matched,
        position: targetPos,
        confidence: 0.95,
        rationale,
      };
    }
  }

  return {
    matchedItem: null,
    position: null,
    confidence: 0,
    rationale: '未在自然语言中识别到确定的空间或数字位置指代',
  };
}
