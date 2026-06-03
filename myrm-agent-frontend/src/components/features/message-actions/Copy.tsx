import { Check, ChevronDown, Copy as CopyIcon, FileText, Type } from 'lucide-react';
import { Message } from '@/store/useChatStore';
import { RefObject, useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/primitives/dropdown-menu';

type CopiedState = 'idle' | 'markdown' | 'text';

function buildMarkdownContent(content: string, sources?: { url?: string }[]): string {
  if (!sources || sources.length === 0) return content;
  const citations = sources.map((s, i) => `[${i + 1}] ${s.url || 'Unknown source'}`).join('\n');
  return `${content}\n\nCitations:\n${citations}`;
}

function getPlainText(markdownRef: RefObject<HTMLDivElement | null>): string {
  return markdownRef.current?.innerText?.trim() ?? '';
}

const Copy = ({ message, markdownRef }: { message: Message; markdownRef: RefObject<HTMLDivElement | null> }) => {
  const [copied, setCopied] = useState<CopiedState>('idle');
  const t = useTranslations('chat');

  const flash = useCallback((state: CopiedState) => {
    setCopied(state);
    setTimeout(() => setCopied('idle'), 1200);
  }, []);

  const handleCopyMarkdown = useCallback(() => {
    const text = buildMarkdownContent(message.content, message.sources);
    writeToClipboard(text);
    flash('markdown');
  }, [message.content, message.sources, flash]);

  const handleCopyText = useCallback(() => {
    const text = getPlainText(markdownRef);
    if (text) {
      writeToClipboard(text);
      flash('text');
    }
  }, [markdownRef, flash]);

  const btnClass =
    'p-2 text-black/70 dark:text-white/70 rounded-xl hover:bg-secondary dark:hover:bg-secondary transition duration-200 hover:text-black dark:hover:text-white';

  if (copied !== 'idle') {
    return (
      <span className={btnClass}>
        <Check size={18} className="text-green-500" />
      </span>
    );
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className={`${btnClass} flex items-center gap-0.5`}>
          <CopyIcon size={18} />
          <ChevronDown size={12} className="opacity-50" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-[160px]">
        <DropdownMenuItem onClick={handleCopyMarkdown} className="gap-2">
          <FileText size={14} />
          {t('copyMarkdown')}
        </DropdownMenuItem>
        <DropdownMenuItem onClick={handleCopyText} className="gap-2">
          <Type size={14} />
          {t('copyText')}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
};

export default Copy;
