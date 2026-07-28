/**
 * [INPUT]
 * (none — standalone hook with embedded rules)
 *
 * [OUTPUT]
 * useVisionIntent: Hook providing vision intent classification via bilingual rule matching
 * VisionIntentResult type
 *
 * [POS]
 * Vision intent classifier. Determines if user speech requires camera visual context using bilingual rules.
 */

'use client';

import { useCallback } from 'react';

export type VisionIntentType = 'none' | 'describe_scene' | 'identify_object' | 'read_text' | 'compare_change';

export interface VisionIntentResult {
  needsVision: boolean;
  type: VisionIntentType;
  confidence: number;
  reason: string;
}

const NO_VISION_RESULT: VisionIntentResult = {
  needsVision: false,
  type: 'none',
  confidence: 1,
  reason: 'empty or text-only input',
};

interface VisionRule {
  pattern: RegExp;
  type: VisionIntentType;
  reason: string;
}

const VISION_RULES: VisionRule[] = [
  {
    pattern:
      /(?:屏幕上|画面里|图里|写了什么|文字|字幕|read\s+(?:this|that|the\s+text)|what\s+(?:does\s+it|do\s+(?:these|those))\s+say)/iu,
    type: 'read_text',
    reason: 'text visible in scene',
  },
  {
    pattern:
      /(?:这是什么|这个是什么|这个东西|这玩意|这个按钮|你看一下|what\s+is\s+this|what(?:'s| is)\s+that|identify|recognize)/iu,
    type: 'identify_object',
    reason: 'explicit visual identification',
  },
  {
    pattern:
      /(?:帮我看看|看一下|镜头里|现在看到|描述一下|看得见|看得到|看到画面|看见|看到了?什么|look\s+at|can\s+you\s+see|describe\s+what|show\s+me|what\s+do\s+you\s+see)/iu,
    type: 'describe_scene',
    reason: 'scene description request',
  },
  {
    pattern: /(?:变化|刚才发生|有什么不同|前后对比|过程|what\s+changed|difference|compare|before\s+and\s+after)/iu,
    type: 'compare_change',
    reason: 'change comparison',
  },
];

const TEXT_ONLY_PATTERNS = [
  /(?:总结|翻译|润色|写一段|起个标题|解释一下概念|summarize|translate|write\s+(?:a|me)|explain\s+(?:the\s+)?concept)/iu,
  /(?:帮我写|生成代码|generate\s+code|refactor|debug|fix\s+(?:this|the)\s+(?:bug|error|issue))/iu,
];

function classifyVisionIntent(text: string): VisionIntentResult {
  const normalized = text.trim();
  if (!normalized) return NO_VISION_RESULT;

  for (const pattern of TEXT_ONLY_PATTERNS) {
    if (pattern.test(normalized)) {
      return { needsVision: false, type: 'none', confidence: 0.95, reason: 'text-only task' };
    }
  }

  for (const rule of VISION_RULES) {
    if (rule.pattern.test(normalized)) {
      return { needsVision: true, type: rule.type, confidence: 0.92, reason: rule.reason };
    }
  }

  return { needsVision: false, type: 'none', confidence: 0.6, reason: 'no visual cue detected' };
}

export function useVisionIntent() {
  const classify = useCallback((text: string): VisionIntentResult => {
    return classifyVisionIntent(text);
  }, []);

  return { classify };
}

export { classifyVisionIntent };
