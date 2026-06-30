'use client';

import React, { memo, Suspense, useRef } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import MermaidChart from '../../markdown-render-tools/MermaidChart';
import CodeBlock from '../../markdown-render-tools/CodeBlock';
import DocumentSelectionToolbar from '../portal/DocumentSelectionToolbar';

/** 简单加载状态 */
const LoadingState: React.FC = () => (
  <div className="h-full flex items-center justify-center">
    <div className="animate-spin w-8 h-8 border-2 border-muted-foreground/30 border-t-primary rounded-full" />
  </div>
);

/** 骨架屏加载状态 */
const SkeletonLoader: React.FC = () => (
  <div className="h-full w-full p-4 space-y-3 bg-gray-50 dark:bg-gray-900">
    {Array.from({ length: 12 }).map((_, i) => (
      <div key={i} className="flex gap-3 animate-pulse">
        <div className="w-8 h-4 rounded bg-gray-200 dark:bg-gray-800" />
        <div
          className="h-4 rounded bg-gray-200 dark:bg-gray-800"
          style={{
            width: `${Math.random() * 40 + 30}%`,
            animationDelay: `${i * 50}ms`,
          }}
        />
      </div>
    ))}
  </div>
);

/** ReactMarkdown 渲染器（分离以便懒加载） */
const ReactMarkdownRenderer: React.FC<{ content: string }> = memo(({ content }) => {
  const ReactMarkdown = require('react-markdown').default;
  const remarkGfm = require('remark-gfm').default;
  const remarkMath = require('remark-math').default;
  const rehypeKatex = require('rehype-katex').default;

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkMath]}
      rehypePlugins={[rehypeKatex]}
      components={{
        code: ({
          node: _node,
          className,
          children,
          ...props
        }: {
          node?: unknown;
          className?: string;
          children?: React.ReactNode;
        }) => {
          const match = /language-(\w+)/.exec(className || '');
          const language = match?.[1] || '';
          const value = String(children).replace(/\n$/, '');

          // Mermaid 图表
          if (language === 'mermaid' && value.trim()) {
            return (
              <Suspense fallback={<LoadingState />}>
                <MermaidChart chart={value} />
              </Suspense>
            );
          }

          // 代码块 - 使用专业的 CodeBlock 组件（带语法高亮、行号、复制按钮）
          if (language) {
            return <CodeBlock language={language} value={value} />;
          }

          // 行内代码
          return (
            <code
              className="bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-100 px-1.5 py-0.5 rounded text-sm"
              {...props}
            >
              {children}
            </code>
          );
        },
        img: ({ src, alt, ...props }: { src?: string; alt?: string }) => (
          <img src={src} alt={alt || ''} loading="lazy" className="rounded-lg shadow-md max-w-full h-auto" {...props} />
        ),
        a: ({ href, children, ...props }: { href?: string; children?: React.ReactNode }) => (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary underline hover:text-primary/80"
            {...props}
          >
            {children}
          </a>
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  );
});
ReactMarkdownRenderer.displayName = 'ReactMarkdownRenderer';

/** Markdown 实时渲染预览组件 */
const MarkdownPreview: React.FC<{ content: string; artifactId?: string }> = memo(({ content, artifactId }) => {
  const containerRef = useRef<HTMLDivElement>(null);

  return (
    <div
      ref={containerRef}
      className={cn(
        'h-full overflow-auto p-6 relative',
        'bg-background',
        'prose prose-sm dark:prose-invert max-w-none',
        'prose-headings:font-semibold',
        'prose-h1:text-2xl prose-h1:mb-4 prose-h1:mt-6',
        'prose-h2:text-xl prose-h2:mb-3 prose-h2:mt-5',
        'prose-h3:text-lg prose-h3:mb-2 prose-h3:mt-4',
        'prose-p:leading-relaxed prose-p:mb-3',
        'prose-ul:my-2 prose-ol:my-2',
        'prose-li:my-1',
        'prose-code:bg-gray-100 dark:prose-code:bg-gray-800',
        'prose-code:text-gray-900 dark:prose-code:text-gray-100',
        'prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-sm',
        'prose-pre:bg-transparent prose-pre:p-0 prose-pre:m-0',
        'prose-pre:rounded-none prose-pre:shadow-none',
        '[&_pre:not([data-code-block])]:bg-gray-100 [&_pre:not([data-code-block])]:dark:bg-gray-800',
        '[&_pre:not([data-code-block])]:px-3 [&_pre:not([data-code-block])]:py-2',
        '[&_pre:not([data-code-block])]:rounded-lg [&_pre:not([data-code-block])]:text-sm',
        'prose-blockquote:border-l-4 prose-blockquote:border-primary/50 prose-blockquote:pl-4 prose-blockquote:italic',
        'prose-a:text-primary prose-a:underline hover:prose-a:text-primary/80',
        'prose-table:border-collapse prose-th:border prose-th:border-border prose-th:p-2 prose-th:bg-muted',
        'prose-td:border prose-td:border-border prose-td:p-2',
        'prose-img:rounded-lg prose-img:shadow-md',
      )}
    >
      <Suspense fallback={<SkeletonLoader />}>
        <ReactMarkdownRenderer content={content} />
      </Suspense>
      {artifactId && (
        <DocumentSelectionToolbar containerRef={containerRef} artifactId={artifactId} />
      )}
    </div>
  );
});
MarkdownPreview.displayName = 'MarkdownPreview';

/** 文档/Markdown 预览组件 */
const DocumentPreview: React.FC<{ content: string; filename?: string; artifactId?: string }> = memo(({ content, filename, artifactId }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const isMarkdown = filename?.match(/\.(md|markdown|mdx)$/i);

  if (isMarkdown) {
    return <MarkdownPreview content={content} artifactId={artifactId} />;
  }

  return (
    <div
      ref={containerRef}
      className={cn('h-full overflow-auto p-6 relative', 'bg-background', 'prose prose-sm dark:prose-invert max-w-none')}
    >
      <pre className="whitespace-pre-wrap font-sans text-foreground">{content}</pre>
      {artifactId && (
        <DocumentSelectionToolbar containerRef={containerRef} artifactId={artifactId} />
      )}
    </div>
  );
});
DocumentPreview.displayName = 'DocumentPreview';

export default DocumentPreview;
