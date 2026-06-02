'use client';

import { RefObject, useCallback, useRef, useState } from 'react';
import { ChevronDown, Download, FileText, FileImage, Globe, FileType } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useTheme } from 'next-themes';
import { toast } from 'sonner';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Checkbox } from '@/components/ui/checkbox';
import {
  downloadMessageAsMarkdown,
  downloadMessageAsDocx,
  downloadMessageAsHtml,
  downloadMessageAsImage,
} from '@/lib/utils/chatExport';
import type { Message } from '@/store/chat/types';

const LONG_CONTENT_THRESHOLD = 50_000;

interface ExportMenuProps {
  message: Message;
  markdownRef: RefObject<HTMLDivElement | null>;
}

export default function ExportMenu({ message, markdownRef }: ExportMenuProps) {
  const t = useTranslations('chat');
  const { resolvedTheme } = useTheme();
  const [includeReasoning, setIncludeReasoning] = useState(false);
  const [exporting, setExporting] = useState(false);
  const exportingRef = useRef(false);
  const hasReasoning = Boolean(message.reasoning);
  const theme = (resolvedTheme === 'dark' ? 'dark' : 'light') as 'light' | 'dark';

  const withGuard = useCallback(
    async (fn: () => Promise<void>) => {
      if (exportingRef.current) return;
      exportingRef.current = true;
      setExporting(true);
      try {
        await fn();
      } catch (err) {
        toast.error(t('exportMessage.exportFailed'));
        console.error('[ExportMenu]', err);
      } finally {
        exportingRef.current = false;
        setExporting(false);
      }
    },
    [t],
  );

  const handleMarkdown = useCallback(() => {
    downloadMessageAsMarkdown(message, includeReasoning);
  }, [message, includeReasoning]);

  const handleHtml = useCallback(() => {
    void withGuard(() => downloadMessageAsHtml(message, includeReasoning, theme));
  }, [message, includeReasoning, theme, withGuard]);

  const handleDocx = useCallback(() => {
    void withGuard(() => downloadMessageAsDocx(message, includeReasoning));
  }, [message, includeReasoning, withGuard]);

  const handleImage = useCallback(() => {
    const el = markdownRef.current;
    if (!el) return;
    if (message.content.length > LONG_CONTENT_THRESHOLD) {
      const confirmed = window.confirm(t('exportMessage.longContentWarning'));
      if (!confirmed) return;
    }
    void withGuard(() => downloadMessageAsImage(el, message));
  }, [markdownRef, message, t, withGuard]);

  const btnClass =
    'p-2 text-black/70 dark:text-white/70 rounded-xl hover:bg-secondary dark:hover:bg-secondary transition duration-200 hover:text-black dark:hover:text-white';

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className={`${btnClass} flex items-center gap-0.5`} disabled={exporting}>
          <Download size={18} />
          <ChevronDown size={12} className="opacity-50" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-[180px]">
        <DropdownMenuItem onClick={handleMarkdown} className="gap-2">
          <FileText size={14} />
          {t('exportMessage.markdown')}
        </DropdownMenuItem>
        <DropdownMenuItem onClick={handleDocx} className="gap-2">
          <FileType size={14} />
          {t('exportMessage.word')}
        </DropdownMenuItem>
        <DropdownMenuItem onClick={handleHtml} className="gap-2">
          <Globe size={14} />
          {t('exportMessage.html')}
        </DropdownMenuItem>
        <DropdownMenuItem onClick={handleImage} className="gap-2">
          <FileImage size={14} />
          {t('exportMessage.image')}
        </DropdownMenuItem>
        {hasReasoning && (
          <>
            <DropdownMenuSeparator />
            <div
              className="flex items-center gap-2 px-2 py-1.5 cursor-pointer"
              onClick={() => setIncludeReasoning(!includeReasoning)}
            >
              <Checkbox
                id="export-reasoning"
                checked={includeReasoning}
                onCheckedChange={(v) => setIncludeReasoning(Boolean(v))}
              />
              <label htmlFor="export-reasoning" className="text-sm cursor-pointer select-none">
                {t('exportMessage.includeReasoning')}
              </label>
            </div>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
