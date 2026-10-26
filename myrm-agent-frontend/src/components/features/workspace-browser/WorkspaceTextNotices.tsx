'use client';

/**
 * Notices above the text of the workspace file preview: why a file is view-only, that unsaved text came back, and
 * what to do when the file changed on disk during an edit.
 *
 * [INPUT]
 * - reason: why the editor cannot change the file (not for binary files, which have no text to show)
 * - busy / onSaveCopy / onReload / onOverwrite: the choices once the file is found to have changed under the text
 * - useTranslations from next-intl (namespace: 'workspace')
 *
 * [OUTPUT]
 * - ReadonlyNotice: quiet banner stating the file is shown view-only and why
 * - DraftRestoredNotice: quiet banner stating that the text from an earlier visit is back
 * - ConflictNotice: alert banner with three choices; keeping the user's text as a copy is the highlighted one
 *
 * [POS]
 * Banners of WorkspaceFilePreview. They name outcomes and choices in plain words; the server's wording and
 * technical terms never appear here.
 */

import React from 'react';
import { ClockCounterClockwise, LockSimple, WarningCircle } from '@phosphor-icons/react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import type { WorkspaceTextReadonlyReason } from '@/services/workspaceText';

const READONLY_COPY: Record<Exclude<WorkspaceTextReadonlyReason, 'binary'>, string> = {
  not_utf8: 'readonlyNotUtf8',
  mixed_line_endings: 'readonlyMixedLineEndings',
  too_large: 'readonlyTooLarge',
};

export const ReadonlyNotice: React.FC<{ reason: Exclude<WorkspaceTextReadonlyReason, 'binary'> }> = ({ reason }) => {
  const t = useTranslations('workspace');
  return (
    <output
      data-testid="workspace-edit-readonly"
      className="mx-3 mb-2 flex items-start gap-2 rounded-lg border border-border/60 bg-muted/40 px-3 py-2"
    >
      <LockSimple aria-hidden weight="duotone" className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
      <span className="text-xs leading-relaxed text-muted-foreground">{t(READONLY_COPY[reason])}</span>
    </output>
  );
};

export const DraftRestoredNotice: React.FC = () => {
  const t = useTranslations('workspace');
  return (
    <output
      data-testid="workspace-edit-restored"
      className="mx-3 mb-2 flex items-start gap-2 rounded-lg bg-primary/10 px-3 py-2 ring-1 ring-inset ring-primary/30"
    >
      <ClockCounterClockwise aria-hidden weight="duotone" className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
      <span className="text-xs leading-relaxed text-foreground">{t('draftRestored')}</span>
    </output>
  );
};

type ChoiceTone = 'primary' | 'neutral' | 'danger';

// Coloured outlines are inset rings: the global `* { border-color }` rule is unlayered, so it wins over every
// `border-<color>` utility and a coloured border would render in the neutral border colour.
const CHOICE_TONES: Record<ChoiceTone, string> = {
  primary: 'bg-primary text-primary-foreground hover:bg-primary/90',
  neutral: 'bg-background text-foreground ring-1 ring-inset ring-border hover:bg-muted',
  // Destructive red is too dark to read as text on the dark page background, so only the outline carries it.
  danger: 'bg-background text-foreground ring-1 ring-inset ring-destructive/60 hover:bg-destructive/15',
};

const Choice: React.FC<{
  tone: ChoiceTone;
  disabled: boolean;
  onClick: () => void;
  children: React.ReactNode;
}> = ({ tone, disabled, onClick, children }) => (
  <button
    type="button"
    onClick={onClick}
    disabled={disabled}
    className={cn(
      'rounded-md px-2.5 py-1 text-xs font-medium transition-colors pointer-coarse:min-h-11',
      'focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring',
      'disabled:pointer-events-none disabled:opacity-50',
      CHOICE_TONES[tone],
    )}
  >
    {children}
  </button>
);

export const ConflictNotice: React.FC<{
  busy: boolean;
  onSaveCopy: () => void;
  onReload: () => void;
  onOverwrite: () => void;
}> = ({ busy, onSaveCopy, onReload, onOverwrite }) => {
  const t = useTranslations('workspace');
  return (
    <div
      role="alert"
      data-testid="workspace-edit-conflict"
      className="mx-3 mb-2 flex items-start gap-2.5 rounded-lg bg-warning/10 px-3 py-2.5 ring-1 ring-inset ring-warning/40"
    >
      <WarningCircle aria-hidden weight="fill" className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
      <div className="min-w-0 flex-1 space-y-2">
        <div className="space-y-0.5">
          <p className="text-xs font-medium text-foreground">{t('conflictTitle')}</p>
          <p className="text-xs leading-relaxed text-muted-foreground">{t('conflictBody')}</p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <Choice tone="primary" disabled={busy} onClick={onSaveCopy}>
            {t('conflictSaveCopy')}
          </Choice>
          <Choice tone="neutral" disabled={busy} onClick={onReload}>
            {t('conflictReload')}
          </Choice>
          <Choice tone="danger" disabled={busy} onClick={onOverwrite}>
            {t('conflictOverwrite')}
          </Choice>
        </div>
      </div>
    </div>
  );
};
