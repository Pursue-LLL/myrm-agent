'use client';

/**
 * [INPUT]
 * - @/services/chat::ReferenceSuggestion (POS: Chat API DTO contracts)
 * - @/components/ui/popover::Popover (POS: Floating panel primitive)
 *
 * [OUTPUT]
 * - ReferenceMentionPopover: renders selectable structured @ reference suggestions.
 *
 * [POS]
 * Structured @ reference suggestion view. Shows workspace, stored-file and special reference candidates for MessageInput.
 */
import * as React from 'react';
import { FileText, Folder, FileCode, FileJson, Image, Lightbulb } from 'lucide-react';
import { IconGlow } from '@/components/ui/icons/PremiumIcons';
import { Popover, PopoverContent, PopoverAnchor } from '@/components/ui/popover';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import type { ReferenceSuggestion } from '@/services/chat';

interface ReferenceMentionPopoverProps {
  open: boolean;
  results: ReferenceSuggestion[];
  selectedIndex: number;
  query: string;
  onSelect: (reference: ReferenceSuggestion) => void;
  anchorEl?: HTMLElement | null;
}

const EXT_ICON_MAP: Record<string, React.ElementType> = {
  '.ts': FileCode,
  '.tsx': FileCode,
  '.js': FileCode,
  '.jsx': FileCode,
  '.py': FileCode,
  '.go': FileCode,
  '.rs': FileCode,
  '.java': FileCode,
  '.json': FileJson,
  '.yaml': FileJson,
  '.yml': FileJson,
  '.toml': FileJson,
  '.png': Image,
  '.jpg': Image,
  '.jpeg': Image,
  '.gif': Image,
  '.svg': Image,
  '.webp': Image,
};

function getFileIcon(name: string): React.ElementType {
  const ext = name.includes('.') ? '.' + name.split('.').pop()!.toLowerCase() : '';
  return EXT_ICON_MAP[ext] ?? FileText;
}

function formatSize(bytes: number | null): string {
  if (bytes === null) return '';
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}

function highlightMatch(text: string, ranges: Array<[number, number]>): React.ReactNode {
  if (ranges.length === 0) return text;
  const [start, end] = ranges[0];
  if (start < 0 || end <= start || start >= text.length) return text;
  return (
    <>
      {text.slice(0, start)}
      <span className="text-primary font-semibold">{text.slice(start, end)}</span>
      {text.slice(end)}
    </>
  );
}

export const ReferenceMentionPopover: React.FC<ReferenceMentionPopoverProps> = ({
  open,
  results,
  selectedIndex,
  query,
  onSelect,
  anchorEl,
}) => {
  const t = useTranslations('chat.fileMention');
  const listRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!listRef.current || selectedIndex < 0) return;
    const items = listRef.current.querySelectorAll('[data-mention-item]');
    const target = items[selectedIndex] as HTMLElement | undefined;
    target?.scrollIntoView({ block: 'nearest' });
  }, [selectedIndex]);

  if (!open) return null;

  return (
    <Popover open={open} modal={false}>
      {anchorEl && <PopoverAnchor virtualRef={{ current: anchorEl }} />}
      <PopoverContent
        className="w-[380px] p-0 shadow-xl border-border/50"
        side="top"
        align="start"
        sideOffset={8}
        onOpenAutoFocus={(e) => e.preventDefault()}
        onInteractOutside={(e) => e.preventDefault()}
      >
        <div className="flex flex-col">
          <div className="px-3 py-2 border-b border-border/50">
            <span className="text-xs font-medium text-muted-foreground">{t('title')}</span>
          </div>

          {/* Special References Hint */}
          {query.length === 0 && (
            <div className="px-3 py-2 bg-muted/20 border-b border-border/30">
              <div className="flex items-start gap-2">
                <Lightbulb className="w-3.5 h-3.5 text-primary/60 shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-muted-foreground leading-relaxed">{t('specialReferencesHint')}</p>
                  <div className="flex flex-wrap gap-1.5 mt-1.5">
                    <code className="px-1.5 py-0.5 text-[10px] bg-background/60 rounded border border-border/40 text-primary/80">
                      @staged
                    </code>
                    <code className="px-1.5 py-0.5 text-[10px] bg-background/60 rounded border border-border/40 text-primary/80">
                      @diff
                    </code>
                    <code className="px-1.5 py-0.5 text-[10px] bg-background/60 rounded border border-border/40 text-primary/80">
                      @folder:path
                    </code>
                    <code className="px-1.5 py-0.5 text-[10px] bg-background/60 rounded border border-border/40 text-primary/80">
                      @url:link
                    </code>
                    <code className="px-1.5 py-0.5 text-[10px] bg-background/60 rounded border border-border/40 text-primary/80">
                      file:10-20
                    </code>
                  </div>
                </div>
              </div>
            </div>
          )}

          <div ref={listRef} className="max-h-[300px] overflow-y-auto py-1">
            {results.length === 0 ? (
              <div className="py-6 text-center">
                <Folder className="w-10 h-10 mx-auto mb-2 text-muted-foreground/30" />
                <p className="text-sm text-muted-foreground">{t('noResults')}</p>
              </div>
            ) : (
              results.map((file, index) => {
                const isSpecial = file.source === 'special';
                const isSelected = index === selectedIndex;
                const title = file.basename || file.label;
                const subtitle = file.directory || file.description || file.relative_path || '';
                const Icon = isSpecial ? IconGlow : getFileIcon(title);
                return (
                  <button
                    key={`${file.reference_type}:${file.relative_path ?? file.file_id ?? file.label}`}
                    data-mention-item
                    type="button"
                    className={cn(
                      'flex items-center gap-3 w-full px-3 py-2 text-left transition-colors',
                      'hover:bg-accent/50',
                      isSelected && 'bg-accent',
                      isSpecial && 'bg-primary/5',
                    )}
                    onClick={() => onSelect(file)}
                    onMouseEnter={() => {}}
                  >
                    <Icon className={cn('w-4 h-4 shrink-0', isSpecial ? 'text-primary/70' : 'text-muted-foreground')} />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium truncate">
                        {isSpecial ? title : highlightMatch(title, file.match_ranges)}
                      </div>
                      <div className="text-xs text-muted-foreground/70 truncate">{subtitle}</div>
                    </div>
                    {file.size !== null && (
                      <span className="text-[10px] text-muted-foreground/50 shrink-0">{formatSize(file.size)}</span>
                    )}
                  </button>
                );
              })
            )}
          </div>

          <div className="px-3 py-1.5 border-t border-border/50 flex items-center gap-3 text-[10px] text-muted-foreground/50">
            <span>↑↓ {t('navigate')}</span>
            <span>↵ {t('select')}</span>
            <span>Esc {t('dismiss')}</span>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
};
