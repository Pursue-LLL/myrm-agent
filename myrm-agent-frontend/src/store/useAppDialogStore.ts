/**
 * [INPUT]
 * - zustand::create (POS: lightweight state)
 *
 * [OUTPUT]
 * - useAppDialogStore: the dialog on screen, the ones waiting behind it, and the `enqueue` / `settle` actions
 * - AppDialogSpec / ConfirmSpec / PromptSpec / ChooseSpec: what a request asks for
 * - AppDialogAnswer / PendingAppDialog: what answers a request, and a request waiting for its answer
 *
 * [POS]
 * State behind `@/lib/app-dialog`, shown by `AppDialogHost`. Requests are shown one at a time in arrival order.
 * An answer settles exactly the dialog it belongs to, so a dialog that is still animating out can never answer the
 * request that replaced it.
 */
'use client';

import { create } from 'zustand';

export type AppDialogVariant = 'destructive' | 'warning' | 'info';
export type ChoiceTone = 'primary' | 'destructive' | 'neutral';

interface DialogText {
  /** The question or explanation shown under the title. */
  description: string;
  /** Left to the host, which words it for the user's language. */
  title?: string;
  cancelText?: string;
}

export interface ConfirmSpec extends DialogText {
  kind: 'confirm';
  variant: AppDialogVariant;
  confirmText?: string;
}

export interface PromptSpec extends DialogText {
  kind: 'prompt';
  initialValue: string;
  placeholder?: string;
  confirmText?: string;
}

export interface ChoiceSpec {
  value: string;
  label: string;
  tone: ChoiceTone;
}

export interface ChooseSpec extends DialogText {
  kind: 'choose';
  variant: AppDialogVariant;
  choices: readonly ChoiceSpec[];
}

export type AppDialogSpec = ConfirmSpec | PromptSpec | ChooseSpec;

/** `true` / `false` for a confirmation, the typed text or the chosen value, `null` when dismissed. */
export type AppDialogAnswer = boolean | string | null;

export interface PendingAppDialog {
  id: number;
  spec: AppDialogSpec;
  resolve: (answer: AppDialogAnswer) => void;
}

interface AppDialogState {
  /** Kept after closing so the dialog finishes its exit animation with the same content. */
  current: PendingAppDialog | null;
  open: boolean;
  queue: readonly PendingAppDialog[];
  /** Shows the request right away, or behind the dialogs already waiting. */
  enqueue: (spec: AppDialogSpec, resolve: (answer: AppDialogAnswer) => void) => void;
  /** Answers the dialog with this `id`; an answer for a dialog that is no longer the open one is ignored. */
  settle: (id: number, answer: AppDialogAnswer) => void;
}

let lastId = 0;

export const useAppDialogStore = create<AppDialogState>((set, get) => ({
  current: null,
  open: false,
  queue: [],

  enqueue: (spec, resolve) => {
    const dialog: PendingAppDialog = { id: ++lastId, spec, resolve };
    set((state) => (state.open ? { queue: [...state.queue, dialog] } : { current: dialog, open: true }));
  },

  settle: (id, answer) => {
    const { current, open, queue } = get();
    if (!open || current?.id !== id) {
      return;
    }
    const [next, ...rest] = queue;
    set(next ? { current: next, queue: rest } : { open: false });
    current.resolve(answer);
  },
}));
