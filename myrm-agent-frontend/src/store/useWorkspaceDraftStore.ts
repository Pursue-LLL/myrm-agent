/**
 * [INPUT]
 * - zustand::create (POS: lightweight state)
 * - WorkspaceTextSnapshot, WorkspaceTextWritten from @/services/workspaceText (POS: what a file held when it was
 *   read, and what a save returned)
 *
 * [OUTPUT]
 * - useWorkspaceDraftStore: the unsaved text kept for each workspace file, with `keep` / `drop` / `saved`
 * - keptDraft: the draft kept for one file
 * - latestDraftIn: the draft of a workspace that was edited last
 * - WorkspaceDraft: unsaved text together with the file version it started from
 *
 * [POS]
 * Memory of workspace-file edits that outlives the editor showing them, so leaving a file, closing the drawer or
 * switching chats never costs the user their text. Memory only: a draft lasts as long as the page, and while any
 * exists the browser asks before the page is closed or reloaded. A draft is kept exactly while its text differs from
 * the file; saving, discarding or typing the file's text back forgets it.
 */
'use client';

import { create } from 'zustand';
import type { WorkspaceTextSnapshot, WorkspaceTextWritten } from '@/services/workspaceText';

export interface WorkspaceDraft {
  workspace: string;
  path: string;
  /** What the file held when the text last matched it: the version a save of this text is made against. */
  base: WorkspaceTextSnapshot;
  text: string;
  /** When the text last changed; the Files tab reopens the draft of its workspace that was edited last. */
  editedAt: number;
}

interface WorkspaceDraftState {
  drafts: Readonly<Record<string, WorkspaceDraft>>;
  /** Keeps `text` as unsaved against `base`; the same text and base again leave the store untouched. */
  keep: (workspace: string, path: string, base: WorkspaceTextSnapshot, text: string) => void;
  /** Forgets the draft of a file: it was saved, thrown away, or replaced by the file as it is now. */
  drop: (workspace: string, path: string) => void;
  /**
   * A save finished: the kept text is forgotten when it is what was written, and otherwise (typed on while the save
   * ran) continues from the written version, so its own save is not mistaken for someone else's change.
   */
  saved: (
    workspace: string,
    path: string,
    text: string,
    written: Pick<WorkspaceTextWritten, 'version' | 'size'>,
  ) => void;
}

const draftKey = (workspace: string, path: string): string => `${workspace}\0${path}`;

function withDraft(
  drafts: WorkspaceDraftState['drafts'],
  key: string,
  draft: WorkspaceDraft | null,
): WorkspaceDraftState['drafts'] {
  const others = Object.fromEntries(Object.entries(drafts).filter(([other]) => other !== key));
  return draft ? { ...others, [key]: draft } : others;
}

export const useWorkspaceDraftStore = create<WorkspaceDraftState>((set) => ({
  drafts: {},

  keep: (workspace, path, base, text) =>
    set((state) => {
      const kept = state.drafts[draftKey(workspace, path)];
      if (kept?.base === base && kept.text === text) {
        return state;
      }
      return {
        drafts: withDraft(state.drafts, draftKey(workspace, path), {
          workspace,
          path,
          base,
          text,
          editedAt: Date.now(),
        }),
      };
    }),

  drop: (workspace, path) =>
    set((state) =>
      draftKey(workspace, path) in state.drafts
        ? { drafts: withDraft(state.drafts, draftKey(workspace, path), null) }
        : state,
    ),

  saved: (workspace, path, text, written) =>
    set((state) => {
      const key = draftKey(workspace, path);
      const kept = state.drafts[key];
      if (!kept) {
        return state;
      }
      const base: WorkspaceTextSnapshot = { ...kept.base, content: text, version: written.version, size: written.size };
      return { drafts: withDraft(state.drafts, key, kept.text === text ? null : { ...kept, base }) };
    }),
}));

export function keptDraft(workspace: string, path: string): WorkspaceDraft | undefined {
  return useWorkspaceDraftStore.getState().drafts[draftKey(workspace, path)];
}

export function latestDraftIn(workspace: string): WorkspaceDraft | undefined {
  let latest: WorkspaceDraft | undefined;
  for (const draft of Object.values(useWorkspaceDraftStore.getState().drafts)) {
    if (draft.workspace === workspace && (!latest || draft.editedAt > latest.editedAt)) {
      latest = draft;
    }
  }
  return latest;
}

/** Closing or reloading the page would lose every kept draft. */
function warnBeforeLeaving(event: BeforeUnloadEvent): void {
  event.preventDefault();
  event.returnValue = '';
}

if (typeof window !== 'undefined') {
  let warning = false;
  useWorkspaceDraftStore.subscribe((state) => {
    const hasDrafts = Object.keys(state.drafts).length > 0;
    if (hasDrafts === warning) {
      return;
    }
    warning = hasDrafts;
    if (hasDrafts) {
      window.addEventListener('beforeunload', warnBeforeLeaving);
    } else {
      window.removeEventListener('beforeunload', warnBeforeLeaving);
    }
  });
}
