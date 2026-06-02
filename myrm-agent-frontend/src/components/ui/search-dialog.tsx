'use client';

import { useState, useEffect, useRef, useCallback, useMemo, forwardRef } from 'react';
import { createPortal } from 'react-dom';
import { Search, X, Loader2, MessageSquare, Calendar } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { searchChatHistory, type SearchResult } from '@/services/chat';

type TimePreset = 'today' | 'week' | 'month' | 'quarter' | null;

function computePresetRange(preset: TimePreset): { since?: string; until?: string } {
  if (!preset) return {};
  const now = new Date();
  const until = now.toISOString();
  const start = new Date(now);
  switch (preset) {
    case 'today':
      start.setHours(0, 0, 0, 0);
      break;
    case 'week':
      start.setDate(start.getDate() - 7);
      break;
    case 'month':
      start.setMonth(start.getMonth() - 1);
      break;
    case 'quarter':
      start.setMonth(start.getMonth() - 3);
      break;
  }
  return { since: start.toISOString(), until };
}

interface SearchDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  className?: string;
  children: React.ReactNode;
}

export function SearchDialog({ open, onOpenChange, className, children }: SearchDialogProps) {
  const t = useTranslations();
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [mounted, setMounted] = useState(false);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [timePreset, setTimePreset] = useState<TimePreset>(null);
  const [showTimeFilter, setShowTimeFilter] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const timeRange = useMemo(() => computePresetRange(timePreset), [timePreset]);

  useEffect(() => {
    setMounted(true);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  useEffect(() => {
    if (open) {
      const timer = setTimeout(() => inputRef.current?.focus(), 100);
      document.body.style.overflow = 'hidden';
      return () => {
        clearTimeout(timer);
        document.body.style.overflow = '';
      };
    }
    setQuery('');
    setResults([]);
    setTotal(0);
    setHasSearched(false);
    setTimePreset(null);
    setShowTimeFilter(false);
    document.body.style.overflow = '';
  }, [open]);

  // Cmd+K / Ctrl+K global shortcut
  useEffect(() => {
    const handleGlobalKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        onOpenChange(!open);
      }
    };
    window.addEventListener('keydown', handleGlobalKeyDown);
    return () => window.removeEventListener('keydown', handleGlobalKeyDown);
  }, [open, onOpenChange]);

  const doSearch = useCallback(async (q: string, since?: string, until?: string) => {
    if (!q.trim()) {
      setResults([]);
      setTotal(0);
      setHasSearched(false);
      return;
    }
    setLoading(true);
    setHasSearched(true);
    try {
      const data = await searchChatHistory(q.trim(), 20, 0, since, until);
      setResults(data.items);
      setTotal(data.total);
    } catch {
      setResults([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (query.trim()) {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => doSearch(query, timeRange.since, timeRange.until), 300);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [timePreset]);

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const value = e.target.value;
      setQuery(value);
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => doSearch(value, timeRange.since, timeRange.until), 300);
    },
    [doSearch, timeRange],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Escape') onOpenChange(false);
    },
    [onOpenChange],
  );

  const handleResultClick = useCallback(
    (chatId: string, messageId: string) => {
      router.push(`/${chatId}?highlight=${messageId}`);
      onOpenChange(false);
    },
    [router, onOpenChange],
  );

  const handleBackdropClick = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === e.currentTarget) onOpenChange(false);
    },
    [onOpenChange],
  );

  const formatDate = (dateStr: string) => {
    try {
      const d = new Date(dateStr);
      return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
    } catch {
      return '';
    }
  };

  const dialogContent =
    open && mounted ? (
      <div
        className="fixed inset-0 bg-black/30 flex items-start justify-center pt-[10vh] sm:pt-[15vh] z-[9999] px-4 pb-4"
        onClick={handleBackdropClick}
      >
        <div
          className={cn(
            'bg-background rounded-xl shadow-2xl border border-border',
            'w-full max-w-2xl max-h-[70vh] flex flex-col overflow-hidden',
            className,
          )}
        >
          {/* Search Input */}
          <div className="flex items-center px-4 py-3 border-b border-border">
            <Search size={18} className="text-muted-foreground mr-3 shrink-0" />
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={handleChange}
              onKeyDown={handleKeyDown}
              placeholder={t('search.placeholder')}
              className="flex-1 text-base bg-transparent border-none outline-none text-foreground placeholder:text-muted-foreground/60"
              spellCheck={false}
              autoComplete="off"
            />
            {query && (
              <button
                onClick={() => {
                  setQuery('');
                  setResults([]);
                  setTotal(0);
                  setHasSearched(false);
                  inputRef.current?.focus();
                }}
                className="p-1 hover:bg-muted rounded-full text-muted-foreground transition-colors mr-2"
              >
                <X size={16} />
              </button>
            )}
            <button
              onClick={() => setShowTimeFilter(!showTimeFilter)}
              className={cn(
                'p-1.5 rounded-full transition-colors mr-2',
                showTimeFilter || timePreset ? 'bg-primary/10 text-primary' : 'hover:bg-muted text-muted-foreground',
              )}
              title={t('search.timeFilter')}
            >
              <Calendar size={15} />
            </button>
            <kbd className="hidden sm:inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground bg-muted rounded border border-border">
              ESC
            </kbd>
          </div>

          {showTimeFilter && (
            <div className="flex items-center gap-1.5 px-4 py-2 border-b border-border bg-muted/20">
              {(['today', 'week', 'month', 'quarter'] as const).map((preset) => (
                <button
                  key={preset}
                  onClick={() => setTimePreset(timePreset === preset ? null : preset)}
                  className={cn(
                    'px-2.5 py-1 text-xs rounded-full transition-colors',
                    timePreset === preset
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-muted hover:bg-muted/80 text-muted-foreground',
                  )}
                >
                  {t(
                    `search.preset${preset.charAt(0).toUpperCase() + preset.slice(1)}` as
                      | 'search.presetToday'
                      | 'search.presetWeek'
                      | 'search.presetMonth'
                      | 'search.presetQuarter',
                  )}
                </button>
              ))}
              {timePreset && (
                <button
                  onClick={() => setTimePreset(null)}
                  className="ml-auto text-xs text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1"
                >
                  <X size={12} />
                  {t('search.clearTimeFilter')}
                </button>
              )}
            </div>
          )}

          {/* Results Area */}
          <div className="flex-1 overflow-y-auto p-2">
            {loading ? (
              <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                <Loader2 className="w-5 h-5 animate-spin mb-2" />
                <span className="text-sm">{t('search.searching')}</span>
              </div>
            ) : hasSearched && results.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                <Search className="w-7 h-7 mb-3 opacity-20" />
                <span className="text-sm">{t('search.noResults')}</span>
              </div>
            ) : !hasSearched ? (
              <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                <Search className="w-7 h-7 mb-3 opacity-15" />
                <span className="text-sm">{t('search.hint')}</span>
              </div>
            ) : (
              <div className="space-y-0.5">
                {results.map((item) => (
                  <button
                    key={item.id}
                    onClick={() => handleResultClick(item.chat_id, String(item.id))}
                    className="w-full text-left p-3 rounded-lg hover:bg-muted/50 transition-colors flex flex-col gap-1.5"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 text-sm font-medium text-foreground truncate min-w-0">
                        <MessageSquare className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                        <span className="truncate">{item.chat_title || t('chat.newChat')}</span>
                      </div>
                      <div className="flex items-center gap-1.5 text-xs text-muted-foreground shrink-0">
                        <Calendar className="w-3 h-3" />
                        <span>{formatDate(item.sent_at)}</span>
                      </div>
                    </div>
                    <div className="text-sm text-muted-foreground line-clamp-2 pl-5">
                      <span
                        className={cn(
                          'inline-block px-1.5 py-0.5 rounded text-[10px] font-medium mr-2 uppercase',
                          item.role === 'user'
                            ? 'bg-primary/10 text-primary'
                            : 'bg-secondary text-secondary-foreground',
                        )}
                      >
                        {item.role}
                      </span>
                      <span
                        dangerouslySetInnerHTML={{
                          __html: item.snippet,
                        }}
                      />
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Footer */}
          {hasSearched && !loading && total > 0 && (
            <div className="px-4 py-2 border-t border-border bg-muted/30 text-xs text-muted-foreground flex justify-between items-center">
              <span>{t('search.resultsCount', { count: total })}</span>
              <kbd className="hidden sm:inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground bg-muted rounded border border-border">
                ⌘K
              </kbd>
            </div>
          )}
        </div>
      </div>
    ) : null;

  return (
    <>
      {children}
      {mounted && dialogContent && createPortal(dialogContent, document.body)}
    </>
  );
}

interface SearchTriggerProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  placeholder?: string;
  onOpenDialog?: () => void;
}

export const SearchTrigger = forwardRef<HTMLButtonElement, SearchTriggerProps>(
  ({ placeholder, onOpenDialog, className, ...props }, ref) => {
    const t = useTranslations();

    return (
      <button
        ref={ref}
        onClick={onOpenDialog}
        className={cn(
          'flex items-center gap-2 px-3 h-9 rounded-full',
          'bg-muted/50 border border-border/50',
          'text-sm',
          'hover:bg-muted hover:border-border',
          'transition-all duration-200',
          'w-full',
          className,
        )}
        {...props}
      >
        <Search size={14} className="shrink-0 text-muted-foreground/50" />
        <span className="flex-1 text-left truncate text-muted-foreground/50">
          {placeholder || t('search.placeholder')}
        </span>
        <kbd className="hidden sm:inline-flex items-center gap-0.5 px-1 py-0.5 text-[10px] font-medium text-muted-foreground/50 bg-muted/80 rounded border border-border/50">
          ⌘K
        </kbd>
      </button>
    );
  },
);

SearchTrigger.displayName = 'SearchTrigger';
