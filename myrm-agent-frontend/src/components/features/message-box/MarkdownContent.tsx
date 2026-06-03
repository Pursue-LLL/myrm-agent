/**
 * MarkdownContent - Markdown 渲染组件
 *
 * [POS]
 * 负责将 Markdown 文本渲染为富文本，支持数学公式、代码块、图表、链接等。
 *
 * [关键职责]
 * - 使用 ReactMarkdown + remark/rehype 插件解析和渲染 Markdown
 * - 将 isStreaming 状态传递给 CodeBlock 组件以启用流式优化
 * - 处理自定义标签 (vault://, think/thinking/thought/antthinking/reasoning, mermaid, diff 等)
 * - 平滑流式渲染：通过 useSmoothStream 实现逐字符打字机效果
 *
 * [优化] (2026-05-06)
 * 传递 isStreaming prop 给 CodeBlock，支持流式输出时的 debounce 优化。
 *
 * [优化] (2026-05-18)
 * 集成 useSmoothStream Hook，实现平滑流式渲染。当 smoothStreamEnabled=true 且 isStreaming=true 时，
 * 内容通过 Intl.Segmenter 分割为 grapheme cluster 队列，requestAnimationFrame 渲染循环逐字显示。
 */
import React, { useEffect, useMemo } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { useSmoothStream } from '@/hooks/useSmoothStream';
import useConfigStore from '@/store/useConfigStore';
import ReactMarkdown from 'react-markdown';
import remarkMath, { Options } from 'remark-math';
import rehypeKatex from 'rehype-katex';
import rehypeRaw from 'rehype-raw';
import rehypeHeadingIds from '../markdown-render-tools/rehypeHeadingIds';
import 'katex/dist/katex.min.css';
import remarkGfm from 'remark-gfm';
import LinkPopover from '@/components/features/markdown-render-tools/LinkPopover';
import CodeBlock from '@/components/features/markdown-render-tools/CodeBlock';
import InlineHtmlWidget from '@/components/features/markdown-render-tools/InlineHtmlWidget';
import MermaidChart from '@/components/features/markdown-render-tools/MermaidChart';
import { preprocessContentMath, katexConfig } from '@/components/features/markdown-render-tools/MathRenderer';
import ThinkTagProcessor from '../markdown-render-tools/ThinkTagProcessor';
import MarkdownImage from '../markdown-render-tools/MarkdownImage';
import { getChildrenAsText } from '@/lib/utils/reactUtils';
import VaultArtifactCard from '../artifacts/VaultArtifactCard';
import InlineDiffViewer from '../markdown-render-tools/InlineDiffViewer';
import TimeSlotPicker from './TimeSlotPicker';

const INLINE_RENDER_LANGUAGES = new Set(['html', 'svg']);

const remarkMathOptions: Options = {
  singleDollarTextMath: true,
};

const preprocessVaultLinks = (text: string) => {
  // Convert plain text vault://<uuid> to <vault id="<uuid>"></vault>
  // We use a regex that matches UUIDs (with hyphens) after vault://
  return text.replace(/vault:\/\/([a-f0-9A-F-]+)/gi, '<vault id="$1"></vault>');
};

const MarkdownContent = React.memo(
  ({
    content,
    sources,
    messageId: _messageId,
    isStreaming = false,
  }: {
    content: string;
    sources: any;
    messageId: string;
    isStreaming?: boolean;
  }) => {
    const smoothStreamEnabled = useConfigStore((state) => state.smoothStreamEnabled);
    const { addChunk, displayedContent, flush, reset } = useSmoothStream();
    const prevContentRef = React.useRef('');

    // Strip citations so they don't render during streaming or static view
    const sanitizedContent = useMemo(() => content.replace(/<cite:[^>]+>/gi, ''), [content]);

    // 平滑流式渲染逻辑
    const shouldUseSmoothStream = smoothStreamEnabled && isStreaming;
    const displayContent = shouldUseSmoothStream ? displayedContent : sanitizedContent;

    // 当 content 变化时，将新增内容加入平滑流队列
    useEffect(() => {
      if (!shouldUseSmoothStream) {
        prevContentRef.current = sanitizedContent;
        return;
      }

      // 计算新增内容
      if (sanitizedContent.length > prevContentRef.current.length && sanitizedContent.startsWith(prevContentRef.current)) {
        const newChunk = sanitizedContent.slice(prevContentRef.current.length);
        addChunk(newChunk);
      } else if (sanitizedContent !== prevContentRef.current) {
        // 内容不连续（如消息切换），重置
        reset();
        addChunk(sanitizedContent);
      }
      prevContentRef.current = sanitizedContent;
    }, [sanitizedContent, shouldUseSmoothStream, addChunk, reset]);

    // 流结束时 flush 剩余内容
    useEffect(() => {
      if (!isStreaming && shouldUseSmoothStream) {
        flush();
      }
    }, [isStreaming, shouldUseSmoothStream, flush]);

    // 内容变化时重置（如切换消息）
    useEffect(() => {
      if (!isStreaming) {
        reset();
        prevContentRef.current = '';
      }
    }, [_messageId, isStreaming, reset]);

    const processedContent = useMemo(
      () => preprocessVaultLinks(preprocessContentMath(displayContent, isStreaming)),
      [displayContent, isStreaming],
    );
    const components = useMemo(
      () => ({
        vault: ({ id }: { id?: string }) => {
          if (!id) return null;
          return <VaultArtifactCard id={id} />;
        },
        timeslotpicker: ({ data }: { data?: string }) => {
          if (!data) return null;
          return <TimeSlotPicker data={data} />;
        },
        think: ThinkTagProcessor,
        thinking: ThinkTagProcessor,
        thought: ThinkTagProcessor,
        antthinking: ThinkTagProcessor,
        reasoning: ThinkTagProcessor,
        code: ({ node, className, children, ...props }: any) => {
          const match = /language-(\w+)/.exec(className || '');
          const language = match && match[1] ? match[1] : '';
          const value = getChildrenAsText(children);

          if (language === 'mermaid' && value.trim()) {
            return <MermaidChart chart={value} />;
          }

          if (language === 'diff' && value.trim()) {
            return <InlineDiffViewer diff={value} />;
          }

          if (!isStreaming && INLINE_RENDER_LANGUAGES.has(language.toLowerCase()) && value.trim()) {
            return <InlineHtmlWidget language={language} value={value} />;
          }

          if (language) {
            return <CodeBlock language={language} value={value} isStreaming={isStreaming} />;
          }

          // 内联代码块
          const isInlineCode = node.position.start.line === node.position.end.line;
          if (isInlineCode) {
            return (
              <code
                className="bg-[#f6f6f1] font-normal text-[#ED6037] dark:bg-gray-800 px-1 py-0.5 rounded text-sm"
                {...props}
              >
                {value}
              </code>
            );
          }

          // 普通文本
          return <span>{value}</span>;
        },
        a: ({ href, children }: { href?: string; children?: React.ReactNode }) => {
          const isExternal = href && /^https?:\/\//.test(href);
          if (isExternal) {
            return (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary underline decoration-primary/30 hover:decoration-primary transition-colors"
              >
                {children}
              </a>
            );
          }
          return <a href={href}>{children}</a>;
        },
        img: ({ src, alt }: { src?: string; alt?: string }) => <MarkdownImage src={src} alt={alt} />,
        citation: (props: any) => {
          const url = props['data-url'];
          const num = props['data-num'];
          const sourceIndex = parseInt(props['data-source-index']);

          if (isNaN(sourceIndex) || !sources || sourceIndex >= sources.length) {
            return <>[{num}]</>;
          }

          const source = sources[sourceIndex];

          // MCP 类型来源 - 使用技能名作为 title，调用信息作为 description
          if (source?.type === 'mcp') {
            const mcpTitle = source.skill_name || 'MCP Skill';
            // 构建调用信息摘要
            let mcpDescription = 'MCP 技能调用';
            if (source.calls && source.calls.length > 0) {
              mcpDescription = source.calls
                .map((call: { tool_name: string; result_preview?: string }) => {
                  const preview = call.result_preview || '';
                  return `${call.tool_name}: ${preview}`;
                })
                .join('\n\n');
            }

            return <LinkPopover url="#" title={mcpTitle} description={mcpDescription} label={num} />;
          }

          // 默认渲染网页引用 (web_search, web_fetch)
          const title = source?.title;
          const description = source?.snippet;

          // 如果没有URL或URL为空，仍然使用LinkPopover但传入#作为占位符
          const linkUrl = url && url !== '' ? url : '#';

          return <LinkPopover url={linkUrl} title={title} description={description} label={num} />;
        },
      }),
      [sources, isStreaming],
    );

    return (
      <div
        className={cn(
          'prose prose-h1:mb-3 prose-h2:mb-2 prose-h2:mt-6 prose-h2:font-[800] prose-h3:mt-4 prose-h3:mb-1.5 prose-h3:font-[600] dark:prose-invert prose-p:leading-relaxed prose-pre:p-0 font-[400]',
          'prose-table:table-auto prose-table:border-collapse prose-th:border prose-th:border-gray-300 prose-th:px-6 prose-th:py-3 prose-th:bg-[#f3f3ee] prose-th:font-semibold prose-th:text-center prose-th:align-middle prose-td:border prose-td:border-gray-300 prose-td:px-6 prose-td:py-3 prose-td:text-center prose-td:align-middle',
          'dark:prose-th:border-gray-600 dark:prose-th:bg-gray-800 dark:prose-td:border-gray-600 prose-table:overflow-hidden',
          'max-w-none break-words text-black dark:text-white',
          'prose-math:text-inherit',
          'prose-pre:rounded-md prose-pre:bg-transparent prose-pre:p-0 prose-pre:text-gray-500 dark:prose-pre:text-gray-100',
        )}
      >
        <ReactMarkdown
          remarkPlugins={[[remarkMath, remarkMathOptions], remarkGfm]} // 用于 渲染 解析后的 AST 内容
          rehypePlugins={[[rehypeKatex, katexConfig], rehypeRaw, [rehypeHeadingIds, { prefix: `toc-${_messageId}` }]]} // 将 AST 转换为最终的 HTML 结构
          components={components}
          allowedElements={[
            // 允许渲染的元素
            // 基本文本和标题
            'p',
            'h1',
            'h2',
            'h3',
            'h4',
            'h5',
            'h6',
            'br',
            // 文本格式化
            'strong',
            'em',
            'code',
            'del',
            // 列表
            'ul',
            'ol',
            'li',
            // 引用和分隔
            'blockquote',
            'hr',
            // 表格
            'table',
            'thead',
            'tbody',
            'tr',
            'th',
            'td',
            // 代码块
            'pre',
            // 链接和图片
            'a',
            'img',
            // 容器
            'div',
            'span',
            // 自定义标签
            'think',
            'thinking',
            'thought',
            'antthinking',
            'reasoning',
            'citation',
            'vault',
            'timeslotpicker',
          ]}
          unwrapDisallowed={true} // 如果某个元素被禁止，该元素本身会被移除，但它的 子内容会被保留并提升到父级
        >
          {processedContent}
        </ReactMarkdown>
      </div>
    );
  },
);

MarkdownContent.displayName = 'MarkdownContent';

export default MarkdownContent;
