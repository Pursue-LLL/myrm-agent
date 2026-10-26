/** @vitest-environment jsdom */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { chooseAction, confirmAction, promptText } from '@/lib/app-dialog';
import { useAppDialogStore } from '@/store/useAppDialogStore';
import en from '../../../../../locales/en.json';
import AppDialogHost from '../app-dialog-host';

const messages: Record<string, Record<string, unknown>> = { appDialog: en.appDialog, common: en.common };

/** One stable translator per namespace, resolving keys against the shipped English messages: a missing key fails. */
const translators = Object.fromEntries(
  Object.entries(messages).map(([namespace, bundle]) => [
    namespace,
    (key: string) => (typeof bundle[key] === 'string' ? (bundle[key] as string) : `MISSING ${namespace}.${key}`),
  ]),
);
vi.mock('next-intl', () => ({ useTranslations: (namespace: string) => translators[namespace] }));

/** Starts a request the way application code does, outside any React event. */
function ask<T>(start: () => Promise<T>): Promise<T> {
  let request!: Promise<T>;
  act(() => {
    request = start();
  });
  return request;
}

const isPending = async (request: Promise<unknown>): Promise<boolean> => {
  const marker = Symbol('pending');
  return (await Promise.race([request, new Promise((resolve) => setTimeout(() => resolve(marker), 30))])) === marker;
};

const dialogGone = () => waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull());

describe('AppDialogHost', () => {
  beforeEach(() => {
    useAppDialogStore.setState({ current: null, open: false, queue: [] });
  });

  it('renders nothing until a request arrives', () => {
    render(<AppDialogHost />);

    expect(screen.queryByRole('alertdialog')).toBeNull();
  });

  describe('confirmation', () => {
    it('asks in the user language by default and confirms with the primary button', async () => {
      render(<AppDialogHost />);

      const request = ask(() => confirmAction({ variant: 'destructive', description: 'Delete the file?' }));

      const dialog = await screen.findByRole('alertdialog');
      expect(dialog).toHaveTextContent(en.appDialog.titleDestructive);
      expect(dialog).toHaveTextContent('Delete the file?');
      fireEvent.click(within(dialog).getByRole('button', { name: en.common.confirm }));

      await expect(request).resolves.toBe(true);
      await dialogGone();
    });

    it.each(['warning', 'info'] as const)('titles a %s question "%s"', async (variant) => {
      render(<AppDialogHost />);

      void ask(() => confirmAction({ variant, description: 'Go on?' }));

      expect(await screen.findByRole('alertdialog')).toHaveTextContent(en.appDialog.titleConfirm);
    });

    it('uses the words the caller gives instead of the defaults', async () => {
      render(<AppDialogHost />);

      void ask(() =>
        confirmAction({
          variant: 'destructive',
          title: 'Remove skill',
          description: 'Remove it?',
          confirmText: 'Remove',
          cancelText: 'Keep it',
        }),
      );

      const dialog = await screen.findByRole('alertdialog');
      expect(dialog).toHaveTextContent('Remove skill');
      expect(within(dialog).getByRole('button', { name: 'Remove' })).toBeInTheDocument();
      expect(within(dialog).getByRole('button', { name: 'Keep it' })).toBeInTheDocument();
      expect(dialog).not.toHaveTextContent(en.appDialog.titleDestructive);
    });

    it('does not confirm when the user cancels', async () => {
      render(<AppDialogHost />);
      const request = ask(() => confirmAction({ variant: 'warning', description: 'Go on?' }));

      fireEvent.click(await screen.findByRole('button', { name: en.common.cancel }));

      await expect(request).resolves.toBe(false);
      await dialogGone();
    });

    it('does not confirm when the user presses Escape', async () => {
      render(<AppDialogHost />);
      const request = ask(() => confirmAction({ variant: 'destructive', description: 'Delete it?' }));
      await screen.findByRole('alertdialog');

      fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape' });

      await expect(request).resolves.toBe(false);
      await dialogGone();
    });

    it('stays above the workbench drawer and the modals built on it', async () => {
      render(<AppDialogHost />);

      void ask(() => confirmAction({ variant: 'warning', description: 'Go on?' }));

      const dialog = await screen.findByRole('alertdialog');
      expect(dialog).toHaveClass('z-[10010]');
      // The dialog and its backdrop are the only things on that layer.
      expect(document.querySelectorAll('.z-\\[10010\\]')).toHaveLength(2);
    });

    it('gives focus back to the button that started the action', async () => {
      render(
        <>
          <button type="button">Delete</button>
          <AppDialogHost />
        </>,
      );
      const opener = screen.getByRole('button', { name: 'Delete' });
      opener.focus();

      void ask(() => confirmAction({ variant: 'destructive', description: 'Delete it?' }));
      fireEvent.click(await screen.findByRole('button', { name: en.common.cancel }));

      await waitFor(() => expect(opener).toHaveFocus());
    });
  });

  describe('text prompt', () => {
    it('puts the cursor in the field with the initial text selected', async () => {
      render(<AppDialogHost />);

      void ask(() => promptText({ description: 'Name?', initialValue: 'draft' }));

      const field = await screen.findByRole('textbox');
      await waitFor(() => expect(field).toHaveFocus());
      expect(field).toHaveValue('draft');
      expect((field as HTMLInputElement).selectionStart).toBe(0);
      expect((field as HTMLInputElement).selectionEnd).toBe('draft'.length);
      expect(screen.getByRole('alertdialog')).toHaveTextContent(en.appDialog.titlePrompt);
    });

    it('hands over the typed text when the user confirms', async () => {
      const user = userEvent.setup();
      render(<AppDialogHost />);
      const request = ask(() => promptText({ description: 'Name?' }));

      await user.type(await screen.findByRole('textbox'), 'mem-42');
      await user.click(screen.getByRole('button', { name: en.common.confirm }));

      await expect(request).resolves.toBe('mem-42');
      await dialogGone();
    });

    it('submits with Enter', async () => {
      const user = userEvent.setup();
      render(<AppDialogHost />);
      const request = ask(() => promptText({ description: 'Name?' }));

      await user.type(await screen.findByRole('textbox'), 'mem-42{Enter}');

      await expect(request).resolves.toBe('mem-42');
    });

    it('does not accept an empty or blank answer', async () => {
      const user = userEvent.setup();
      render(<AppDialogHost />);
      const request = ask(() => promptText({ description: 'Name?' }));
      const field = await screen.findByRole('textbox');
      const confirm = screen.getByRole('button', { name: en.common.confirm });

      expect(confirm).toBeDisabled();
      await user.type(field, '   {Enter}');
      expect(confirm).toBeDisabled();
      expect(await isPending(request)).toBe(true);

      await user.type(field, 'x');
      expect(confirm).toBeEnabled();
    });

    it.each([
      ['cancels', () => fireEvent.click(screen.getByRole('button', { name: en.common.cancel }))],
      ['presses Escape', () => fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape' })],
    ])('hands over nothing when the user %s', async (_label, dismiss) => {
      const user = userEvent.setup();
      render(<AppDialogHost />);
      const request = ask(() => promptText({ description: 'Name?' }));
      await user.type(await screen.findByRole('textbox'), 'half typed');

      dismiss();

      await expect(request).resolves.toBeNull();
      await dialogGone();
    });

    it("uses the caller's words and placeholder", async () => {
      render(<AppDialogHost />);

      void ask(() =>
        promptText({ title: 'Merge', description: 'Target memory ID', placeholder: 'mem-…', confirmText: 'Merge' }),
      );

      const dialog = await screen.findByRole('alertdialog');
      expect(dialog).toHaveTextContent('Merge');
      expect(within(dialog).getByPlaceholderText('mem-…')).toBeInTheDocument();
      expect(within(dialog).getByRole('button', { name: 'Merge' })).toBeInTheDocument();
    });
  });

  describe('choice', () => {
    const choices = [
      { value: 'keep', label: 'Keep agent' },
      { value: 'delete', label: 'Delete agent too', tone: 'destructive' },
    ] as const;

    it('lists Cancel first, then the choices in the order given', async () => {
      render(<AppDialogHost />);

      void ask(() => chooseAction({ variant: 'destructive', description: 'Also delete the agent?', choices }));

      const dialog = await screen.findByRole('alertdialog');
      expect(
        within(dialog)
          .getAllByRole('button')
          .map((button) => button.textContent),
      ).toEqual([en.common.cancel, 'Keep agent', 'Delete agent too']);
      expect(dialog).toHaveTextContent(en.appDialog.titleDestructive);
    });

    it('styles a destructive choice as destructive and a neutral one as secondary', async () => {
      render(<AppDialogHost />);

      void ask(() => chooseAction({ variant: 'destructive', description: 'Also delete the agent?', choices }));

      await screen.findByRole('alertdialog');
      expect(screen.getByRole('button', { name: 'Delete agent too' })).toHaveClass('bg-destructive');
      expect(screen.getByRole('button', { name: 'Keep agent' })).not.toHaveClass('bg-destructive');
    });

    it('resolves the value of the clicked choice', async () => {
      render(<AppDialogHost />);
      const request = ask(() => chooseAction({ variant: 'destructive', description: 'Also delete?', choices }));

      fireEvent.click(await screen.findByRole('button', { name: 'Delete agent too' }));

      await expect(request).resolves.toBe('delete');
      await dialogGone();
    });

    it.each([
      ['cancels', () => fireEvent.click(screen.getByRole('button', { name: en.common.cancel }))],
      ['presses Escape', () => fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape' })],
    ])('chooses nothing when the user %s', async (_label, dismiss) => {
      render(<AppDialogHost />);
      const request = ask(() => chooseAction({ variant: 'destructive', description: 'Also delete?', choices }));
      await screen.findByRole('alertdialog');

      dismiss();

      await expect(request).resolves.toBeNull();
    });

    it('starts on the safe button, Cancel', async () => {
      render(<AppDialogHost />);

      void ask(() => chooseAction({ variant: 'destructive', description: 'Also delete?', choices }));

      const cancel = await screen.findByRole('button', { name: en.common.cancel });
      await waitFor(() => expect(cancel).toHaveFocus());
    });
  });

  describe('several requests', () => {
    it('shows them one after another, each answered by its own dialog', async () => {
      render(<AppDialogHost />);
      const first = ask(() => confirmAction({ variant: 'warning', description: 'First question' }));
      const second = ask(() => confirmAction({ variant: 'destructive', description: 'Second question' }));

      const firstDialog = await screen.findByRole('alertdialog');
      expect(firstDialog).toHaveTextContent('First question');
      expect(screen.queryByText('Second question')).toBeNull();

      fireEvent.click(within(firstDialog).getByRole('button', { name: en.common.confirm }));
      await expect(first).resolves.toBe(true);

      await waitFor(() => expect(screen.getByRole('alertdialog')).toHaveTextContent('Second question'));
      // The first dialog reporting that it closed must not answer the second question.
      expect(await isPending(second)).toBe(true);

      fireEvent.click(screen.getByRole('button', { name: en.common.cancel }));
      await expect(second).resolves.toBe(false);
    });

    it('starts every prompt empty, whatever was typed into the one before', async () => {
      const user = userEvent.setup();
      render(<AppDialogHost />);
      const first = ask(() => promptText({ description: 'First name?' }));
      const second = ask(() => promptText({ description: 'Second name?' }));

      await user.type(await screen.findByRole('textbox'), 'abc');
      await user.click(screen.getByRole('button', { name: en.common.confirm }));
      await expect(first).resolves.toBe('abc');

      await waitFor(() => expect(screen.getByRole('alertdialog')).toHaveTextContent('Second name?'));
      expect(screen.getByRole('textbox')).toHaveValue('');
      expect(await isPending(second)).toBe(true);
    });
  });
});
