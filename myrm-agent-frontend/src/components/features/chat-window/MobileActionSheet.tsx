/**
 * [INPUT]
 * - react-dom::createPortal (POS: React Portal DOM 渲染)
 * - @/lib/utils/classnameUtils::cn (POS: Tailwind 类名合并工具)
 *
 * [OUTPUT]
 * - MobileActionSheet: 移动端底部弹出式操作面板，支持子菜单滑动切换。
 * - MobileActionSheetEntry / MobileActionSheetOption / MobileActionSheetSubMenu: 类型定义
 *
 * [POS]
 * 移动端工具选择交互层。以 ActionSheet 模式展示结构化操作列表，支持主菜单→子菜单的滑动导航。
 */
'use client';

import { type ReactNode, useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { ChevronRight, ChevronLeft } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface MobileActionSheetOption {
  key: string;
  label: ReactNode;
  description?: ReactNode;
  active?: boolean;
}

export interface MobileActionSheetSubMenu {
  title: ReactNode;
  options: MobileActionSheetOption[];
  onSelect: (key: string) => void;
  emptyText?: ReactNode;
  /** When false, options behave as plain action rows (no radio indicator). Default: true. */
  selectable?: boolean;
}

export interface MobileActionSheetEntry {
  key: string;
  icon?: ReactNode;
  label: ReactNode;
  description?: ReactNode;
  /** Right-side hint text, e.g. current model name */
  meta?: ReactNode;
  dividerBefore?: boolean;
  submenu?: MobileActionSheetSubMenu;
  onClick?: () => void;
  disabled?: boolean;
}

export interface MobileActionSheetProps {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  entries: MobileActionSheetEntry[];
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TRANSITION_MS = 280;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function MobileActionSheet({ open, onClose, title, entries }: MobileActionSheetProps) {
  const t = useTranslations('common');
  const [mounted, setMounted] = useState(false);
  const [visible, setVisible] = useState(false);
  const [activeSubKey, setActiveSubKey] = useState<string | null>(null);
  const [subVisible, setSubVisible] = useState(false);
  const rafRef = useRef<number>(0);

  // Mount/unmount lifecycle
  useEffect(() => {
    if (open) {
      setMounted(true);
      // Double-rAF ensures the initial off-screen frame paints before transition starts
      rafRef.current = requestAnimationFrame(() => {
        rafRef.current = requestAnimationFrame(() => setVisible(true));
      });
      return;
    }
    setVisible(false);
    setActiveSubKey(null);
    setSubVisible(false);
    const timer = setTimeout(() => setMounted(false), TRANSITION_MS);
    return () => clearTimeout(timer);
  }, [open]);

  useEffect(() => {
    return () => cancelAnimationFrame(rafRef.current);
  }, []);

  // Lock body scroll when open
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  // Sub-menu animation
  useEffect(() => {
    if (activeSubKey) {
      requestAnimationFrame(() => setSubVisible(true));
    } else {
      setSubVisible(false);
    }
  }, [activeSubKey]);

  const handleEntryClick = useCallback(
    (entry: MobileActionSheetEntry) => {
      if (entry.disabled) return;
      if (entry.submenu) {
        setActiveSubKey(entry.key);
        return;
      }
      entry.onClick?.();
      onClose();
    },
    [onClose],
  );

  const handleSubSelect = useCallback(
    (key: string) => {
      const activeEntry = entries.find((e) => e.key === activeSubKey);
      const sub = activeEntry?.submenu;
      if (!sub) return;
      sub.onSelect(key);
      if (sub.selectable !== false) {
        setActiveSubKey(null);
        return;
      }
      onClose();
    },
    [activeSubKey, entries, onClose],
  );

  const handleBack = useCallback(() => setActiveSubKey(null), []);

  if (!mounted) return null;

  const activeEntry = activeSubKey ? entries.find((e) => e.key === activeSubKey) : null;
  const activeSub = activeEntry?.submenu;

  return createPortal(
    <>
      {/* Backdrop */}
      <div
        className={cn(
          'fixed inset-0 z-[1100] bg-black/40 transition-opacity duration-200',
          visible ? 'opacity-100' : 'opacity-0 pointer-events-none',
        )}
        onClick={onClose}
      />
      {/* Sheet */}
      <div
        className={cn(
          'fixed inset-x-0 bottom-0 z-[1101] flex flex-col',
          'max-h-[72vh] rounded-t-2xl bg-background shadow-2xl',
          'transition-transform duration-[280ms] ease-[cubic-bezier(0.32,0.72,0,1)]',
          'pb-[env(safe-area-inset-bottom,0px)]',
          visible ? 'translate-y-0' : 'translate-y-full',
        )}
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Handle bar */}
        <div className="mx-auto mt-2 mb-1 h-1 w-9 shrink-0 rounded-full bg-muted-foreground/30" />

        {/* Panes wrapper */}
        <div className="relative overflow-hidden flex-1 min-h-0">
          {/* Main pane */}
          <div
            className={cn(
              'flex flex-col transition-transform duration-[260ms] ease-[cubic-bezier(0.32,0.72,0,1)]',
              subVisible ? '-translate-x-[24%]' : 'translate-x-0',
            )}
            aria-hidden={subVisible}
          >
            {title && <div className="shrink-0 px-4 pt-1 pb-1 text-sm font-semibold text-foreground">{title}</div>}
            <div className="flex-1 min-h-0 overflow-y-auto py-1">
              {entries.map((entry, idx) => (
                <div key={entry.key}>
                  {entry.dividerBefore && idx !== 0 && <div className="my-1 h-[3px] bg-muted" />}
                  <button
                    type="button"
                    className={cn(
                      'flex w-full items-center gap-3 px-4 min-h-[44px] text-left',
                      'active:bg-muted transition-colors',
                      entry.disabled && 'opacity-50 cursor-not-allowed',
                    )}
                    onClick={() => handleEntryClick(entry)}
                    disabled={entry.disabled}
                    data-testid={`mobile-action-sheet-${entry.key}`}
                  >
                    {entry.icon && (
                      <span className="flex size-5 shrink-0 items-center justify-center text-muted-foreground">
                        {entry.icon}
                      </span>
                    )}
                    <span className="flex-1 min-w-0">
                      <span className="block text-sm leading-tight truncate">{entry.label}</span>
                      {entry.description && (
                        <span className="block text-xs text-muted-foreground leading-tight truncate">
                          {entry.description}
                        </span>
                      )}
                    </span>
                    {(entry.meta || entry.submenu) && (
                      <span className="flex items-center gap-1 text-xs text-muted-foreground shrink-0 max-w-[45%]">
                        {entry.meta && <span className="truncate">{entry.meta}</span>}
                        {entry.submenu && <ChevronRight size={14} className="opacity-50" />}
                      </span>
                    )}
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* Sub pane */}
          {activeSub && (
            <div
              className={cn(
                'absolute inset-0 flex flex-col bg-background',
                'transition-transform duration-[260ms] ease-[cubic-bezier(0.32,0.72,0,1)]',
                subVisible ? 'translate-x-0' : 'translate-x-full',
              )}
              aria-hidden={!subVisible}
            >
              {/* Sub header */}
              <div className="flex items-center shrink-0 border-b border-border px-2 py-2">
                <button
                  type="button"
                  className="flex items-center gap-0.5 px-2 py-1 text-sm text-primary"
                  onClick={handleBack}
                >
                  <ChevronLeft size={16} />
                  <span>{t('back', { defaultMessage: 'Back' })}</span>
                </button>
                <span className="flex-1 text-center text-sm font-semibold pr-12">{activeSub.title}</span>
              </div>
              {/* Sub options */}
              <div className="flex-1 min-h-0 overflow-y-auto py-1">
                {activeSub.options.length === 0 ? (
                  <div className="py-6 text-center text-sm text-muted-foreground">
                    {activeSub.emptyText ?? t('noOptions', { defaultMessage: 'No options available' })}
                  </div>
                ) : (
                  activeSub.options.map((option) => {
                    const showRadio = activeSub.selectable !== false;
                    return (
                      <button
                        key={option.key}
                        type="button"
                        className="flex w-full items-center gap-3 px-4 min-h-[44px] text-left active:bg-muted transition-colors"
                        onClick={() => handleSubSelect(option.key)}
                        data-testid={`mobile-action-sheet-option-${option.key}`}
                      >
                        <span className="flex-1 min-w-0">
                          <span className="block text-sm leading-tight truncate">{option.label}</span>
                          {option.description && (
                            <span className="block text-xs text-muted-foreground leading-tight truncate">
                              {option.description}
                            </span>
                          )}
                        </span>
                        {showRadio && (
                          <span
                            className={cn(
                              'size-3.5 shrink-0 rounded-full border-[1.5px] ml-auto',
                              option.active
                                ? 'border-primary bg-primary shadow-[inset_0_0_0_2px_var(--background)]'
                                : 'border-muted-foreground/40',
                            )}
                          />
                        )}
                      </button>
                    );
                  })
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </>,
    document.body,
  );
}
