/** @vitest-environment jsdom */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { confirmAction } from '@/lib/app-dialog';
import { toast } from '@/lib/utils/toast';
import type { SlashCommand } from '@/types/command';
import { CommandSettings } from '../CommandSettings';

const deleteCommand = vi.fn();
const commands: SlashCommand[] = [
  {
    id: 'cmd-1',
    type: 'command',
    name: 'summarize',
    template: 'Summarize {{input}}',
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
  },
];

const translators = new Map<string, (key: string, values?: { name?: string }) => string>();
/** One stable translator per namespace, like next-intl's: components list it in effect dependencies. */
const translatorFor = (namespace: string) => {
  let translate = translators.get(namespace);
  if (!translate) {
    translate = (key, values) => (values?.name ? `${namespace}.${key}:${values.name}` : `${namespace}.${key}`);
    translators.set(namespace, translate);
  }
  return translate;
};
vi.mock('next-intl', () => ({ useTranslations: (namespace: string) => translatorFor(namespace) }));
vi.mock('@/store/useCommandStore', () => ({ useCommandStore: () => ({ commands, deleteCommand }) }));
vi.mock('@/lib/app-dialog', () => ({ confirmAction: vi.fn() }));
vi.mock('@/lib/utils/toast', () => ({ toast: { success: vi.fn() } }));
vi.mock('../CommandEditor', () => ({ CommandEditor: () => null }));

const settle = () =>
  act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });

/** The row's last button is the trash icon. */
const deleteButton = () => screen.getAllByRole('button').at(-1) as HTMLElement;

describe('CommandSettings delete', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('removes the command after the user confirms, naming it in the question', async () => {
    vi.mocked(confirmAction).mockResolvedValue(true);
    render(<CommandSettings />);

    fireEvent.click(deleteButton());

    await waitFor(() => expect(deleteCommand).toHaveBeenCalledExactlyOnceWith('cmd-1'));
    expect(confirmAction).toHaveBeenCalledExactlyOnceWith({
      variant: 'destructive',
      description: 'settings.commands.delete.confirm:summarize',
      confirmText: 'common.delete',
    });
    expect(toast.success).toHaveBeenCalledWith('settings.commands.delete.success');
  });

  it('keeps the command when the user declines', async () => {
    vi.mocked(confirmAction).mockResolvedValue(false);
    render(<CommandSettings />);

    fireEvent.click(deleteButton());
    await waitFor(() => expect(confirmAction).toHaveBeenCalledTimes(1));
    await settle();

    expect(deleteCommand).not.toHaveBeenCalled();
    expect(toast.success).not.toHaveBeenCalled();
  });
});
