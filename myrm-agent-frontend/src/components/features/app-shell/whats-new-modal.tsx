'use client';

/**
 * [POS] 版本更新后"What's New"弹窗
 *
 * 应用启动时检测版本变更，从 GitHub Release API 拉取本版本的完整 Release Notes，
 * 以富文本 Markdown 形式展示给用户。关闭后将当前版本写入 localStorage，不再重复弹出。
 * 仅在 Tauri 桌面端生效。
 */

import { useTranslations } from 'next-intl';

import { useWhatsNew } from '@/hooks/useWhatsNew';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/primitives/dialog';

export function WhatsNewModal() {
  const t = useTranslations('whatsNew');
  const { visible, release, loading, dismiss } = useWhatsNew();

  if (loading || !visible || !release) return null;

  return (
    <Dialog open={visible} onOpenChange={(open) => !open && dismiss()}>
      <DialogContent className="max-w-md max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <SparkleIcon className="w-5 h-5 text-primary" />
            {t('title', { version: release.version })}
          </DialogTitle>
          <DialogDescription>{t('description')}</DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto -mx-1 px-1">
          <MarkdownBody body={release.body} />
        </div>

        <DialogFooter className="flex-shrink-0 pt-2">
          {release.htmlUrl && (
            <a
              href={release.htmlUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-muted-foreground hover:text-foreground underline underline-offset-2 mr-auto self-center"
            >
              {t('viewOnGitHub')}
            </a>
          )}
          <button
            onClick={dismiss}
            className="px-4 py-2 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground text-sm font-medium transition-colors"
          >
            {t('gotIt')}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function renderInline(text: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  const pattern = /!\[([^\]]*)\]\(([^)]+)\)|\[([^\]]+)\]\(([^)]+)\)|`([^`]+)`|\*\*(.+?)\*\*|\*(.+?)\*/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }

    if (match[2] !== undefined && match[1] !== undefined) {
      nodes.push(
        <img
          key={`img-${match.index}`}
          src={match[2]}
          alt={match[1] || ''}
          loading="lazy"
          className="max-w-full rounded-md mt-1"
          onError={(e) => {
            (e.target as HTMLImageElement).style.display = 'none';
          }}
        />,
      );
    } else if (match[3] !== undefined) {
      nodes.push(
        <a
          key={`a-${match.index}`}
          href={match[4]}
          target="_blank"
          rel="noopener noreferrer"
          className="text-primary hover:text-primary/80 underline underline-offset-2"
        >
          {match[3]}
        </a>,
      );
    } else if (match[5] !== undefined) {
      nodes.push(
        <code key={`c-${match.index}`} className="px-1 py-0.5 rounded bg-muted text-[0.85em] font-mono">
          {match[5]}
        </code>,
      );
    } else if (match[6] !== undefined) {
      nodes.push(<strong key={`b-${match.index}`}>{match[6]}</strong>);
    } else if (match[7] !== undefined) {
      nodes.push(<em key={`i-${match.index}`}>{match[7]}</em>);
    }

    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }

  return nodes;
}

function MarkdownBody({ body }: { body: string }) {
  const lines = body.trim().split('\n');
  const elements: React.ReactElement[] = [];
  let listItems: string[] = [];
  let listKey = 0;

  const flushList = () => {
    if (listItems.length === 0) return;
    elements.push(
      <ul key={`list-${listKey++}`} className="list-disc pl-5 space-y-1 text-sm text-foreground/90">
        {listItems.map((item, i) => (
          <li key={i}>{renderInline(item)}</li>
        ))}
      </ul>,
    );
    listItems = [];
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (line.startsWith('![')) {
      flushList();
      const imgMatch = /^!\[([^\]]*)\]\(([^)]+)\)/.exec(line);
      if (imgMatch) {
        elements.push(
          <img
            key={`img-${i}`}
            src={imgMatch[2]}
            alt={imgMatch[1] || ''}
            loading="lazy"
            className="max-w-full rounded-md"
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = 'none';
            }}
          />,
        );
      }
    } else if (/^#{1,3}\s/.test(line)) {
      flushList();
      const text = line.replace(/^#+\s*/, '');
      elements.push(
        <h3 key={`h-${i}`} className="text-sm font-semibold text-foreground mt-3 first:mt-0">
          {renderInline(text)}
        </h3>,
      );
    } else if (/^[-*]\s/.test(line)) {
      listItems.push(line.replace(/^[-*]\s*/, ''));
    } else if (line.trim() === '') {
      flushList();
    } else {
      flushList();
      elements.push(
        <p key={`p-${i}`} className="text-sm text-foreground/80 leading-relaxed">
          {renderInline(line)}
        </p>,
      );
    }
  }
  flushList();

  return <div className="space-y-2 py-2">{elements}</div>;
}

function SparkleIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
      <path d="M10 1l2.39 5.36L18 7.27l-4.12 3.59L15 16.36 10 13.4l-5 2.96 1.12-5.5L2 7.27l5.61-.91L10 1z" />
    </svg>
  );
}
