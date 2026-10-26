'use client';

/**
 * Renders the dialogs requested through `@/lib/app-dialog`, one at a time.
 *
 * [INPUT]
 * - @/store/useAppDialogStore (POS: the request on screen and the ones waiting behind it)
 * - ./confirm-dialog (POS: the confirmation itself)
 * - ./app-dialog-views (POS: prompt and choice dialogs)
 * - next-intl (POS: default title and button words in the user's language)
 *
 * [OUTPUT]
 * - AppDialogHost: global host, mounted once in the root layout beside the other root-level modals
 *
 * [POS]
 * Every request is keyed by its id so a new request starts from a fresh dialog (typed text never carries over), and
 * each dialog answers through the id it was created for: a dialog still animating out can never answer the request
 * that replaced it.
 */

import { useTranslations } from 'next-intl';

import { useAppDialogStore, type AppDialogVariant } from '@/store/useAppDialogStore';

import { ChoiceView, PromptView, APP_DIALOG_LAYER } from './app-dialog-views';
import { ConfirmDialog } from './confirm-dialog';

export default function AppDialogHost() {
  const t = useTranslations('appDialog');
  const tCommon = useTranslations('common');
  const current = useAppDialogStore((state) => state.current);
  const open = useAppDialogStore((state) => state.open);
  const settle = useAppDialogStore((state) => state.settle);

  if (!current) {
    return null;
  }

  const { id, spec } = current;
  const answer = (value: boolean | string | null) => settle(id, value);
  const dismiss = (isOpen: boolean) => {
    if (!isOpen) {
      answer(null);
    }
  };
  const cancelText = spec.cancelText ?? tCommon('cancel');
  const titleFor = (variant: AppDialogVariant) =>
    variant === 'destructive' ? t('titleDestructive') : t('titleConfirm');

  switch (spec.kind) {
    case 'confirm':
      return (
        <ConfirmDialog
          key={id}
          open={open}
          variant={spec.variant}
          title={spec.title ?? titleFor(spec.variant)}
          description={spec.description}
          confirmText={spec.confirmText ?? tCommon('confirm')}
          cancelText={cancelText}
          onConfirm={() => answer(true)}
          onOpenChange={dismiss}
          className={APP_DIALOG_LAYER}
          overlayClassName={APP_DIALOG_LAYER}
        />
      );
    case 'prompt':
      return (
        <PromptView
          key={id}
          spec={spec}
          open={open}
          title={spec.title ?? t('titlePrompt')}
          confirmText={spec.confirmText ?? tCommon('confirm')}
          cancelText={cancelText}
          onAnswer={answer}
        />
      );
    case 'choose':
      return (
        <ChoiceView
          key={id}
          spec={spec}
          open={open}
          title={spec.title ?? titleFor(spec.variant)}
          cancelText={cancelText}
          onAnswer={answer}
        />
      );
  }
}
