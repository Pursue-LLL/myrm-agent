'use client';

/**
 * [INPUT]
 * @/services/chat::regenerateLastTurn (POS: Chat API service layer)
 * @/lib/utils/imeUtils::isImeComposing (POS: IME composition guard for Enter-to-submit)
 *
 * [OUTPUT]
 * RegenerateMenu: Dropdown button with regenerate options (Try Again, More Concise, More Detailed, Custom).
 * `onRegenerate` resolves whether the regeneration went through; a custom instruction that was refused stays in its
 * box, open for editing, instead of being lost with the closed menu.
 *
 * [POS]
 * Regenerate action surface: a plain retry plus style presets and a custom instruction.
 */

import { useState, useRef, useEffect } from 'react';
import { RefreshCw, ChevronDown, AlignLeft, AlignJustify, MessageSquarePlus } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { isImeComposing } from '@/lib/utils/imeUtils';

interface RegenerateMenuProps {
  onRegenerate: (instruction?: string) => Promise<boolean>;
}

export default function RegenerateMenu({ onRegenerate }: RegenerateMenuProps) {
  const [open, setOpen] = useState(false);
  const [customMode, setCustomMode] = useState(false);
  const [customPrompt, setCustomPrompt] = useState('');
  const [loading, setLoading] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const t = useTranslations('chat');

  useEffect(() => {
    if (customMode && inputRef.current) {
      inputRef.current.focus();
    }
  }, [customMode]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
        setCustomMode(false);
      }
    };
    if (open) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [open]);

  const handleClick = async (instruction?: string): Promise<boolean> => {
    setLoading(true);
    setOpen(false);
    setCustomMode(false);
    try {
      return await onRegenerate(instruction);
    } finally {
      setLoading(false);
    }
  };

  const handlePreset = (instruction?: string) => {
    if (!loading) {
      void handleClick(instruction);
    }
  };

  const handleCustomSubmit = async () => {
    const instruction = customPrompt.trim();
    if (!instruction || loading) {
      return;
    }
    if (await handleClick(instruction)) {
      setCustomPrompt('');
      return;
    }
    // Refused: the text is still what the user wrote, so the box comes back with it.
    setOpen(true);
    setCustomMode(true);
  };

  // `instruction` is prompt text for the model, not UI copy: it stays English
  // so one preset sends the same prompt in every UI language.
  const presets = [
    { icon: RefreshCw, labelKey: 'regenerate_try_again' as const, instruction: undefined },
    { icon: AlignLeft, labelKey: 'regenerate_concise' as const, instruction: 'Be more concise and to the point' },
    {
      icon: AlignJustify,
      labelKey: 'regenerate_detailed' as const,
      instruction: 'Provide more detail and explanation',
    },
    { icon: MessageSquarePlus, labelKey: 'regenerate_creative' as const, instruction: 'Be more creative and engaging' },
  ];

  return (
    <div ref={menuRef} className="relative inline-flex">
      <div className="inline-flex items-center rounded-xl overflow-hidden">
        <button
          onClick={() => handlePreset()}
          disabled={loading}
          className="p-2 text-black/70 dark:text-white/70 hover:bg-secondary dark:hover:bg-secondary transition duration-200 hover:text-black dark:hover:text-white disabled:opacity-50"
          title={t('regenerate')}
          data-testid="message-regenerate-button"
        >
          <RefreshCw size={18} className={loading ? 'animate-spin' : ''} />
        </button>
        <button
          onClick={() => setOpen(!open)}
          className="p-1 pr-1.5 text-black/70 dark:text-white/70 hover:bg-secondary dark:hover:bg-secondary transition duration-200 hover:text-black dark:hover:text-white"
          aria-label={t('regenerate_options')}
        >
          <ChevronDown size={12} />
        </button>
      </div>

      {open && (
        <div className="absolute bottom-full left-0 mb-1 w-56 bg-popover border border-border rounded-lg shadow-lg z-50 overflow-hidden">
          {!customMode ? (
            <>
              {presets.map(({ icon: Icon, labelKey, instruction }) => (
                <button
                  key={labelKey}
                  onClick={() => handlePreset(instruction)}
                  className="flex items-center gap-2.5 w-full px-3 py-2 text-sm text-left hover:bg-accent transition-colors"
                >
                  <Icon className="w-4 h-4 shrink-0 text-muted-foreground" />
                  <span>{t(labelKey)}</span>
                </button>
              ))}
              <div className="border-t border-border" />
              <button
                onClick={() => setCustomMode(true)}
                className="flex items-center gap-2.5 w-full px-3 py-2 text-sm text-left hover:bg-accent transition-colors"
              >
                <MessageSquarePlus className="w-4 h-4 shrink-0 text-muted-foreground" />
                <span>{t('regenerate_custom')}</span>
              </button>
            </>
          ) : (
            <div className="p-2">
              <input
                ref={inputRef}
                value={customPrompt}
                onChange={(e) => setCustomPrompt(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !isImeComposing(e)) {
                    void handleCustomSubmit();
                  }
                }}
                placeholder={t('regenerate_custom_placeholder')}
                className="w-full px-2.5 py-1.5 text-sm bg-background border border-input rounded-full focus:outline-none focus:ring-1 focus:ring-ring"
              />
              <button
                onClick={() => void handleCustomSubmit()}
                disabled={!customPrompt.trim()}
                className="mt-1.5 w-full px-2.5 py-1.5 text-sm bg-primary text-primary-foreground rounded-full hover:bg-primary/90 disabled:opacity-50 transition-colors"
              >
                {t('regenerate_submit')}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
