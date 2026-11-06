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
      <button
        type="button"
        onClick={onOpenSheet}
        className="flex size-7 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground hover:bg-muted-foreground/20 transition-colors"
        aria-label={chatT('input.expandToolbar')}
        data-testid="sendbox-mobile-plus-btn"
      >
        <Plus size={16} />
      </button>
      <SearchModeSelector actionMode={actionMode} setActionMode={setActionMode} />
    </div>
  );
}
