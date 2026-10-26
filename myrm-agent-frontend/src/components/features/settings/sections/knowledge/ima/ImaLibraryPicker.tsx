'use client';

/**
 * [INPUT]
 * @/services/wiki/ima::listImaLibraries (POS: the account's knowledge bases)
 * ./imaCopy::imaErrorKey (POS: server error code → locale key)
 *
 * [OUTPUT]
 * ImaLibraryPicker: choose which knowledge bases (and whether notes) to import, then start or re-run the sync
 *
 * [POS]
 * Second screen of the ima card, also reopened from "change selection". Libraries are read live from ima so the list is
 * always the account's own; the server drops any id it does not recognise, so a stale tick can never import a stranger's data.
 */

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { Checkbox } from '@/components/primitives/checkbox';
import { Label } from '@/components/primitives/label';
import { Skeleton } from '@/components/primitives/skeleton';
import { Switch } from '@/components/primitives/switch';
import { listImaLibraries, type ImaLibrary, type ImaSelectionInput } from '@/services/wiki/ima';
import { imaErrorKey } from './imaCopy';

interface ImaLibraryPickerProps {
  /** Libraries already chosen when the picker reopens; empty on first run. */
  initialSelected: readonly ImaLibrary[];
  initialIncludeNotes: boolean;
  busy: boolean;
  /** Present while editing an existing sync, so the user can back out without changing anything. */
  onCancel?: () => void;
  /** Locale key (relative to `settings.wiki.ima`) of the last failure. */
  errorKey: string | null;
  onSubmit: (selection: ImaSelectionInput) => Promise<void>;
}

type LibraryState =
  { kind: 'loading' } | { kind: 'ready'; libraries: ImaLibrary[] } | { kind: 'failed'; errorKey: string };

export default function ImaLibraryPicker({
  initialSelected,
  initialIncludeNotes,
  busy,
  onCancel,
  errorKey,
  onSubmit,
}: ImaLibraryPickerProps) {
  const t = useTranslations('settings.wiki.ima');
  const [state, setState] = useState<LibraryState>({ kind: 'loading' });
  const [selectedIds, setSelectedIds] = useState<ReadonlySet<string>>(
    () => new Set(initialSelected.map((kb) => kb.id)),
  );
  const [includeNotes, setIncludeNotes] = useState(initialIncludeNotes);

  const load = useCallback(async () => {
    setState({ kind: 'loading' });
    try {
      setState({ kind: 'ready', libraries: await listImaLibraries() });
    } catch (error) {
      setState({ kind: 'failed', errorKey: imaErrorKey(error) });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const toggle = (id: string, checked: boolean) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (checked) {
        next.add(id);
      } else {
        next.delete(id);
      }
      return next;
    });
  };

  const libraries = state.kind === 'ready' ? state.libraries : [];
  // Only ids ima still lists count; a library deleted since the last run must not keep the button enabled.
  const chosenIds = libraries.filter((library) => selectedIds.has(library.id)).map((library) => library.id);
  const canSubmit = !busy && state.kind === 'ready' && (chosenIds.length > 0 || includeNotes);

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t('libraries.hint')}</p>

      {state.kind === 'loading' ? (
        <div className="space-y-2" aria-busy="true" aria-label={t('libraries.loading')}>
          <Skeleton className="h-10" />
          <Skeleton className="h-10" />
          <Skeleton className="h-10" />
        </div>
      ) : null}

      {state.kind === 'failed' ? (
        <div className="space-y-2">
          <p role="alert" className="text-sm text-destructive">
            {t(state.errorKey)}
          </p>
          <Button type="button" size="sm" variant="outline" onClick={() => void load()}>
            {t('libraries.reload')}
          </Button>
        </div>
      ) : null}

      {state.kind === 'ready' && libraries.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('libraries.empty')}</p>
      ) : null}

      {libraries.length > 0 ? (
        <ul className="max-h-64 space-y-1 overflow-y-auto rounded-lg border border-border/60 p-1">
          {libraries.map((library) => (
            <li key={library.id}>
              <Label
                htmlFor={`ima-library-${library.id}`}
                className="flex cursor-pointer items-center gap-3 rounded-md px-3 py-2.5 font-normal hover:bg-accent"
              >
                <Checkbox
                  id={`ima-library-${library.id}`}
                  checked={selectedIds.has(library.id)}
                  onCheckedChange={(checked) => toggle(library.id, checked === true)}
                />
                <span className="min-w-0 flex-1 truncate">{library.name}</span>
              </Label>
            </li>
          ))}
        </ul>
      ) : null}

      <div className="flex items-center justify-between gap-3 rounded-lg border border-border/60 px-3 py-2.5">
        <div className="space-y-0.5">
          <Label htmlFor="ima-include-notes">{t('libraries.notesLabel')}</Label>
          <p className="text-xs text-muted-foreground">{t('libraries.notesHint')}</p>
        </div>
        <Switch id="ima-include-notes" checked={includeNotes} onCheckedChange={setIncludeNotes} />
      </div>
      <p className="text-xs text-muted-foreground">{t('libraries.supported')}</p>

      {errorKey ? (
        <p role="alert" className="text-sm text-destructive">
          {t(errorKey)}
        </p>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          size="sm"
          disabled={!canSubmit}
          onClick={() => void onSubmit({ library_ids: chosenIds, include_notes: includeNotes })}
        >
          {busy ? t('libraries.starting') : onCancel ? t('libraries.apply') : t('libraries.start')}
        </Button>
        {onCancel ? (
          <Button type="button" size="sm" variant="ghost" disabled={busy} onClick={onCancel}>
            {t('common.cancel')}
          </Button>
        ) : null}
        <p className="basis-full text-xs text-muted-foreground sm:basis-auto">{t('libraries.costHint')}</p>
      </div>
    </div>
  );
}
