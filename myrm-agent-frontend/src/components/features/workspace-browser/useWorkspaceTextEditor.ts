'use client';

/**
 * Editing state of one workspace text file: what was read, what is being typed, and how a save ended.
 *
 * [INPUT]
 * - workspace / path: the file being edited; a different file starts a fresh session
 * - enabled: false for files that are never edited as text (rich media), which are then not read here
 * - @/services/workspaceText (POS: versioned read, save against that version, save as copy)
 *
 * [OUTPUT]
 * - useWorkspaceTextEditor: `phase`, the last read `snapshot`, the `draft`, `dirty`, `saving`, `conflict`, and the
 *   actions `setDraft` / `save` / `overwrite` / `saveCopy` / `reload` / `discard`; save outcomes are reported
 *   with localized toasts, never with the server's wording
 *
 * [POS]
 * Logic behind WorkspaceFilePreview. A save is always made against the version that was read. When the file
 * changed on disk meanwhile (the agent, a terminal, another editor) the draft is kept untouched and `conflict` is
 * raised; the user then loads the latest, overwrites it on purpose, or keeps their text as a copy. Text typed
 * while a save is in flight stays in the draft and counts as unsaved. State belongs to one file: nothing read,
 * typed or answered for another file is ever shown or applied to this one.
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

interface ReadyState {
  phase: 'ready';
  /** What the file held when it was last read or saved. */
  snapshot: WorkspaceTextSnapshot;
  draft: string;
  saving: boolean;
  /** The version the file has on disk now, once a save found it changed. */
  conflictVersion: string | null;
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

export interface WorkspaceTextEditor {
  phase: EditorState['phase'];
  snapshot: WorkspaceTextSnapshot | null;
  draft: string;
  /** The typed text differs from what the file holds. */
  dirty: boolean;
  saving: boolean;
  /** The file changed on disk since it was read, so saving needs a decision. */
  conflict: boolean;
  setDraft: (value: string) => void;
  save: () => Promise<void>;
  /** Saves over the newer version found on disk; only meaningful while `conflict` is true. */
  overwrite: () => Promise<void>;
  /** Writes the typed text to a new file next to the original. */
  saveCopy: () => Promise<void>;
  /** Reads the file again, dropping whatever was typed. */
  reload: () => Promise<void>;
  /** Drops what was typed and goes back to what the file holds. */
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
    try {
      const snapshot = await readWorkspaceText(workspace, path);
      if (mine === session.current) {
        setStored({ key, phase: 'ready', snapshot, draft: snapshot.content, saving: false, conflictVersion: null });
      }
    } catch {
      // The server's reason names paths and system errors; the reader only needs to know the file did not open.
      if (mine === session.current) {
        setStored({ key, phase: 'failed' });
      }
    }
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

  const failureCopy = useCallback(
    (error: unknown, fallback: string) =>
      t((error instanceof WorkspaceTextError && FAILURE_COPY[error.reason]) || fallback),
    [t],
  );

  const saveAgainst = useCallback(
    async (baseVersion: string) => {
      const mine = session.current;
      if (!ready || writing.current === mine) {
        return;
      }
      writing.current = mine;
      const savedText = ready.draft;
      updateReady((current) => ({ ...current, saving: true }));
      try {
        const written = await saveWorkspaceText(workspace, path, savedText, baseVersion);
        toast.success(t('saveSuccess'));
        if (mine === session.current) {
          updateReady((current) => ({
            ...current,
            snapshot: { ...current.snapshot, content: savedText, version: written.version, size: written.size },
            saving: false,
            conflictVersion: null,
          }));
        }
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
          return;
        }
        if (stillOpen) {
          updateReady((current) => ({ ...current, saving: false }));
        }
        // Said even when the user already left the file: the text did not reach the disk.
        toast.error(failureCopy(error, 'saveFailed'));
      } finally {
        if (writing.current === mine) {
          writing.current = null;
        }
      }
    },
    [ready, workspace, path, updateReady, failureCopy, t],
  );

  const save = useCallback(async () => {
    if (ready && ready.snapshot.editable && ready.draft !== ready.snapshot.content) {
      await saveAgainst(ready.snapshot.version);
    }
  }, [ready, saveAgainst]);

  const overwrite = useCallback(async () => {
    if (ready?.conflictVersion) {
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
    (value: string) => updateReady((current) => ({ ...current, draft: value })),
    [updateReady],
  );

  const discard = useCallback(
    () => updateReady((current) => ({ ...current, draft: current.snapshot.content, conflictVersion: null })),
    [updateReady],
  );

  return {
    phase: state.phase,
    snapshot: ready?.snapshot ?? null,
    draft: ready?.draft ?? '',
    dirty: ready !== null && ready.draft !== ready.snapshot.content,
    saving: ready?.saving ?? false,
    conflict: ready?.conflictVersion != null,
    setDraft,
    save,
    overwrite,
    saveCopy,
    reload: load,
    discard,
  };
}
