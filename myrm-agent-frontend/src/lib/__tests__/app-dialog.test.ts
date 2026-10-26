import { beforeEach, describe, expect, it } from 'vitest';

import { useAppDialogStore } from '@/store/useAppDialogStore';
import { chooseAction, confirmAction, promptText } from '../app-dialog';

const state = () => useAppDialogStore.getState();

/** The request the user is looking at, with the spec exactly as the host receives it. */
const showing = () => {
  const current = state().current;
  if (!current || !state().open) {
    throw new Error('no dialog is showing');
  }
  return current;
};

const answer = (value: boolean | string | null) => state().settle(showing().id, value);

const isPending = async (promise: Promise<unknown>): Promise<boolean> => {
  const marker = Symbol('pending');
  return (await Promise.race([promise, Promise.resolve(marker)])) === marker;
};

describe('app dialogs', () => {
  beforeEach(() => {
    useAppDialogStore.setState({ current: null, open: false, queue: [] });
  });

  describe('confirmAction', () => {
    it('asks with the given words and waits for the user', async () => {
      const result = confirmAction({
        variant: 'destructive',
        description: 'Delete this file?',
        title: 'Delete',
        confirmText: 'Delete file',
        cancelText: 'Keep',
      });

      expect(showing().spec).toEqual({
        kind: 'confirm',
        variant: 'destructive',
        description: 'Delete this file?',
        title: 'Delete',
        confirmText: 'Delete file',
        cancelText: 'Keep',
      });
      expect(await isPending(result)).toBe(true);

      answer(true);
      await expect(result).resolves.toBe(true);
    });

    it.each([
      ['declined', false],
      ['dismissed', null],
      ['a value no confirmation produces', 'yes'],
    ])('does not confirm when the answer is %s', async (_label, value) => {
      const result = confirmAction({ variant: 'warning', description: 'Go on?' });

      answer(value);

      await expect(result).resolves.toBe(false);
    });
  });

  describe('promptText', () => {
    it('starts from the initial value, empty by default', () => {
      void promptText({ description: 'Name?' });
      expect(showing().spec).toMatchObject({ kind: 'prompt', initialValue: '' });
      answer(null);

      void promptText({ description: 'Name?', initialValue: 'draft', placeholder: 'e.g. notes' });
      expect(showing().spec).toMatchObject({ initialValue: 'draft', placeholder: 'e.g. notes' });
    });

    it('resolves the typed text exactly as the user left it', async () => {
      const result = promptText({ description: 'Name?' });

      answer('  notes ');

      await expect(result).resolves.toBe('  notes ');
    });

    it.each([
      ['dismissed', null],
      ['a confirmation', true],
    ])('resolves null when the answer is %s', async (_label, value) => {
      const result = promptText({ description: 'Name?' });

      answer(value);

      await expect(result).resolves.toBeNull();
    });
  });

  describe('chooseAction', () => {
    const choices = [
      { value: 'save', label: 'Save', tone: 'primary' },
      { value: 'discard', label: 'Discard' },
    ] as const;

    it('offers the choices in order, neutral unless told otherwise, as a warning by default', () => {
      void chooseAction({ description: 'Unsaved changes', choices });

      expect(showing().spec).toMatchObject({
        kind: 'choose',
        variant: 'warning',
        choices: [
          { value: 'save', label: 'Save', tone: 'primary' },
          { value: 'discard', label: 'Discard', tone: 'neutral' },
        ],
      });
    });

    it('resolves the value of the chosen option', async () => {
      const result = chooseAction({ description: 'Unsaved changes', choices });

      answer('discard');

      await expect(result).resolves.toBe('discard');
    });

    it.each([
      ['dismissed', null],
      ['a value that was not offered', 'delete-everything'],
      ['a confirmation', true],
    ])('resolves null when the answer is %s', async (_label, value) => {
      const result = chooseAction({ description: 'Unsaved changes', choices });

      answer(value);

      await expect(result).resolves.toBeNull();
    });
  });

  it('asks one question at a time, in the order they were raised', async () => {
    const first = confirmAction({ variant: 'info', description: 'First?' });
    const second = promptText({ description: 'Second?' });

    expect(showing().spec).toMatchObject({ kind: 'confirm' });
    expect(await isPending(second)).toBe(true);

    answer(true);
    await expect(first).resolves.toBe(true);
    expect(showing().spec).toMatchObject({ kind: 'prompt' });

    answer('typed');
    await expect(second).resolves.toBe('typed');
  });
});
