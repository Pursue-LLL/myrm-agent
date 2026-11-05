'use client';

/**
 * [INPUT]
 * - ./ComposerOptionsToggle::ComposerOptionsToggle (POS: the button that opens the options region)
 * - @/components/features/message-input-actions/{SearchModeSelector,BaseModelSelector} (POS: the pickers every message uses)
 * - ../thinking-permission::PermissionModeTierSwitcher (POS: permission tier)
 *
 * [OUTPUT]
 * - ComposerPrimaryControls: the desktop composer's always-visible controls.
 *
 * [POS]
 * Five controls and no more: the options toggle, the Fast/Agent switch, the model, the permission tier and the editor
 * expander. Every other option lives in ComposerOptionsRegion, so a new option goes there, not here. The row never
 * scrolls sideways: the model name is the only part that shortens when the composer is narrow, so every other
 * control keeps its width (a squeezed permission pill wraps its label onto two lines). Phones render their own "+"
 * and action sheet instead.
 */

import { Maximize2, Minimize2 } from 'lucide-react';
import { useTranslations } from 'next-intl';

import BaseModelSelector from '@/components/features/message-input-actions/BaseModelSelector';
import SearchModeSelector from '@/components/features/message-input-actions/SearchModeSelector';
import type { ActionMode } from '@/store/chat/types';

import { PermissionModeTierSwitcher } from '../thinking-permission';
import { ComposerOptionsToggle } from './ComposerOptionsToggle';

interface ComposerPrimaryControlsProps {
  optionsExpanded: boolean;
  optionsRegionId: string;
  onToggleOptions: () => void;
  actionMode: ActionMode;
  setActionMode: (mode: ActionMode) => void;
  editorExpanded: boolean;
  onToggleEditor: () => void;
}

export function ComposerPrimaryControls({
  optionsExpanded,
  optionsRegionId,
  onToggleOptions,
  actionMode,
  setActionMode,
  editorExpanded,
  onToggleEditor,
}: ComposerPrimaryControlsProps) {
  const t = useTranslations('chat.input');
  const editorLabel = t(editorExpanded ? 'collapseEditor' : 'expandEditor');

  return (
    <div
      data-testid="composer-primary-controls"
      className="hidden sm:flex min-w-0 flex-row flex-nowrap items-center gap-2"
    >
      <ComposerOptionsToggle expanded={optionsExpanded} onToggle={onToggleOptions} controlsId={optionsRegionId} />
      <SearchModeSelector actionMode={actionMode} setActionMode={setActionMode} />
      <BaseModelSelector />
      <PermissionModeTierSwitcher className="shrink-0" />
      <button
        type="button"
        data-testid="composer-editor-toggle"
        onClick={onToggleEditor}
        className="flex size-7 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
        aria-label={editorLabel}
        title={editorLabel}
      >
        {editorExpanded ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
      </button>
    </div>
  );
}
