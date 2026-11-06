'use client';

/**
 * [INPUT]
 * - @/components/features/message-input-actions/SearchModeSelector (POS: Fast / Agent 模式切换)
 *
 * [OUTPUT]
 * - MobileComposerEntry: 手机输入区左侧的「+」与模式切换。
 *
 * [POS]
 * 手机（<`sm`）上桌面主行与选项区都不显示，只留「+」打开操作表（MobileComposerSheet）和每条消息都要用的模式切换。
 */
import { Plus } from 'lucide-react';
import { useTranslations } from 'next-intl';

import SearchModeSelector from '@/components/features/message-input-actions/SearchModeSelector';
import type { ActionMode } from '@/store/chat/types';

interface MobileComposerEntryProps {
  actionMode: ActionMode;
  setActionMode: (mode: ActionMode) => void;
  onOpenSheet: () => void;
}

export function MobileComposerEntry({ actionMode, setActionMode, onOpenSheet }: MobileComposerEntryProps) {
  const chatT = useTranslations('chat');

  return (
    <div className="flex sm:hidden flex-row items-center gap-1 shrink-0">
      {/* The glyph stays 28px; the invisible `after:` box lifts the touch target to 44×44 on every side except the right, where the mode switch sits 6px away. */}
      <button
        type="button"
        onClick={onOpenSheet}
        className="relative flex size-7 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground hover:bg-muted-foreground/20 transition-colors after:absolute after:-inset-y-2 after:-left-3.5 after:-right-0.5"
        aria-label={chatT('input.expandToolbar')}
        data-testid="sendbox-mobile-plus-btn"
      >
        <Plus size={16} />
      </button>
      <SearchModeSelector actionMode={actionMode} setActionMode={setActionMode} />
    </div>
  );
}
