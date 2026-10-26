/**
 * Awaitable confirm / prompt / choose dialogs rendered by the app itself.
 *
 * [INPUT]
 * - @/store/useAppDialogStore (POS: queue behind the dialogs, shown by AppDialogHost)
 *
 * [OUTPUT]
 * - confirmAction: yes / no question; resolves `true` only when the user confirms
 * - promptText: asks for a line of text; resolves the text, or `null` when dismissed
 * - chooseAction: several labelled outcomes plus cancel; resolves the chosen `value`, or `null` when dismissed
 *
 * [POS]
 * Replacement for `window.confirm` / `prompt` / `alert`, which the Tauri dialog plugin turns into an async shim whose
 * Promise is truthy (every destructive guard would pass) and which browsers may suppress. Callable from components and
 * plain modules alike. Texts arrive already localized; the host words only what is left out (title, default buttons).
 * Dismissing (Escape, Cancel) never confirms, so a guard written as `if (!(await confirmAction(...))) return` is safe.
 */

import { useAppDialogStore, type AppDialogVariant, type ChoiceTone } from '@/store/useAppDialogStore';

interface DialogTextOptions {
  /** The question or explanation shown under the title. */
  description: string;
  /** Defaults to a generic title that fits the variant. */
  title?: string;
  /** Defaults to the localized "Cancel". */
  cancelText?: string;
}

export interface ConfirmOptions extends DialogTextOptions {
  /** `destructive` for deleting or discarding, `warning` for replacing or overriding, `info` for permissions. */
  variant: AppDialogVariant;
  /** Defaults to the localized "Confirm"; name the action instead ("Delete") when the question allows. */
  confirmText?: string;
}

export interface PromptOptions extends DialogTextOptions {
  initialValue?: string;
  placeholder?: string;
  /** Defaults to the localized "Confirm". */
  confirmText?: string;
}

export interface ChoiceOption<T extends string> {
  value: T;
  label: string;
  /** `primary` is the recommended outcome; `destructive` throws something away. Defaults to `neutral`. */
  tone?: ChoiceTone;
}

export interface ChooseOptions<T extends string> extends DialogTextOptions {
  choices: readonly ChoiceOption<T>[];
  variant?: AppDialogVariant;
}

export function confirmAction(options: ConfirmOptions): Promise<boolean> {
  return new Promise((resolve) => {
    useAppDialogStore.getState().enqueue({ kind: 'confirm', ...options }, (answer) => resolve(answer === true));
  });
}

export function promptText({ initialValue = '', ...options }: PromptOptions): Promise<string | null> {
  return new Promise((resolve) => {
    useAppDialogStore
      .getState()
      .enqueue({ kind: 'prompt', initialValue, ...options }, (answer) =>
        resolve(typeof answer === 'string' ? answer : null),
      );
  });
}

export function chooseAction<T extends string>({
  choices,
  variant = 'warning',
  ...options
}: ChooseOptions<T>): Promise<T | null> {
  return new Promise((resolve) => {
    useAppDialogStore.getState().enqueue(
      {
        kind: 'choose',
        variant,
        choices: choices.map(({ value, label, tone = 'neutral' }) => ({ value, label, tone })),
        ...options,
      },
      // Resolved from the caller's own list, so only a value the caller offered can come back.
      (answer) => resolve(choices.find((choice) => choice.value === answer)?.value ?? null),
    );
  });
}
