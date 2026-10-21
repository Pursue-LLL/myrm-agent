/**
 * incrementalStreamParser - 基于块级状态机的高性能增量流式 Markdown 解析引擎
 *
 * [INPUT]
 * - fullText: string 当前累计接收到的完整 Markdown 文本
 * - isStreaming: boolean 是否正处于流式生成状态
 *
 * [OUTPUT]
 * - parseIncrementalStream: (fullText: string, isStreaming: boolean) => IncrementalParsedStream
 *
 * [POS]
 * 增量流式渲染核心算法层。借鉴 pi-tui 增量渲染思想，将全量 AST 重复构建转化为
 * 冻结快照块（Frozen Blocks）与末尾活跃块（Active Tail Block）的精准双分流，
 * 消除主线程对超长文档反复全量重绘导致的掉帧。
 */

import type {
  IncrementalParsedStream,
  MarkdownBlock,
  MarkdownBlockType,
} from './streamingMarkdownTypes';

/**
 * 提取围栏代码块中的语言标识符
 */
function extractCodeLanguage(firstLine: string): string | undefined {
  const match = firstLine.match(/^```([a-zA-Z0-9_-]+)?/);
  if (match && match[1]) {
    return match[1].trim();
  }
  return undefined;
}

/**
 * 探测块的 Markdown 语义类型
 */
function detectBlockType(rawText: string): MarkdownBlockType {
  const trimmed = rawText.trim();
  if (trimmed.startsWith('```')) {
    return 'code';
  }
  if (/^#{1,6}\s+/.test(trimmed)) {
    return 'heading';
  }
  if (trimmed.startsWith('>')) {
    return 'blockquote';
  }
  if (/^[-*+]\s+/.test(trimmed) || /^\d+\.\s+/.test(trimmed)) {
    return 'list';
  }
  if (trimmed.includes('|') && trimmed.split('\n').length >= 2) {
    return 'table';
  }
  if (/^[-*_]{3,}$/.test(trimmed)) {
    return 'thematicBreak';
  }
  if (trimmed.length > 0) {
    return 'paragraph';
  }
  return 'unknown';
}

/**
 * 计算标题级别
 */
function extractHeadingLevel(rawText: string): number | undefined {
  const match = rawText.trim().match(/^(#{1,6})\s+/);
  if (match && match[1]) {
    return match[1].length;
  }
  return undefined;
}

/**
 * 将连续 Markdown 纯文本增量拆解为冻结块与末尾活跃块
 */
export function parseIncrementalStream(
  fullText: string,
  isStreaming: boolean,
): IncrementalParsedStream {
  if (!fullText) {
    return {
      frozenBlocks: [],
      activeTailBlock: null,
      totalBlocksCount: 0,
      fullContentLength: 0,
    };
  }

  const frozenBlocks: MarkdownBlock[] = [];
  let remainingText = fullText;
  let blockIndex = 0;

  while (remainingText.length > 0) {
    // 消耗前置的多余换行符与空白
    const leadingWhitespaceMatch = remainingText.match(/^[\r\n\s]+/);
    if (leadingWhitespaceMatch) {
      remainingText = remainingText.slice(leadingWhitespaceMatch[0].length);
      if (remainingText.length === 0) {
        break;
      }
    }

    // 1. 处理围栏代码块 (```)
    if (remainingText.startsWith('```')) {
      const codeStartIdx = remainingText.indexOf('```');
      const afterFence = remainingText.slice(codeStartIdx + 3);
      const closeFenceIdx = afterFence.indexOf('\n```');

      if (closeFenceIdx !== -1) {
        // 发现已闭合的代码块
        const fullCodeBlockLen = codeStartIdx + 3 + closeFenceIdx + 4; // 包含 \n```
        const rawContent = remainingText.slice(0, fullCodeBlockLen).trim();
        const firstLine = rawContent.split('\n')[0] ?? '';
        const language = extractCodeLanguage(firstLine);

        frozenBlocks.push({
          id: `block-${blockIndex++}`,
          type: 'code',
          rawContent,
          isFrozen: true,
          language,
        });

        remainingText = remainingText.slice(fullCodeBlockLen);
        continue;
      } else {
        // 未闭合的代码块：作为尾部活动块或最终块
        const firstLine = remainingText.split('\n')[0] ?? '';
        const language = extractCodeLanguage(firstLine);
        const tailBlock: MarkdownBlock = {
          id: `block-${blockIndex++}`,
          type: 'code',
          rawContent: remainingText,
          isFrozen: !isStreaming,
          language,
        };

        if (isStreaming) {
          return {
            frozenBlocks,
            activeTailBlock: tailBlock,
            totalBlocksCount: frozenBlocks.length + 1,
            fullContentLength: fullText.length,
          };
        } else {
          frozenBlocks.push(tailBlock);
          remainingText = '';
          break;
        }
      }
    }

    // 2. 处理普通段落/标题/引用/表格：寻找段落分隔符 "\n\n"
    const nextParagraphBreakIdx = remainingText.indexOf('\n\n');

    if (nextParagraphBreakIdx !== -1) {
      // 找到了明确的双换行闭合点
      const blockRaw = remainingText.slice(0, nextParagraphBreakIdx).trim();
      if (blockRaw.length > 0) {
        const type = detectBlockType(blockRaw);
        const level = type === 'heading' ? extractHeadingLevel(blockRaw) : undefined;

        frozenBlocks.push({
          id: `block-${blockIndex++}`,
          type,
          rawContent: blockRaw,
          isFrozen: true,
          level,
        });
      }

      // 跨过 \n\n
      remainingText = remainingText.slice(nextParagraphBreakIdx + 2);
    } else {
      // 未遇到双换行：如果正在流式输出，视为活跃尾部块
      const trimmedRemaining = remainingText.trim();
      if (trimmedRemaining.length === 0) {
        break;
      }
      const type = detectBlockType(trimmedRemaining);
      const level = type === 'heading' ? extractHeadingLevel(trimmedRemaining) : undefined;
      const tailBlock: MarkdownBlock = {
        id: `block-${blockIndex++}`,
        type,
        rawContent: trimmedRemaining,
        isFrozen: !isStreaming,
        level,
      };

      if (isStreaming) {
        return {
          frozenBlocks,
          activeTailBlock: tailBlock,
          totalBlocksCount: frozenBlocks.length + 1,
          fullContentLength: fullText.length,
        };
      } else {
        frozenBlocks.push(tailBlock);
        remainingText = '';
        break;
      }
    }
  }

  return {
    frozenBlocks,
    activeTailBlock: null,
    totalBlocksCount: frozenBlocks.length,
    fullContentLength: fullText.length,
  };
}
