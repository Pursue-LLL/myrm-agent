'use client';

import React, { useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import { cn } from '@/lib/utils/classnameUtils';
import CodeBlock from '@/components/ui/markdown-render-tools/CodeBlock';
import { getChildrenAsText } from '@/lib/utils/reactUtils';
import { useTranslations } from 'next-intl';

interface KanbanMarkdownProps {
  children: string;
  maxLines?: number;
  className?: string;
}

const ALLOWED_ELEMENTS = [
  'p',
  'h1',
  'h2',
  'h3',
  'h4',
  'h5',
  'h6',
  'br',
  'strong',
  'em',
  'code',
  'del',
  'ul',
  'ol',
  'li',
  'blockquote',
  'hr',
  'table',
  'thead',
  'tbody',
  'tr',
  'th',
  'td',
  'pre',
  'a',
  'img',
  'div',
  'span',
  'input',
];

const components = {
  code: ({ node: _node, className: codeClassName, children, ...props }: any) => {
    const match = /language-(\w+)/.exec(codeClassName || '');
    const language = match?.[1] ?? '';
    const value = getChildrenAsText(children);

    if (language) {
      return <CodeBlock language={language} value={value} isStreaming={false} />;
    }

    return (
      <code className="bg-muted font-normal text-foreground px-1 py-0.5 rounded text-[10px]" {...props}>
        {value}
      </code>
    );
  },
  a: ({ href, children }: { href?: string; children?: React.ReactNode }) => {
    const trimmed = href?.trim() ?? '';
    if (!/^(https?:|mailto:)/i.test(trimmed)) {
      return <span>{children}</span>;
    }
    return (
      <a
        href={trimmed}
        target="_blank"
        rel="noopener noreferrer"
        className="text-primary underline decoration-primary/30 hover:decoration-primary transition-colors break-all"
      >
        {children}
      </a>
    );
  },
};

const LINE_CLAMP_CLASS: Record<number, string> = {
  2: 'line-clamp-2',
  3: 'line-clamp-3',
  4: 'line-clamp-4',
  6: 'line-clamp-6',
};

const KanbanMarkdown = React.memo(({ children: content, maxLines, className }: KanbanMarkdownProps) => {
  const t = useTranslations('kanban');
  const [expanded, setExpanded] = useState(false);

  const shouldClamp = Boolean(maxLines && !expanded);

  const proseClasses = useMemo(
    () =>
      cn(
        'prose prose-xs dark:prose-invert max-w-none break-words',
        'prose-headings:text-xs prose-headings:font-semibold prose-headings:mt-2 prose-headings:mb-1',
        'prose-p:text-[11px] prose-p:leading-relaxed prose-p:my-0.5',
        'prose-li:text-[11px] prose-li:my-0',
        'prose-code:text-[10px]',
        'prose-pre:text-[10px] prose-pre:bg-transparent prose-pre:p-0 prose-pre:my-1',
        'prose-ul:my-0.5 prose-ol:my-0.5',
        'prose-strong:text-foreground',
        'prose-table:text-[10px] prose-th:px-2 prose-th:py-1 prose-td:px-2 prose-td:py-1',
        '[&_*]:text-inherit',
        className,
      ),
    [className],
  );

  return (
    <div className="relative">
      <div className={cn(proseClasses, shouldClamp && maxLines && LINE_CLAMP_CLASS[maxLines])}>
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypeRaw]}
          components={components}
          allowedElements={ALLOWED_ELEMENTS}
          unwrapDisallowed={true}
        >
          {content}
        </ReactMarkdown>
      </div>
      {shouldClamp && (
        <button
          onClick={() => setExpanded(true)}
          className="text-[9px] text-primary/70 hover:text-primary mt-0.5 transition-colors"
        >
          {t('showMore')}
        </button>
      )}
      {maxLines && expanded && (
        <button
          onClick={() => setExpanded(false)}
          className="text-[9px] text-primary/70 hover:text-primary mt-0.5 transition-colors"
        >
          {t('showLess')}
        </button>
      )}
    </div>
  );
});

KanbanMarkdown.displayName = 'KanbanMarkdown';

export default KanbanMarkdown;
