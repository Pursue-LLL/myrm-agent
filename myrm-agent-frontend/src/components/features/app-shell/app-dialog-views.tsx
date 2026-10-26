'use client';

/**
 * Prompt and choice dialogs of the app dialog host; confirmations reuse ConfirmDialog.
 *
 * [INPUT]
 * - @/store/useAppDialogStore (POS: shape of a prompt / choose request)
 * - ./confirm-dialog (POS: heading and action styling shared with every confirmation)
 * - ./useFocusReturn (POS: hands focus back to what started the action)
 *
 * [OUTPUT]
 * - APP_DIALOG_LAYER: classes lifting a dialog and its backdrop above the workbench drawer and floating panels
 * - PromptView: one line of text; Enter submits, Confirm stays disabled while the text is blank
 * - ChoiceView: Cancel plus one button per choice, in the order given
 *
 * [POS]
 * Presentational half of `AppDialogHost`. Texts arrive worded for the user; the views only lay them out and report
 * the outcome through `onAnswer`.
 */

import { useRef, useState } from 'react';

import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogFooter,
} from '@/components/primitives/alert-dialog';
import { Button, type ButtonProps } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { cn } from '@/lib/utils/classnameUtils';
import type { ChooseSpec, ChoiceTone, PromptSpec } from '@/store/useAppDialogStore';

import { ConfirmDialogHeading } from './confirm-dialog';
import { useFocusReturn } from './useFocusReturn';

/** Above the workbench drawer (z-9970) and every modal built on it (up to z-10000). */
export const APP_DIALOG_LAYER = 'z-[10010]';

interface ViewTexts {
  title: string;
  cancelText: string;
}

interface PromptViewProps extends ViewTexts {
  spec: PromptSpec;
  confirmText: string;
  open: boolean;
  /** The typed text, or `null` when dismissed. */
  onAnswer: (answer: string | null) => void;
}

export function PromptView({ spec, title, confirmText, cancelText, open, onAnswer }: PromptViewProps) {
  const [value, setValue] = useState(spec.initialValue);
  const inputRef = useRef<HTMLInputElement>(null);
  const handleCloseAutoFocus = useFocusReturn(open);
  const canSubmit = value.trim() !== '';

  return (
    <AlertDialog open={open} onOpenChange={(next) => !next && onAnswer(null)}>
      <AlertDialogContent
        className={cn('sm:max-w-[425px]', APP_DIALOG_LAYER)}
        overlayClassName={APP_DIALOG_LAYER}
        // The only thing to do here is type, so the field gets focus instead of Cancel.
        onOpenAutoFocus={(event) => {
          event.preventDefault();
          inputRef.current?.focus();
          inputRef.current?.select();
        }}
        onCloseAutoFocus={handleCloseAutoFocus}
      >
        <form
          className="grid gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            if (canSubmit) {
              onAnswer(value);
            }
          }}
        >
          <ConfirmDialogHeading variant="info" title={title} description={spec.description} />
          <Input
            ref={inputRef}
            value={value}
            placeholder={spec.placeholder}
            aria-label={title}
            autoComplete="off"
            spellCheck={false}
            onChange={(event) => setValue(event.target.value)}
          />
          <AlertDialogFooter>
            <AlertDialogCancel>{cancelText}</AlertDialogCancel>
            <Button type="submit" disabled={!canSubmit}>
              {confirmText}
            </Button>
          </AlertDialogFooter>
        </form>
      </AlertDialogContent>
    </AlertDialog>
  );
}

const CHOICE_BUTTON_VARIANT: Record<ChoiceTone, ButtonProps['variant']> = {
  primary: 'default',
  destructive: 'destructive',
  neutral: 'outline',
};

interface ChoiceViewProps extends ViewTexts {
  spec: ChooseSpec;
  open: boolean;
  /** The `value` of the chosen option, or `null` when dismissed. */
  onAnswer: (answer: string | null) => void;
}

export function ChoiceView({ spec, title, cancelText, open, onAnswer }: ChoiceViewProps) {
  const handleCloseAutoFocus = useFocusReturn(open);

  return (
    <AlertDialog open={open} onOpenChange={(next) => !next && onAnswer(null)}>
      <AlertDialogContent
        className={cn('sm:max-w-[425px]', APP_DIALOG_LAYER)}
        overlayClassName={APP_DIALOG_LAYER}
        onCloseAutoFocus={handleCloseAutoFocus}
      >
        <ConfirmDialogHeading variant={spec.variant} title={title} description={spec.description} />
        {/* Cancel plus every option can be wider than the dialog in some languages, so the row wraps. */}
        <AlertDialogFooter className="sm:flex-wrap sm:gap-2 sm:space-x-0">
          <AlertDialogCancel>{cancelText}</AlertDialogCancel>
          {spec.choices.map((choice) => (
            <Button
              key={choice.value}
              type="button"
              variant={CHOICE_BUTTON_VARIANT[choice.tone]}
              onClick={() => onAnswer(choice.value)}
            >
              {choice.label}
            </Button>
          ))}
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
