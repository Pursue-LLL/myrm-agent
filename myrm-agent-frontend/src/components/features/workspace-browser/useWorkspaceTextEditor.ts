'use client';

/**
 * Editing state of one workspace text file: what was read, what is being typed, and how a save ended.
 *
 * [INPUT]
 * - workspace / path: the file being edited; a different file starts a fresh visit
 * - enabled: false for files that are never edited as text (rich media), which are then not read here
 * - @/services/workspaceText (POS: versioned read, save against that version, save as copy)
 * - @/store/useWorkspaceDraftStore (POS: unsaved text kept between visits to a file)
 *
 * [OUTPUT]
 * - useWorkspaceTextEditor: `phase`, the last read `snapshot`, the `draft`, `dirty`, `restored`, `saving`,
 *   `conflict`, and the actions `setDraft` / `save` / `overwrite` / `saveCopy` / `reload` / `discard`; save
 *   outcomes are reported with localized toasts, never with the server's wording
 *
 * [POS]
 * Logic behind WorkspaceFilePreview. A save is always made against the version that was read. When the file
 * changed on disk meanwhile (the agent, a terminal, another editor) the draft is kept untouched and `conflict` is
 * raised; the user then loads the latest, overwrites it on purpose, or keeps their text as a copy. Text typed
 * while a save is in flight stays in the draft and counts as unsaved. State belongs to one file: nothing read,
 * typed or answered for another file is ever shown or applied to this one.
 * Unsaved text is kept in the draft store for exactly as long as it differs from the file, so leaving the file, the
 * drawer or the chat does not lose it: the next visit starts from that text (`restored`), laid over the version it
 * was typed against, and raises `conflict` at once when the file has moved on since.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import {
  readWorkspaceText,
  saveWorkspaceText,
  saveWorkspaceTextCopy,
  WorkspaceTextError,
  type WorkspaceTextFailureReason,
  type WorkspaceTextSnapshot,
} from '@/services/workspaceText';
import { keptDraft, useWorkspaceDraftStore, type WorkspaceDraft } from '@/store/useWorkspaceDraftStore';

interface ReadyState {
  phase: 'ready';
  /** What the file held when it was last read or saved. */
  snapshot: WorkspaceTextSnapshot;
  draft: string;
  saving: boolean;
  /** The version the file has on disk now, once the file was found to have changed under the draft. */
  conflictVersion: string | null;
  /** The draft came back from an earlier visit; it stops being news with the first edit. */
  restored: boolean;
}

type EditorState = { phase: 'idle' } | { phase: 'loading' } | { phase: 'failed' } | ReadyState;

/** State tagged with the file it belongs to, so a render for another file can never see it. */
type KeyedState = EditorState & { key: string };

/** Localized wording (keys under `workspace`) for a refusal; unlisted reasons get the action's own default. */
const FAILURE_COPY: Partial<Record<WorkspaceTextFailureReason, string>> = {
  write_blocked: 'saveBlocked',
  not_found: 'saveGone',
  not_a_file: 'saveGone',
  invalid_content: 'saveInvalidContent',
  content_too_large: 'saveTooLarge',
};

/**
 * Where a visit starts: the file as it was read, or, when unsaved text was kept from an earlier visit, that text
 * over the version it was typed against. `latest` is null when the file cannot be read now; the text still comes
 * back, and a save then says what is wrong. Null when there is nothing to show.
 */
function opening(
  latest: WorkspaceTextSnapshot | null,
  kept: WorkspaceDraft | undefined,
): Pick<ReadyState, 'snapshot' | 'draft' | 'conflictVersion' | 'restored'> | null {
  if (kept && kept.text !== latest?.content) {
    return {
      snapshot: kept.base,
      draft: kept.text,
      // The file moved on since the text was typed, so saving it needs a decision first.
      conflictVersion: latest && latest.version !== kept.base.version ? latest.version : null,
      restored: true,
    };
  }
  return latest && { snapshot: latest, draft: latest.content, conflictVersion: null, restored: false };
}

export interface WorkspaceTextEditor {
  phase: EditorState['phase'];
  snapshot: WorkspaceTextSnapshot | null;
  draft: string;
  /** The typed text differs from what the file holds. */
  dirty: boolean;
  /** The draft was brought back from an earlier visit to the file rather than typed in this one. */
  restored: boolean;
  saving: boolean;
  /** The file changed on disk since it was read, so saving needs a decision. */
  conflict: boolean;
  setDraft: (value: string) => void;
  /** Resolves true when the file holds the draft afterwards, which includes there being nothing to save. */
  save: () => Promise<boolean>;
  /** Saves over the newer version found on disk; only meaningful while `conflict` is true. */
  overwrite: () => Promise<void>;
  /** Writes the typed text to a new file next to the original. */
  saveCopy: () => Promise<void>;
  /** Reads the file again, dropping whatever was typed. */
  reload: () => Promise<void>;
  /** Drops what was typed and goes back to what the file holds; a file known to have changed is read again. */
  discard: () => void;
}

export function useWorkspaceTextEditor(workspace: string, path: string, enabled: boolean): WorkspaceTextEditor {
  const t = useTranslations('workspace');
  const key = `${workspace}\0${path}`;
  const [stored, setStored] = useState<KeyedState>({ key, phase: enabled ? 'loading' : 'idle' });
  // Bumped whenever the file or its session changes, so a slow answer for the old one is recognised and dropped.
  const session = useRef(0);
  // Session whose save or copy is running. Read synchronously, so a second key press handled by a closure that has
  // not re-rendered yet is refused instead of racing the first write (which would then see a conflict with itself).
  const writing = useRef<number | null>(null);

  const state: EditorState = stored.key === key ? stored : { phase: enabled ? 'loading' : 'idle' };
  const ready = state.phase === 'ready' ? state : null;

  const updateReady = useCallback(
    (update: (current: ReadyState) => ReadyState) => {
      setStored((current) =>
        current.key === key && current.phase === 'ready' ? { ...update(current), key } : current,
      );
    },
    [key],
  );

  const load = useCallback(async () => {
    const mine = ++session.current;
    setStored({ key, phase: 'loading' });
    let latest: WorkspaceTextSnapshot | null = null;
    try {
      latest = await readWorkspaceText(workspace, path);
    } catch {
      // The server's reason names paths and system errors; the reader only needs to know the file did not open.
    }
    if (mine !== session.current) {
      return;
    }
    const start = opening(latest, keptDraft(workspace, path));
    setStored(start ? { key, phase: 'ready', saving: false, ...start } : { key, phase: 'failed' });
  }, [key, workspace, path]);

  useEffect(() => {
    if (!enabled) {
      session.current += 1;
      setStored({ key, phase: 'idle' });
      return;
    }
    void load();
    return () => {
      session.current += 1;
    };
  }, [enabled, key, load]);

  const snapshotNow = ready?.snapshot;
  const draftNow = ready?.draft;
  // Unsaved text outlives this editor: it is kept for the next visit for exactly as long as it differs from the file.
  useEffect(() => {
    if (snapshotNow === undefined || draftNow === undefined) {
      return;
    }
    const drafts = useWorkspaceDraftStore.getState();
    if (draftNow === snapshotNow.content) {
      drafts.drop(workspace, path);
    } else {
      drafts.keep(workspace, path, snapshotNow, draftNow);
    }
  }, [workspace, path, snapshotNow, draftNow]);

  const failureCopy = useCallback(
    (error: unknown, fallback: string) =>
      t((error instanceof WorkspaceTextError && FAILURE_COPY[error.reason]) || fallback),
    [t],
  );

  const saveAgainst = useCallback(
    async (baseVersion: string): Promise<boolean> => {
      const mine = session.current;
      if (!ready || writing.current === mine) {
        return false;
      }
      writing.current = mine;
      const savedText = ready.draft;
      updateReady((current) => ({ ...current, saving: true }));
      try {
        const written = await saveWorkspaceText(workspace, path, savedText, baseVersion);
        toast.success(t('saveSuccess'));
        // Settled at once: the editor may be gone before it renders again, and nothing else would forget the draft.
        useWorkspaceDraftStore.getState().saved(workspace, path, savedText, written);
        if (mine === session.current) {
          updateReady((current) => ({
            ...current,
            snapshot: { ...current.snapshot, content: savedText, version: written.version, size: written.size },
            saving: false,
            conflictVersion: null,
            restored: false,
          }));
        }
        return true;
      } catch (error) {
        const stillOpen = mine === session.current;
        if (
          stillOpen &&
          error instanceof WorkspaceTextError &&
          error.reason === 'version_conflict' &&
          error.currentVersion
        ) {
          const conflictVersion = error.currentVersion;
          updateReady((current) => ({ ...current, saving: false, conflictVersion }));
          return false;
        }
        if (stillOpen) {
          updateReady((current) => ({ ...current, saving: false }));
        }
        // Said even when the user already left the file: the text did not reach the disk.
        toast.error(failureCopy(error, 'saveFailed'));
        return false;
      } finally {
        if (writing.current === mine) {
          writing.current = null;
        }
      }
    },
    [ready, workspace, path, updateReady, failureCopy, t],
  );

  const save = useCallback(async (): Promise<boolean> => {
    if (!ready?.snapshot.editable) {
      return false;
    }
    return ready.draft === ready.snapshot.content ? true : saveAgainst(ready.snapshot.version);
  }, [ready, saveAgainst]);

  const overwrite = useCallback(async () => {
    // An empty version (the file can no longer be versioned) is sent as it is: the server refuses it, so the text
    // can never replace a file that cannot be edited here.
    if (ready?.conflictVersion != null) {
      await saveAgainst(ready.conflictVersion);
    }
  }, [ready, saveAgainst]);

  const saveCopy = useCallback(async () => {
    const mine = session.current;
    if (!ready || writing.current === mine) {
      return;
    }
    writing.current = mine;
    updateReady((current) => ({ ...current, saving: true }));
    try {
      const written = await saveWorkspaceTextCopy(workspace, path, ready.draft);
      toast.success(t('saveCopySuccess', { name: written.name }));
    } catch (error) {
      toast.error(failureCopy(error, 'saveCopyFailed'));
    } finally {
      if (writing.current === mine) {
        writing.current = null;
      }
      if (mine === session.current) {
        updateReady((current) => ({ ...current, saving: false }));
      }
    }
  }, [ready, workspace, path, updateReady, failureCopy, t]);

  const setDraft = useCallback(
    (value: string) => updateReady((current) => ({ ...current, draft: value, restored: false })),
    [updateReady],
  );

  const reload = useCallback(async () => {
    // Reading again is how the user lets go of their text, so the kept copy must not come back with it.
    useWorkspaceDraftStore.getState().drop(workspace, path);
    await load();
  }, [workspace, path, load]);

  const conflictVersion = ready?.conflictVersion;
  const discard = useCallback(() => {
    // Forgotten at once: the preview may unmount in this same batch, before an effect could forget the kept copy.
    useWorkspaceDraftStore.getState().drop(workspace, path);
    if (conflictVersion != null) {
      // What was read is out of date, so going back to it would show a file that no longer exists.
      void load();
      return;
    }
    updateReady((current) => ({ ...current, draft: current.snapshot.content, restored: false }));
  }, [conflictVersion, workspace, path, load, updateReady]);

  return {
    phase: state.phase,
    snapshot: ready?.snapshot ?? null,
    draft: ready?.draft ?? '',
    dirty: ready !== null && ready.draft !== ready.snapshot.content,
    restored: ready?.restored ?? false,
    saving: ready?.saving ?? false,
    conflict: ready?.conflictVersion != null,
    setDraft,
    save,
    overwrite,
    saveCopy,
    reload,
    discard,
  };
}
