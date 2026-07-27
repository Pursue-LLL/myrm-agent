/**
 * SourceChunkDrawer — KB 引用原文片段 Drawer
 *
 * [POS]
 * 当用户点击 KB 类型的 citation 标记时，以右侧 Sheet 展示原文 snippet。
 * 以分段渲染展示原文片段与分层标签（L0/L1/L2），使用户能快速验证 AI 引用来源的可信度。
 */
'use client';

import React, { useMemo } from 'react';
import { BookOpen, X } from 'lucide-react';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/primitives/sheet';
import { useTranslations } from 'next-intl';
import { WikiSourceLevel } from '@/store/chat/types';

interface SourceChunkDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  section?: string;
  snippet: string;
  level?: WikiSourceLevel;
}

function renderSnippetParagraphs(text: string, maxSegments: number = 3): React.ReactNode[] {
  if (!text) return [];

  const sentences = text.split(/(?<=[。.!?！？\n])\s*/);
  const segments = sentences.slice(0, maxSegments);
  return segments.map((seg, i) => (
    <p key={i} className="text-sm text-foreground/90 leading-relaxed mb-2 last:mb-0">
      {seg}
    </p>
  ));
}

const SourceChunkDrawer: React.FC<SourceChunkDrawerProps> = React.memo(
  ({ open, onOpenChange, title, section, snippet, level }) => {
    const t = useTranslations('MessageSources');
    const renderedSnippet = useMemo(() => renderSnippetParagraphs(snippet), [snippet]);
    const levelLabel = useMemo(() => {
      if (level === 'L0') return t('kb_level_l0');
      if (level === 'L1') return t('kb_level_l1');
      if (level === 'L2') return t('kb_level_l2');
      return '';
    }, [level, t]);

    return (
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent side="right" hideCloseButton className="w-full sm:max-w-md flex flex-col p-0">
          <SheetHeader className="px-5 pt-5 pb-3 border-b border-border/50 flex-shrink-0">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5 min-w-0">
                <div className="bg-amber-500/20 flex items-center justify-center w-8 h-8 rounded-full flex-shrink-0">
                  <BookOpen size={16} className="text-amber-600 dark:text-amber-400" />
                </div>
                <div className="min-w-0">
                  <SheetTitle className="text-base truncate">{title}</SheetTitle>
                  <div className="flex items-center gap-2 mt-0.5 min-w-0">
                    {section && <p className="text-xs text-muted-foreground truncate">§ {section}</p>}
                    {levelLabel && (
                      <span className="text-[10px] leading-4 px-1.5 py-0.5 rounded-full bg-amber-500/15 text-amber-700 dark:text-amber-300 border border-amber-500/30">
                        {levelLabel}
                      </span>
                    )}
                  </div>
                </div>
              </div>
              <button
                onClick={() => onOpenChange(false)}
                className="rounded-full p-1.5 hover:bg-muted transition-colors flex-shrink-0"
              >
                <X size={16} className="text-muted-foreground" />
              </button>
            </div>
          </SheetHeader>

          <div className="flex-1 overflow-y-auto px-5 py-4">
            <div className="flex items-center gap-1.5 mb-3">
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                {t('source_excerpt')}
              </span>
            </div>

            <div className="bg-muted/40 rounded-lg p-4 border border-border/30">
              {renderedSnippet.length > 0 ? (
                renderedSnippet
              ) : (
                <p className="text-sm text-muted-foreground italic">{t('no_snippet')}</p>
              )}
            </div>

            <p className="text-xs text-muted-foreground mt-4 flex items-center gap-1">
              <BookOpen size={12} />
              {t('knowledge_base')}: LLM-Wiki
            </p>
          </div>
        </SheetContent>
      </Sheet>
    );
  },
);

SourceChunkDrawer.displayName = 'SourceChunkDrawer';

export default SourceChunkDrawer;
