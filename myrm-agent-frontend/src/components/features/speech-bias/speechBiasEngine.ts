import { CorrectionRecord, CorrectionResult, DevTermItem } from './speechBiasTypes';

export const DEFAULT_DEV_LEXICON: DevTermItem[] = [
  {
    id: 'term-grep',
    term: 'grep',
    category: 'cli_tool',
    aliases: ['grape', '格莱普', '割裂普', 'g rep'],
    weight: 10,
  },
  {
    id: 'term-pnpm',
    term: 'pnpm',
    category: 'cli_tool',
    aliases: ['pen pm', '屁恩屁恩', 'pn pm', 'p n p m'],
    weight: 10,
  },
  {
    id: 'term-k8s',
    term: 'Kubernetes',
    category: 'framework',
    aliases: ['库伯拉提斯', 'cooper net is', 'k8s', 'coopernetes'],
    weight: 9,
  },
  {
    id: 'term-docker',
    term: 'docker',
    category: 'cli_tool',
    aliases: ['doc er', '豆客', '道客'],
    weight: 9,
  },
  {
    id: 'term-tmux',
    term: 'tmux',
    category: 'cli_tool',
    aliases: ['t max', 'tea mugs', '梯马克斯', 't m u x'],
    weight: 9,
  },
  {
    id: 'term-vitest',
    term: 'vitest',
    category: 'framework',
    aliases: ['why test', 'v test', 'y test', '歪测试'],
    weight: 8,
  },
  {
    id: 'term-oxlint',
    term: 'oxlint',
    category: 'cli_tool',
    aliases: ['ox lint', '奥克斯林特', '公牛代码'],
    weight: 8,
  },
  {
    id: 'term-nextjs',
    term: 'Next.js',
    category: 'framework',
    aliases: ['next js', '耐克思特', 'nextjs'],
    weight: 8,
  },
  {
    id: 'term-tailwind',
    term: 'Tailwind CSS',
    category: 'framework',
    aliases: ['tailwind', '泰尔温德', 'tail wind'],
    weight: 7,
  },
  {
    id: 'term-typescript',
    term: 'TypeScript',
    category: 'framework',
    aliases: ['type script', '泰普脚本', 'ts'],
    weight: 9,
  },
];

export interface ContextExtractionInput {
  branch?: string;
  astSymbols?: string[];
  skills?: string[];
  packages?: string[];
}

export function extractContextTerms(input: ContextExtractionInput): DevTermItem[] {
  const dynamicTerms: DevTermItem[] = [];

  if (input.branch && input.branch.trim() !== '') {
    const branchName = input.branch.trim();
    dynamicTerms.push({
      id: `branch-${branchName}`,
      term: branchName,
      category: 'git_branch',
      aliases: [branchName.replace(/[-_/]/g, ' '), branchName.replace(/[-_/]/g, '')],
      weight: 8,
      source: 'Git Branch',
    });
  }

  if (input.astSymbols && input.astSymbols.length > 0) {
    for (const sym of input.astSymbols) {
      if (sym && sym.trim() !== '') {
        const trimmed = sym.trim();
        dynamicTerms.push({
          id: `ast-${trimmed}`,
          term: trimmed,
          category: 'ast_symbol',
          aliases: [trimmed.toLowerCase(), trimmed.replace(/([A-Z])/g, ' $1').trim().toLowerCase()],
          weight: 7,
          source: 'AST Symbol',
        });
      }
    }
  }

  if (input.skills && input.skills.length > 0) {
    for (const sk of input.skills) {
      if (sk && sk.trim() !== '') {
        const trimmed = sk.trim();
        dynamicTerms.push({
          id: `skill-${trimmed}`,
          term: trimmed,
          category: 'skill',
          aliases: [trimmed.replace(/[-_]/g, ' ')],
          weight: 8,
          source: 'Active Skill',
        });
      }
    }
  }

  if (input.packages && input.packages.length > 0) {
    for (const pkg of input.packages) {
      if (pkg && pkg.trim() !== '') {
        const trimmed = pkg.trim();
        dynamicTerms.push({
          id: `pkg-${trimmed}`,
          term: trimmed,
          category: 'package',
          aliases: [trimmed.replace(/[-_@/]/g, ' ')],
          weight: 7,
          source: 'Dependencies',
        });
      }
    }
  }

  return dynamicTerms;
}

function escapeRegExp(str: string): string {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

export function correctSpeechTranscript(rawText: string, lexicon: DevTermItem[]): CorrectionResult {
  if (!rawText || rawText.trim() === '') {
    return {
      originalText: rawText,
      correctedText: rawText,
      corrections: [],
      containsCodeBlocks: false,
    };
  }

  let text = rawText;
  const corrections: CorrectionRecord[] = [];
  let recordCounter = 0;

  // 按词条权重从高到低排序，优先纠偏高权重和长别名
  const sortedLexicon = [...lexicon].sort((a, b) => b.weight - a.weight);

  for (const item of sortedLexicon) {
    const aliasList = [item.term.toLowerCase(), ...item.aliases.map((a) => a.toLowerCase())];
    // 过滤重复别名
    const uniqueAliases = Array.from(new Set(aliasList));

    for (const alias of uniqueAliases) {
      if (alias === item.term.toLowerCase() && item.category !== 'ast_symbol') {
        // 如果别名就是自身小写，且原词含有大写，允许大小写归一
        if (item.term === alias) {
          continue;
        }
      }

      // 构建正则：支持中英文边界与非严格字符匹配
      const escaped = escapeRegExp(alias);
      const isEnglishOnly = /^[a-zA-Z0-9\s]+$/.test(alias);
      const pattern = isEnglishOnly
        ? new RegExp(`(?<=\\b|\\s|^)${escaped}(?=\\b|\\s|$)`, 'gi')
        : new RegExp(escaped, 'gi');

      let match: RegExpExecArray | null;
      // 使用带全局标志的正则匹配并收集替换位置
      while ((match = pattern.exec(text)) !== null) {
        const matchedStr = match[0];
        // 如果已经和目标术语完全一致（包括大小写），则跳过
        if (matchedStr === item.term) {
          continue;
        }

        const startIndex = match.index;
        const endIndex = startIndex + matchedStr.length;

        recordCounter += 1;
        corrections.push({
          id: `corr-${recordCounter}`,
          original: matchedStr,
          corrected: item.term,
          category: item.category,
          confidence: Math.min(0.95, 0.75 + item.weight * 0.02),
          startIndex,
          endIndex: startIndex + item.term.length,
        });

        // 替换文本并更新当前游标
        text = text.slice(0, startIndex) + item.term + text.slice(endIndex);
        pattern.lastIndex = startIndex + item.term.length;
      }
    }
  }

  // 格式化代码标识符（例如 CamelCase 或包含下划线的标识符）
  const formattedWithCode = detectAndFormatCodeSymbols(text);
  const containsCodeBlocks = formattedWithCode.includes('`');

  return {
    originalText: rawText,
    correctedText: formattedWithCode,
    corrections,
    containsCodeBlocks,
  };
}

export function detectAndFormatCodeSymbols(text: string): string {
  if (!text) {
    return '';
  }

  // 识别被两个非字母包围的 CamelCase 变量或以下划线连接的函数调用 (至少 6 个字符)，但排除普通全大写缩写
  const camelCasePattern = /(?<=\s|^)([a-z]+[A-Z][a-zA-Z0-9]+|[a-zA-Z0-9]+_[a-zA-Z0-9_]+)(?=\s|[.,!?，。！？]|$)/g;

  return text.replace(camelCasePattern, (match) => {
    // 若已包裹在反引号中则保留
    if (match.startsWith('`') && match.endsWith('`')) {
      return match;
    }
    return `\`${match}\``;
  });
}
