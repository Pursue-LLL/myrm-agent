/**
 * [INPUT]
 * - Speech-to-text transcript text from user utterance
 *
 * [OUTPUT]
 * - VoiceVisualIntentResult: { hasVisualIntent: boolean, category: VoiceVisualIntentType, confidence: number, triggers: string[], cleanText: string }
 *
 * [POS]
 * Client-side visual intent detector for voice screenshot awareness (Item 303).
 * Detects whether a spoken prompt references visible screen items (errors, code, buttons, windows),
 * allowing automatic screenshot capture before dispatching to AgentBridge.
 */

export type VoiceVisualIntentType =
  | 'error_diagnosis'
  | 'ui_element_query'
  | 'code_inspection'
  | 'general_screen'
  | 'none';

export interface VoiceVisualIntentResult {
  readonly hasVisualIntent: boolean;
  readonly category: VoiceVisualIntentType;
  readonly confidence: number;
  readonly triggers: ReadonlyArray<string>;
  readonly cleanText: string;
}

const COLLOQUIAL_PREFIX_RE =
  /^[，。！？\s]*(?:请(?:帮我|给我)?|麻烦你?(?:帮我)?|帮我|给我|现在|看一下|看下|查一下)\s*/u;

interface IntentRule {
  readonly category: VoiceVisualIntentType;
  readonly pattern: RegExp;
  readonly confidence: number;
}

const INTENT_RULES: ReadonlyArray<IntentRule> = [
  {
    category: 'error_diagnosis',
    pattern:
      /(?:这(?:个|段)?(?:报错|异常|错误|error|exception|crash|stacktrace)|为什么(?:报错|报红|挂了|挂掉)|why (?:is|does) this (?:error|exception|fail|crash)|fix this error|solve this error)/iu,
    confidence: 0.95,
  },
  {
    category: 'ui_element_query',
    pattern:
      /(?:这(?:个|条)?(?:按钮|图标|菜单|弹窗|输入框|下拉框|组件|卡片|视图|tab|button|icon|modal|dialog)|点(?:这(?:个|里)|它)?没反应|左(?:上|下)?角|右(?:上|下)?角|what is this button|click this|this modal|this icon)/iu,
    confidence: 0.9,
  },
  {
    category: 'code_inspection',
    pattern:
      /(?:这(?:段|行|个)?(?:代码|函数|类|方法|脚本|code|function|snippet)|终端(?:里|输出|日志)?(?:写的是啥|什么意思)|review this code|look at this function|check this snippet)/iu,
    confidence: 0.88,
  },
  {
    category: 'general_screen',
    pattern:
      /(?:(?:当前|这个)?屏幕(?:上|里)?(?:(?:显示|写|是|有)?(?:的是)?(?:什么|啥|内容)|[^\w\s]*$)|看(?:一下|下)?(?:这里|这个|屏幕)|这(?:里|个)怎么(?:弄|写|填|搞|处理)|look at (?:my|this)?\s*screen|what is (?:this|here|on (?:my|the) screen)|on my screen)/iu,
    confidence: 0.8,
  },
];

export function cleanSpokenTranscript(transcript: string): string {
  let cleaned = transcript.trim();
  let prev = '';
  while (cleaned !== prev) {
    prev = cleaned;
    cleaned = cleaned.replace(COLLOQUIAL_PREFIX_RE, '').trim();
  }
  return cleaned;
}

export function detectVoiceVisualIntent(transcript: string): VoiceVisualIntentResult {
  const cleanText = cleanSpokenTranscript(transcript);
  if (!cleanText) {
    return {
      hasVisualIntent: false,
      category: 'none',
      confidence: 0,
      triggers: [],
      cleanText,
    };
  }

  for (const rule of INTENT_RULES) {
    const match = rule.pattern.exec(cleanText);
    if (match) {
      return {
        hasVisualIntent: true,
        category: rule.category,
        confidence: rule.confidence,
        triggers: [match[0]],
        cleanText,
      };
    }
  }

  return {
    hasVisualIntent: false,
    category: 'none',
    confidence: 0,
    triggers: [],
    cleanText,
  };
}
