/**
 * [INPUT] Raw assistant suggestion text (containing pleasantries, meta-commentary)
 * [OUTPUT] CleanedActionItem with stripped fluff, actionable title, category and bullets
 * [POS] task-action-preview/smartFluffStripper.ts
 */

import type { ActionCategory, ActionUrgency, CleanedActionItem } from './taskActionPreviewTypes';

const LEADING_FLUFF_PATTERNS: RegExp[] = [
  /^(?:好的|收到|明白|没问题|当然可以|没关系)[，,。!！\s]*/i,
  /^(?:根据您(?:的要求|的反馈|的指令)|结合当前上下文|经过(?:深度)?分析)[，,。!！\s]*/i,
  /^(?:(?:我)?(?:建议|认为|这边推荐|可以为您)|建议您|接下来我们(?:可以|应该|需要))[，,。!！\s]*/i,
  /^(?:以下是(?:我的建议|下一步计划|具体的执行方案))[：:\s]*/i,
  /^(?:sure|certainly|great|alright|absolutely|of course)[,!.\s]*/i,
  /^(?:based on (?:your requirement|the discussion|the analysis)|after reviewing)[,!.\s]*/i,
  /^(?:i (?:recommend|suggest|propose) (?:that we|to)|here (?:is|are) (?:the next steps|my recommendation))[：:!.\s]*/i,
];

const TRAILING_FLUFF_PATTERNS: RegExp[] = [
  /(?:您看(?:这样)?(?:合适|可以|行)吗[？?]?|如有任何问题请随时告诉我[。！!]?|期待您的(?:反馈|确认)[。！!]?)$/i,
  /(?:请问是否需要继续推进[？?]?|是否需要为您执行该方案[？?]?)$/i,
  /(?:do you (?:think this works|agree|have any questions)[?]?|let me know what you think[.! ]?)$/i,
  /(?:feel free to let me know if you need any adjustments[.! ]?)$/i,
];

const META_EXPLANATION_PATTERNS: RegExp[] = [
  /^(?:作为一个(?:专业)?AI(?:助手)?|作为全栈工程师|在本次分析中)[，,。!！\s]*/i,
  /^(?:as an ai assistant|in my role as an architect)[,!.\s]*/i,
];

function stripLineFluff(line: string): string {
  let cleaned = line.trim();
  if (!cleaned) {
    return '';
  }

  let modified = true;
  while (modified) {
    modified = false;
    for (const pattern of LEADING_FLUFF_PATTERNS) {
      if (pattern.test(cleaned)) {
        cleaned = cleaned.replace(pattern, '').trim();
        modified = true;
      }
    }
    for (const pattern of META_EXPLANATION_PATTERNS) {
      if (pattern.test(cleaned)) {
        cleaned = cleaned.replace(pattern, '').trim();
        modified = true;
      }
    }
    for (const pattern of TRAILING_FLUFF_PATTERNS) {
      if (pattern.test(cleaned)) {
        cleaned = cleaned.replace(pattern, '').trim();
        modified = true;
      }
    }
    // Clean lingering leading or trailing punctuation
    const beforePunct = cleaned;
    cleaned = cleaned.replace(/^[，,。!！；;：:?\s]+/, '').replace(/[，,。!！；;？?\s]+$/, '').trim();
    if (beforePunct !== cleaned) {
      modified = true;
    }
  }

  return cleaned;
}

function inferCategory(text: string): ActionCategory {
  const lower = text.toLowerCase();
  if (/修复|bug|fix|panic|crash|error|异常|崩溃/i.test(lower)) {
    return 'fix';
  }
  if (/重构|refactor|解耦|拆分|优化结构|clean up|提取/i.test(lower)) {
    return 'refactor';
  }
  if (/验证|verify|测试|test|spec|assert|单测|门禁/i.test(lower)) {
    return 'verify';
  }
  if (/排查|调查|定位|investigate|audit|排错|分析根因/i.test(lower)) {
    return 'investigate';
  }
  return 'task';
}

function inferUrgency(text: string): ActionUrgency {
  const lower = text.toLowerCase();
  if (/紧急|立刻|高危|严重|critical|urgent|asap|致命/i.test(lower)) {
    return 'high';
  }
  if (/优先|尽快|important|p0|高优先级/i.test(lower)) {
    return 'medium';
  }
  return 'low';
}

function extractBullets(rawText: string): string[] {
  const lines = rawText.split('\n');
  const bullets: string[] = [];
  const bulletRegex = /^(?:[-*•]|\d+[.)])\s+(.*)$/;

  for (const rawLine of lines) {
    const trimmed = rawLine.trim();
    if (!trimmed) {
      continue;
    }
    const match = bulletRegex.exec(trimmed);
    if (match && match[1]) {
      const cleaned = stripLineFluff(match[1]);
      if (cleaned.length > 0) {
        bullets.push(cleaned);
      }
    }
  }

  return bullets;
}

export function extractCleanedActionItem(rawText: string): CleanedActionItem {
  if (!rawText || !rawText.trim()) {
    return {
      rawText: '',
      actionableTitle: '',
      suggestedDescription: '',
      category: 'task',
      urgency: 'low',
      extractedBulletPoints: [],
    };
  }

  const bullets = extractBullets(rawText);
  const rawLines = rawText.split('\n');
  const cleanedLines: string[] = [];

  for (const line of rawLines) {
    const cleaned = stripLineFluff(line);
    if (cleaned.length > 0) {
      cleanedLines.push(cleaned);
    }
  }

  // Determine the primary actionable title
  let actionableTitle = '';
  if (bullets.length > 0 && bullets[0]) {
    actionableTitle = bullets[0];
  } else if (cleanedLines.length > 0 && cleanedLines[0]) {
    actionableTitle = cleanedLines[0];
  } else {
    actionableTitle = stripLineFluff(rawText);
  }

  // Truncate title if overly long
  if (actionableTitle.length > 80) {
    actionableTitle = actionableTitle.slice(0, 76).trim() + '...';
  }

  const combinedBody = cleanedLines.join('\n');
  const category = inferCategory(rawText);
  const urgency = inferUrgency(rawText);

  return {
    rawText,
    actionableTitle,
    suggestedDescription: combinedBody,
    category,
    urgency,
    extractedBulletPoints: bullets,
  };
}
