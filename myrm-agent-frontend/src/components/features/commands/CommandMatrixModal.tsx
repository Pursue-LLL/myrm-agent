/**
 * [INPUT]
 * - onSelectCommand: Optional callback when a command is selected to insert into prompt
 * - useCommandMatrixStore: Zustand store for commands, search, category, active modal state
 * - next-intl: useTranslations
 * - lucide-react icons
 *
 * [OUTPUT]
 * - CommandMatrixModal: Interactive system capability matrix dialog ("Mousepad View")
 *
 * [POS]
 * Client-side UI component for Item 38 P0. Strictly under 350 lines. Zero `any`. Zero native emojis.
 */

import React, { useEffect, useMemo, useRef } from 'react';
import { useTranslations } from 'next-intl';
import {
  Activity,
  Bookmark,
  CheckCircle2,
  Code,
  Compass,
  CornerDownLeft,
  FileCheck,
  Lock,
  Search,
  Sparkles,
  X,
  Zap,
} from 'lucide-react';
import { useCommandMatrixStore } from './useCommandMatrixStore';
import type { CommandCategory, CommandMatrixEntry } from './commandMatrixTypes';

export interface CommandMatrixModalProps {
  onSelectCommand?: (entry: CommandMatrixEntry) => void;
}

const CATEGORY_ICONS: Record<CommandCategory | 'all', React.ComponentType<{ className?: string }>> = {
  all: Compass,
  concurrency_collaboration: Zap,
  data_science: Code,
  security_credential: Lock,
  memory_knowledge: Bookmark,
  delivery_workflow: FileCheck,
};

export const CommandMatrixModal: React.FC<CommandMatrixModalProps> = ({ onSelectCommand }) => {
  const t = useTranslations('commandMatrix');
  const dialogRef = useRef<HTMLDialogElement | null>(null);
  const searchInputRef = useRef<HTMLInputElement | null>(null);

  const isModalOpen = useCommandMatrixStore((s) => s.isModalOpen);
  const closeModal = useCommandMatrixStore((s) => s.closeModal);
  const toggleModal = useCommandMatrixStore((s) => s.toggleModal);
  const searchQuery = useCommandMatrixStore((s) => s.searchQuery);
  const setSearchQuery = useCommandMatrixStore((s) => s.setSearchQuery);
  const selectedCategory = useCommandMatrixStore((s) => s.selectedCategory);
  const setSelectedCategory = useCommandMatrixStore((s) => s.setSelectedCategory);
  const commands = useCommandMatrixStore((s) => s.commands);
  const fetchCatalog = useCommandMatrixStore((s) => s.fetchCatalog);
  const selectedIndex = useCommandMatrixStore((s) => s.selectedIndex);
  const setSelectedIndex = useCommandMatrixStore((s) => s.setSelectedIndex);
  const markCommandMastered = useCommandMatrixStore((s) => s.markCommandMastered);

  // Global Cmd/Ctrl + / hotkey listener
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === '/') {
        e.preventDefault();
        toggleModal();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [toggleModal]);

  // Initial catalog load on mount
  useEffect(() => {
    if (isModalOpen && commands.length === 0) {
      void fetchCatalog();
    }
  }, [isModalOpen, commands.length, fetchCatalog]);

  // Auto-focus search input upon opening
  useEffect(() => {
    if (isModalOpen) {
      setTimeout(() => {
        if (searchInputRef.current) {
          searchInputRef.current.focus();
        }
      }, 50);
    }
  }, [isModalOpen]);

  // Filter commands
  const filteredCommands = useMemo(() => {
    return commands.filter((cmd) => {
      const matchCategory = selectedCategory === 'all' || cmd.category === selectedCategory;
      if (!matchCategory) {
        return false;
      }

      if (!searchQuery.trim()) {
        return true;
      }

      const q = searchQuery.toLowerCase().trim();
      return (
        cmd.command.toLowerCase().includes(q) ||
        cmd.title_zh.toLowerCase().includes(q) ||
        cmd.title_en.toLowerCase().includes(q) ||
        cmd.description_zh.toLowerCase().includes(q) ||
        cmd.description_en.toLowerCase().includes(q) ||
        cmd.tags.some((t) => t.toLowerCase().includes(q))
      );
    });
  }, [commands, selectedCategory, searchQuery]);

  // Keyboard navigation within modal
  const handleListKeyDown = (e: React.KeyboardEvent) => {
    if (filteredCommands.length === 0) {
      return;
    }

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      const next = (selectedIndex + 1) % filteredCommands.length;
      setSelectedIndex(next);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      const prev = (selectedIndex - 1 + filteredCommands.length) % filteredCommands.length;
      setSelectedIndex(prev);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const active = filteredCommands[selectedIndex];
      if (active) {
        handleSelect(active);
      }
    } else if (e.key === 'Escape') {
      e.preventDefault();
      closeModal();
    }
  };

  const handleSelect = (entry: CommandMatrixEntry) => {
    markCommandMastered(entry.command);
    if (onSelectCommand) {
      onSelectCommand(entry);
    }
    closeModal();
  };

  if (!isModalOpen) {
    return null;
  }

  const categories: Array<{ id: CommandCategory | 'all'; label: string }> = [
    { id: 'all', label: t('allCategories') },
    { id: 'concurrency_collaboration', label: t('concurrency_collaboration') },
    { id: 'data_science', label: t('data_science') },
    { id: 'security_credential', label: t('security_credential') },
    { id: 'memory_knowledge', label: t('memory_knowledge') },
    { id: 'delivery_workflow', label: t('delivery_workflow') },
  ];

  return (
    <dialog
      ref={dialogRef}
      open
      aria-label={t('title')}
      onKeyDown={handleListKeyDown}
      className="fixed inset-0 z-50 flex items-center justify-center w-full h-full bg-black/50 backdrop-blur-xs p-4 overflow-y-auto block"
    >
      <div className="relative w-full max-w-2xl bg-background rounded-2xl border border-border shadow-2xl overflow-hidden flex flex-col max-h-[85vh] animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border/60 bg-muted/20">
          <div className="flex items-center gap-2.5">
            <div className="p-1.5 rounded-lg bg-primary/10 text-primary">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-foreground tracking-tight">
                {t('title')}
              </h2>
              <p className="text-xs text-muted-foreground">{t('subtitle')}</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="hidden sm:inline-flex px-2 py-0.5 text-[10px] font-mono text-muted-foreground bg-muted rounded border border-border/50">
              {t('shortcutHint')}
            </span>
            <button
              type="button"
              onClick={closeModal}
              className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted/60 rounded-lg transition-colors cursor-pointer"
              aria-label={t('close')}
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Search Input Bar */}
        <div className="p-3 border-b border-border/40 bg-background/50">
          <div className="relative flex items-center">
            <Search className="absolute left-3 w-4 h-4 text-muted-foreground" />
            <input
              ref={searchInputRef}
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t('searchPlaceholder')}
              className="w-full pl-9 pr-4 py-2 bg-muted/40 border border-border/60 rounded-xl text-xs text-foreground placeholder:text-muted-foreground focus:outline-hidden focus:ring-1 focus:ring-primary focus:border-primary transition-all"
            />
          </div>

          {/* Category Tabs */}
          <div className="flex items-center gap-1.5 overflow-x-auto no-scrollbar pt-2.5 pb-0.5">
            {categories.map((cat) => {
              const Icon = CATEGORY_ICONS[cat.id];
              const isSelected = selectedCategory === cat.id;
              return (
                <button
                  key={cat.id}
                  type="button"
                  onClick={() => setSelectedCategory(cat.id)}
                  className={`flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-medium rounded-lg whitespace-nowrap transition-all cursor-pointer ${
                    isSelected
                      ? 'bg-primary text-primary-foreground shadow-xs'
                      : 'bg-muted/40 text-muted-foreground hover:text-foreground hover:bg-muted'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  <span>{cat.label}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Command Matrix List */}
        <div className="flex-1 overflow-y-auto p-3 space-y-1.5">
          {filteredCommands.length === 0 ? (
            <div className="py-12 text-center text-muted-foreground text-xs">
              <Activity className="w-8 h-8 mx-auto mb-2 opacity-40" />
              <span>{t('noCommandsFound')}</span>
            </div>
          ) : (
            filteredCommands.map((item, index) => {
              const isHighlighted = index === selectedIndex;
              return (
                <button
                  type="button"
                  key={item.command}
                  onClick={() => handleSelect(item)}
                  onMouseEnter={() => setSelectedIndex(index)}
                  className={`w-full text-left group flex items-start justify-between p-3 rounded-xl border transition-all duration-150 cursor-pointer ${
                    isHighlighted
                      ? 'bg-primary/5 border-primary/40 shadow-xs'
                      : 'bg-card/50 border-border/40 hover:bg-muted/40'
                  }`}
                >
                  <div className="flex items-start gap-3 min-w-0">
                    <div
                      className={`p-1.5 rounded-lg text-xs font-mono font-bold flex-shrink-0 mt-0.5 ${
                        isHighlighted
                          ? 'bg-primary text-primary-foreground'
                          : 'bg-muted text-foreground'
                      }`}
                    >
                      {item.command}
                    </div>

                    <div className="min-w-0 space-y-0.5">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-semibold text-foreground truncate">
                          {item.title_zh}
                        </span>
                        <span className="text-[11px] text-muted-foreground truncate">
                          {item.title_en}
                        </span>
                        {item.requires_running_task && (
                          <span className="px-1.5 py-0.2 bg-amber-500/10 text-amber-500 text-[10px] rounded border border-amber-500/20">
                            {t('runningTaskOnly')}
                          </span>
                        )}
                      </div>

                      <p className="text-[11px] text-muted-foreground leading-relaxed line-clamp-2">
                        {item.description_zh}
                      </p>

                      <div className="flex items-center gap-1.5 pt-1">
                        {item.tags.map((tag) => (
                          <span
                            key={tag}
                            className="px-1.5 py-0.2 bg-muted/60 text-muted-foreground text-[10px] rounded font-mono"
                          >
                            #{tag}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 flex-shrink-0 pl-3">
                    {item.shortcut && (
                      <kbd className="px-1.5 py-0.5 text-[10px] font-mono bg-muted text-muted-foreground rounded border border-border/60">
                        {item.shortcut}
                      </kbd>
                    )}
                    <div
                      className={`p-1 rounded-md transition-opacity ${
                        isHighlighted
                          ? 'opacity-100 text-primary'
                          : 'opacity-0 group-hover:opacity-100 text-muted-foreground'
                      }`}
                    >
                      <CornerDownLeft className="w-3.5 h-3.5" />
                    </div>
                  </div>
                </button>
              );
            })
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-4 py-2.5 border-t border-border/50 bg-muted/10 text-[11px] text-muted-foreground">
          <div className="flex items-center gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
            <span>{t('clickToInsert')}</span>
          </div>
          <span>
            {filteredCommands.length} / {commands.length}
          </span>
        </div>
      </div>
    </dialog>
  );
};
