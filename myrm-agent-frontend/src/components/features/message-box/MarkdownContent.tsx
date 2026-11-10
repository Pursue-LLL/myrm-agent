/**
 * MarkdownContent - Markdown 渲染组件
 *
 * [POS]
 * 负责将 Markdown 文本渲染为富文本，支持数学公式、代码块、图表、链接、GFM Alerts、脚注等。
 *
 * [关键职责]
 * - 使用 ReactMarkdown + remark/rehype 插件解析和渲染 Markdown
 * - 将 isStreaming 状态传递给 CodeBlock 组件以启用流式优化
 * - 处理自定义标签 (vault://, think/thinking/thought/antthinking/reasoning, mermaid, diff 等)
 * - 平滑流式渲染：通过 useSmoothStream + Intl.Segmenter 实现逐字符打字机效果
 * - 元素映射（code / a / img / table / citation / vault / think）见 ./markdownComponents；
 *   citation 解析逻辑见 @/lib/citations/preprocessCitationMarkers
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { useSmoothStream } from '@/hooks/message-input/useSmoothStream';
import useConfigStore from '@/store/useConfigStore';
import ReactMarkdown from 'react-markdown';
import rehypeRaw from 'rehype-raw';
import rehypeHeadingIds from '../markdown-render-tools/rehypeHeadingIds';
import 'katex/dist/katex.min.css';
import remarkGfm from 'remark-gfm';
import remarkGitHubAlerts from 'remark-github-markdown-alerts';
import SourceChunkDrawer from './SourceChunkDrawer';
import type { Artifact, Source, WikiSourceLevel } from '@/store/chat/types';
import { recordEvidenceSurface } from '@/services/wiki/evidenceMetrics';
import { useTranslations } from 'next-intl';
import { IncrementalStreamingMarkdownRenderer } from '@/components/features/chat-window/streaming-markdown';
import { preprocessCitationMarkers } from '@/lib/citations/preprocessCitationMarkers';
import { chatMathPlugins, normalizeMathDelimiters } from '@/lib/utils/markdownMath';
import { createMarkdownComponents, type OpenKbDrawer } from './markdownComponents';

const preprocessVaultLinks = (text: string) => {
  return text.replace(/vault:\/\/([a-f0-9A-F-]+)/gi, '<vault id="$1"></vault>');
};

const MarkdownContent = React.memo(
  ({
    content,
    sources,
    messageId: _messageId,
    isStreaming = false,
    enableIncrementalStreaming = false,
    chatId,
    messageArtifacts,
    workspaceDir,
  }: {
    content: string;
    sources: Source[];
    messageId: string;
    isStreaming?: boolean;
    enableIncrementalStreaming?: boolean;
    chatId?: string;
    messageArtifacts?: Artifact[];
    workspaceDir?: string;
  }) => {
    const smoothStreamEnabled = useConfigStore((state) => state.smoothStreamEnabled);
    const { addChunk, displayedContent, flush, reset } = useSmoothStream();
    const prevContentRef = React.useRef('');
    const tSources = useTranslations('MessageSources');

    const [drawerState, setDrawerState] = useState<{
      open: boolean;
      title: string;
      section?: string;
      snippet: string;
      level?: WikiSourceLevel;
      snapshotStatus?: Source['snapshot_status'];
      claimStatus?: Source['claim_status'];
      claimConfidence?: Source['claim_confidence'];
      claimText?: Source['claim_text'];
      resourceUri?: string;
      supersededFromUri?: string;
      thumbnailUrl?: string | null;
    }>({ open: false, title: '', snippet: '' });

    const openKbDrawer = useCallback<OpenKbDrawer>(
      (
        title,
        section,
        snippet,
        level,
        snapshotStatus,
        thumbnailUrl,
        resourceUri,
        supersededFromUri,
        claimStatus,
        claimConfidence,
        claimText,
      ) => {
        setDrawerState({
          open: true,
          title,
          section,
          snippet,
          level,
          snapshotStatus,
          thumbnailUrl,
          resourceUri,
          supersededFromUri,
          claimStatus,
          claimConfidence,
          claimText,
        });
      },
      [],
    );

    // Strip citations so they don't render during streaming or static view
    const sanitizedContent = useMemo(() => content.replace(/<cite:[^>]+>/gi, ''), [content]);
    const hasKbEvidence = useMemo(
      () => sources.some((source) => Boolean(source.kb_name) && Boolean(source.snippet || source.summary)),
      [sources],
    );

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
      if (
        sanitizedContent.length > prevContentRef.current.length &&
        sanitizedContent.startsWith(prevContentRef.current)
      ) {
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

    useEffect(() => {
      if (!hasKbEvidence) {
        return;
      }
      recordEvidenceSurface('chat', 1, `chat:${_messageId}`);
    }, [_messageId, hasKbEvidence]);

    const processedContent = useMemo(() => {
      let text = normalizeMathDelimiters(displayContent, isStreaming);
      if (sources.length > 0) {
        text = preprocessCitationMarkers(text, sources);
      }
      return preprocessVaultLinks(text);
    }, [displayContent, isStreaming, sources]);
    const components = useMemo(
      () =>
        createMarkdownComponents({
          sources,
          isStreaming,
          openKbDrawer,
          tSources,
          chatId,
          messageArtifacts,
          workspaceDir,
        }),
      [sources, isStreaming, openKbDrawer, tSources, chatId, messageArtifacts, workspaceDir],
    );

    if (enableIncrementalStreaming && isStreaming) {
      return (
        <div
          data-testid="incremental-streaming-content"
          className={cn(
            'prose prose-h1:mb-3 prose-h2:mb-2 prose-h2:mt-6 prose-h2:font-[800] prose-h3:mt-4 prose-h3:mb-1.5 prose-h3:font-[600] dark:prose-invert prose-p:leading-relaxed prose-pre:p-0 font-[400]',
            'max-w-none break-words text-black dark:text-white',
          )}
        >
          <IncrementalStreamingMarkdownRenderer content={displayContent} isStreaming={true} />
        </div>
      );
    }

    return (
      <div
        className={cn(
          'prose prose-h1:mb-3 prose-h2:mb-2 prose-h2:mt-6 prose-h2:font-[800] prose-h3:mt-4 prose-h3:mb-1.5 prose-h3:font-[600] dark:prose-invert prose-p:leading-relaxed prose-pre:p-0 font-[400]',
          'max-w-none break-words text-black dark:text-white',
          'prose-math:text-inherit',
          'prose-pre:rounded-md prose-pre:bg-transparent prose-pre:p-0 prose-pre:text-gray-500 dark:prose-pre:text-gray-100',
          'prose-details:bg-gray-50 dark:prose-details:bg-gray-800/50 prose-details:rounded-lg prose-details:border prose-details:border-gray-200 dark:prose-details:border-gray-700 prose-details:mb-4 prose-details:overflow-hidden',
          'prose-summary:px-4 prose-summary:py-2.5 prose-summary:bg-gray-100 dark:prose-summary:bg-gray-800 prose-summary:font-semibold prose-summary:cursor-pointer prose-summary:select-none hover:prose-summary:bg-gray-200 dark:hover:prose-summary:bg-gray-700 transition-colors',
          '[&_details[open]_summary]:border-b [&_details[open]_summary]:border-gray-200 dark:[&_details[open]_summary]:border-gray-700',
          '[&_details_>_*:not(summary)]:px-4 [&_details_>_*:not(summary)]:py-3 [&_details_>_*:last-child]:mb-3',
          '[&_input[type="checkbox"]]:w-4 [&_input[type="checkbox"]]:h-4 [&_input[type="checkbox"]]:text-primary [&_input[type="checkbox"]]:rounded [&_input[type="checkbox"]]:border-gray-300 [&_input[type="checkbox"]]:focus:ring-primary [&_input[type="checkbox"]]:cursor-default [&_input[type="checkbox"]]:mt-1.5 [&_input[type="checkbox"]]:align-top',
          '[&_li.task-list-item]:flex [&_li.task-list-item]:items-start [&_li.task-list-item]:gap-2 [&_li.task-list-item_>_p]:m-0',
        )}
      >
        <SourceChunkDrawer
          open={drawerState.open}
          onOpenChange={(open) => setDrawerState((prev) => ({ ...prev, open }))}
          title={drawerState.title}
          section={drawerState.section}
          snippet={drawerState.snippet}
          level={drawerState.level}
          snapshotStatus={drawerState.snapshotStatus}
          claimStatus={drawerState.claimStatus}
          claimConfidence={drawerState.claimConfidence}
          claimText={drawerState.claimText}
          resourceUri={drawerState.resourceUri}
          supersededFromUri={drawerState.supersededFromUri}
          thumbnailUrl={drawerState.thumbnailUrl}
          surface="chat"
          contextKey={`chat:${_messageId}`}
        />
        <ReactMarkdown
          remarkPlugins={[...chatMathPlugins.remark, remarkGfm, [remarkGitHubAlerts, { mode: 'component' }]]}
          // rehypeRaw 排在公式插件之前：消息里的原始 HTML 先解析成元素，chatMathPlugins 才能展开其中模型自己写的矢量标签
          rehypePlugins={[rehypeRaw, ...chatMathPlugins.rehype, [rehypeHeadingIds, { prefix: `toc-${_messageId}` }]]} // 将 AST 转换为最终的 HTML 结构
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
            // 公式：KaTeX 用矢量图画根号、向量箭头、花括号与删除线
            'svg',
            'path',
            'line',
            // 交互元素
            'input',
            'details',
            'summary',
            // Footnote
            'sup',
            'section',
            // 自定义标签
            'think',
            'thinking',
            'thought',
            'antthinking',
            'reasoning',
            'citation',
            'vault',
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
