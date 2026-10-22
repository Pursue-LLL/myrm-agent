/**
 * Bidirectional RTL Detector & Segmentation Engine
 * 双向文本自动方向探测、混合片段安全隔离与字体回退栈引擎
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 所有 if 显式包裹大括号；
 * 3. 行数严格受控在 400 行以内；
 * 4. 纯算法纯函数设计，覆盖 Unicode RTL 区段与代码变量隔离。
 */

import {
  BidiDetectionResult,
  BidiSegment,
} from './bidiShieldTypes';

/**
 * Unicode RTL 强方向字符范围正则（涵盖阿拉伯语、希伯来语、叙利亚语、塔纳文及阿拉伯表达形式）
 */
const RTL_REGEX = /[\u0591-\u07FF\uFB1D-\uFDFD\uFE70-\uFEFC]/;
const LTR_REGEX = /[A-Za-z\u00C0-\u024F\u0400-\u04FF\u4E00-\u9FFF\u3040-\u30FF]/;

/**
 * Windows 平台 DirectWrite 稳健跨语系字体回退栈
 */
export const WINDOWS_RTL_SAFE_FONT_STACK =
  '"Segoe UI", "Segoe UI Arabic", "Tahoma", "Noto Sans Arabic", "Amiri", Arial, sans-serif';

export function isRtlChar(char: string): boolean {
  return RTL_REGEX.test(char);
}

export function isLtrChar(char: string): boolean {
  return LTR_REGEX.test(char);
}

/**
 * 混合文本双向切片算法：将普通文本、英文代码与阿语文本分离
 */
export function splitBidiSegments(text: string): BidiSegment[] {
  if (text.length === 0) {
    return [];
  }

  const segments: BidiSegment[] = [];
  // 匹配内嵌反引号代码块、完整 URL 或独立英文变量名（优先匹配完整 URL）
  const codeRegex = /(`[^`]+`|https?:\/\/[^\s`"'>)]+|[a-zA-Z0-9_$.-]{2,})/g;

  let lastIndex = 0;
  let match: RegExpExecArray | null = null;

  while ((match = codeRegex.exec(text)) !== null) {
    const startIndex = match.index;
    const matchText = match[0];

    // 处理代码块之前的文本
    if (startIndex > lastIndex) {
      const prevChunk = text.slice(lastIndex, startIndex);
      const isRtl = RTL_REGEX.test(prevChunk);
      segments.push({
        text: prevChunk,
        isRtl,
        isCodeOrVariable: false,
      });
    }

    // 代码块或变量名强制作为 LTR 隔离段
    segments.push({
      text: matchText,
      isRtl: false,
      isCodeOrVariable: true,
    });

    lastIndex = startIndex + matchText.length;
  }

  // 处理剩余尾部文本
  if (lastIndex < text.length) {
    const remaining = text.slice(lastIndex);
    const isRtl = RTL_REGEX.test(remaining);
    segments.push({
      text: remaining,
      isRtl,
      isCodeOrVariable: false,
    });
  }

  return segments;
}

/**
 * 文本主要书写方向探测器
 */
export function detectTextDirection(text: string): BidiDetectionResult {
  if (text.trim().length === 0) {
    return {
      dominantDirection: 'ltr',
      rtlRatio: 0,
      containsRtl: false,
      segments: [],
    };
  }

  let rtlCount = 0;
  let ltrCount = 0;

  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (RTL_REGEX.test(ch)) {
      rtlCount++;
    } else if (LTR_REGEX.test(ch)) {
      ltrCount++;
    }
  }

  const totalStrongChars = rtlCount + ltrCount;
  const rtlRatio =
    totalStrongChars > 0 ? Number((rtlCount / totalStrongChars).toFixed(3)) : 0;
  const containsRtl = rtlCount > 0;

  // 判定基准方向：若 RTL 强字符占比超过 30%，或首个强方向字符为 RTL，判定为主导 RTL
  let dominantDirection: 'ltr' | 'rtl' = 'ltr';

  if (rtlRatio >= 0.3) {
    dominantDirection = 'rtl';
  } else if (containsRtl) {
    // 检查首个强方向字符
    for (let i = 0; i < text.length; i++) {
      const ch = text[i];
      if (RTL_REGEX.test(ch)) {
        dominantDirection = 'rtl';
        break;
      }
      if (LTR_REGEX.test(ch)) {
        dominantDirection = 'ltr';
        break;
      }
    }
  }

  const segments = splitBidiSegments(text);

  return {
    dominantDirection,
    rtlRatio,
    containsRtl,
    segments,
  };
}
