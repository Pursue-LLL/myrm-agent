import {
  RichSpan,
  TypedStreamBlock,
  StreamBlockType,
  StreamPerformanceMetrics,
} from './streamProtocolTypes';

const ANSI_COLOR_MAP: Record<string, string> = {
  '31': 'text-red-400',
  '32': 'text-emerald-400',
  '33': 'text-amber-400',
  '34': 'text-sky-400',
  '35': 'text-purple-400',
  '36': 'text-cyan-400',
  '90': 'text-slate-500',
};

export function parseSinglePassRichSpans(rawText: string): RichSpan[] {
  const spans: RichSpan[] = [];
  const len = rawText.length;
  let idx = 0;
  let currentPlainText = '';

  const flushPlain = () => {
    if (currentPlainText.length > 0) {
      spans.push({ text: currentPlainText, type: 'plain' });
      currentPlainText = '';
    }
  };

  while (idx < len) {
    // 1. ANSI 颜色转义序列检测: \x1b[32m 或 \u001b[32m
    if (
      rawText.charCodeAt(idx) === 27 &&
      idx + 1 < len &&
      rawText[idx + 1] === '['
    ) {
      flushPlain();
      let mIdx = idx + 2;
      while (mIdx < len && rawText[mIdx] !== 'm') {
        mIdx++;
      }
      if (mIdx < len && rawText[mIdx] === 'm') {
        const ansiCode = rawText.substring(idx + 2, mIdx);
        const colorClass = ANSI_COLOR_MAP[ansiCode] || 'text-slate-300';
        idx = mIdx + 1;

        // 收集该 ANSI 范围内的字符直至下一个 ANSI 重置或结尾
        let endIdx = idx;
        while (endIdx < len && rawText.charCodeAt(endIdx) !== 27) {
          endIdx++;
        }
        const coloredText = rawText.substring(idx, endIdx);
        if (coloredText.length > 0) {
          spans.push({ text: coloredText, type: 'ansi_color', colorClass });
        }
        idx = endIdx;
        continue;
      }
    }

    // 2. 行内代码: `code`
    if (rawText[idx] === '`') {
      flushPlain();
      const nextTick = rawText.indexOf('`', idx + 1);
      if (nextTick !== -1) {
        const codeContent = rawText.substring(idx + 1, nextTick);
        spans.push({ text: codeContent, type: 'inline_code' });
        idx = nextTick + 1;
        continue;
      }
    }

    // 3. 粗体: **bold**
    if (rawText[idx] === '*' && idx + 1 < len && rawText[idx + 1] === '*') {
      flushPlain();
      const nextStar = rawText.indexOf('**', idx + 2);
      if (nextStar !== -1) {
        const boldContent = rawText.substring(idx + 2, nextStar);
        spans.push({ text: boldContent, type: 'bold' });
        idx = nextStar + 2;
        continue;
      }
    }

    // 4. 普通字符累加
    currentPlainText += rawText[idx];
    idx++;
  }

  flushPlain();
  return spans.length > 0 ? spans : [{ text: '', type: 'plain' }];
}

export function parseStreamToTypedBlocks(content: string): TypedStreamBlock[] {
  const blocks: TypedStreamBlock[] = [];
  const lines = content.split('\n');
  let currentBlockType: StreamBlockType = 'paragraph';
  let currentLines: string[] = [];
  let blockLanguage: string | undefined;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // 代码块边界 ```lang
    if (line.startsWith('```')) {
      if (currentBlockType === 'code_block') {
        // 关闭当前代码块
        const codeText = currentLines.join('\n');
        blocks.push({
          id: `block_code_${blocks.length}`,
          type: 'code_block',
          language: blockLanguage || 'plaintext',
          spans: [{ text: codeText, type: 'inline_code' }],
          isFinalized: true,
        });
        currentLines = [];
        currentBlockType = 'paragraph';
        blockLanguage = undefined;
      } else {
        // 开启新代码块，先提交之前的段落
        if (currentLines.length > 0) {
          const pText = currentLines.join('\n');
          blocks.push({
            id: `block_p_${blocks.length}`,
            type: 'paragraph',
            spans: parseSinglePassRichSpans(pText),
            isFinalized: true,
          });
          currentLines = [];
        }
        currentBlockType = 'code_block';
        blockLanguage = line.slice(3).trim() || 'plaintext';
      }
      continue;
    }

    currentLines.push(line);
  }

  // 结算剩余行
  if (currentLines.length > 0) {
    const remainingText = currentLines.join('\n');
    if (currentBlockType === 'code_block') {
      blocks.push({
        id: `block_code_${blocks.length}`,
        type: 'code_block',
        language: blockLanguage || 'plaintext',
        spans: [{ text: remainingText, type: 'inline_code' }],
        isFinalized: false,
      });
    } else {
      blocks.push({
        id: `block_p_${blocks.length}`,
        type: 'paragraph',
        spans: parseSinglePassRichSpans(remainingText),
        isFinalized: false,
      });
    }
  }

  return blocks;
}

export function benchmarkSinglePassParser(text: string): StreamPerformanceMetrics {
  const start = performance.now();
  const blocks = parseStreamToTypedBlocks(text);
  const duration = Math.max(0.01, performance.now() - start);

  const tokenCount = Math.round(text.length / 3.5);
  const throughputTokensPerSec = Math.round((tokenCount / duration) * 1000);

  return {
    parseDurationMs: Number(duration.toFixed(2)),
    tokenCount,
    throughputTokensPerSec,
    estimatedCpuUsagePct: Math.min(15, Number((duration * 0.8).toFixed(1))),
    memoryAllocatedBytes: blocks.length * 128 + text.length * 2,
  };
}
