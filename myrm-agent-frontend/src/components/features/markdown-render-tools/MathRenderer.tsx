/**
 * [INPUT] remark-math, rehype-katex (POS: Markdown AST 数学节点解析与渲染)
 * [OUTPUT] preprocessContentMath: 全局数学预处理管线; MathRenderer: 独立数学公式渲染组件; katexConfig: KaTeX 配置
 * [POS] 数学公式渲染与 LaTeX 预处理。将 LLM 输出的各种 LaTeX 格式统一为 remark-math 可识别的 $/$$ 格式，并提供流式保护。
 */
import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkMath, { Options } from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';

const remarkMathOptions: Options = {
  singleDollarTextMath: true,
};

/** 处理数学公式内部特殊字符：% 转义、中文 \text → \mathrm */
export const preprocessMathContent = (content: string): string => {
  if (!content) return content;

  let processed = content;

  processed = processed.replace(/(?<!\\)%/g, '\\%');

  processed = processed.replace(/\\text\{([^}]*)\}/g, (match, textContent) => {
    if (/[\u4e00-\u9fff]/.test(textContent)) {
      return `\\mathrm{${textContent}}`;
    }
    return match;
  });

  const openBraces = (processed.match(/\{/g) || []).length;
  const closeBraces = (processed.match(/\}/g) || []).length;

  if (openBraces !== closeBraces) {
    console.warn('Math content has unmatched braces:', content);
  }

  return processed;
};

interface CodeBlockPlaceholder {
  placeholder: string;
  original: string;
}

/**
 * 提取代码块（``` 和 ``）为占位符，防止其内容被 LaTeX 转换误处理。
 * 返回处理后的文本和还原函数。
 */
function protectCodeBlocks(text: string): { processed: string; restore: (s: string) => string } {
  const placeholders: CodeBlockPlaceholder[] = [];
  let idx = 0;

  const fenceRe = /```[\s\S]*?(?:```|$)/g;
  let processed = text.replace(fenceRe, (match) => {
    const ph = `\x00CODEBLOCK${idx++}\x00`;
    placeholders.push({ placeholder: ph, original: match });
    return ph;
  });

  const inlineRe = /`[^`\n]+`/g;
  processed = processed.replace(inlineRe, (match) => {
    const ph = `\x00CODEBLOCK${idx++}\x00`;
    placeholders.push({ placeholder: ph, original: match });
    return ph;
  });

  const restore = (s: string): string => {
    let result = s;
    for (const { placeholder, original } of placeholders) {
      result = result.replace(placeholder, original);
    }
    return result;
  };

  return { processed, restore };
}

/**
 * 将 LaTeX 分隔符 \[...\] 转换为 $$...$$，\(...\) 转换为 $...$。
 * 大多数现代 LLM（GPT-4o, Claude, Gemini）使用这些格式输出数学公式。
 */
function convertLatexDelimiters(text: string): string {
  let result = text.replace(/\\\[([\s\S]*?)\\\]/g, (_match, inner: string) => {
    return `$$${inner}$$`;
  });

  result = result.replace(/\\\((.+?)\\\)/g, (_match, inner: string) => {
    return `$${inner}$`;
  });

  return result;
}

/**
 * 流式渲染时，转义未配对的 $$ 防止 KaTeX 解析报错产生红色错误闪烁。
 * 仅在 isStreaming=true 时调用。
 */
export function escapeIncompleteBlockMath(text: string): string {
  const parts = text.split('$$');
  if (parts.length % 2 === 0) {
    const lastIdx = text.lastIndexOf('$$');
    return text.slice(0, lastIdx) + '\\$\\$' + text.slice(lastIdx + 2);
  }
  return text;
}

/**
 * 预处理整个内容中的数学公式。
 * 处理链：代码块保护 → LaTeX delimiter 转换 → 流式不完整保护 → 代码块还原 → 内容预处理
 */
export const preprocessContentMath = (content: string, isStreaming = false): string => {
  if (!content) return content;

  const { processed: withoutCode, restore } = protectCodeBlocks(content);

  let processed = convertLatexDelimiters(withoutCode);

  if (isStreaming) {
    processed = escapeIncompleteBlockMath(processed);
  }

  processed = restore(processed);

  processed = processed.replace(/\$\$([\s\S]+?)\$\$/g, (_match, mathContent: string) => {
    return `$$${preprocessMathContent(mathContent)}$$`;
  });

  processed = processed.replace(/\$([^$]+)\$/g, (_match, mathContent: string) => {
    return `$${preprocessMathContent(mathContent)}$`;
  });

  return processed;
};

export const katexConfig = {
  strict: false,
  output: 'html',
  trust: true,
  throwOnError: false,
  errorColor: '#cc0000',
  macros: {
    '\\text': '\\mathrm',
  },
  global: {
    unicodeTextInMathMode: true,
  },
};

interface MathRendererProps {
  content: string;
  isBlock?: boolean;
  className?: string;
}

const MathRenderer: React.FC<MathRendererProps> = ({ content, isBlock = true, className = '' }) => {
  const processedContent = preprocessMathContent(content);
  const mathContent = isBlock ? `$$${processedContent}$$` : `$${processedContent}$`;

  return (
    <div className={`math-renderer ${isBlock ? 'math-block my-4' : 'math-inline'} ${className}`}>
      <ReactMarkdown remarkPlugins={[[remarkMath, remarkMathOptions]]} rehypePlugins={[[rehypeKatex, katexConfig]]}>
        {mathContent}
      </ReactMarkdown>
    </div>
  );
};

MathRenderer.displayName = 'MathRenderer';

export default MathRenderer;
