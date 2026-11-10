/** @vitest-environment jsdom */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { deferred } from '@/test-utils/deferred';

import { ConfirmDialog } from '../confirm-dialog';

describe('ConfirmDialog description', () => {
  it('breaks long unspaced user text instead of overflowing the dialog, and keeps explicit line breaks', async () => {
    const longTitle = 'x'.repeat(200);
    render(
      <ConfirmDialog
        open
        title="Delete this task?"
        description={`"${longTitle}"\nThis cannot be undone.`}
        confirmText="Delete"
        cancelText="Cancel"
        onConfirm={() => {}}
      />,
    );

    const description = await screen.findByText(/This cannot be undone\./);

    expect(description).toHaveTextContent(longTitle);
    expect(description).toHaveClass('wrap-anywhere', 'whitespace-pre-line');
  });
});

describe('ConfirmDialog opening', () => {
  const baseProps = {
    trigger: <button type="button">Open dialog</button>,
    title: 'Delete this task?',
    description: 'This cannot be undone.',
    confirmText: 'Delete',
    cancelText: 'Cancel',
  };
  const openFromTrigger = () => act(async () => fireEvent.click(screen.getByRole('button', { name: 'Open dialog' })));
  const dialogs = () => screen.queryAllByRole('alertdialog');

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('opens from its trigger and closes on cancel, telling the caller about the cancel once', async () => {
    const onCancel = vi.fn();
    const onOpenChange = vi.fn();
    render(<ConfirmDialog {...baseProps} onConfirm={vi.fn()} onCancel={onCancel} onOpenChange={onOpenChange} />);
    expect(dialogs()).toHaveLength(0);

    await openFromTrigger();
    expect(dialogs()).toHaveLength(1);
    await act(async () => fireEvent.click(screen.getByTestId('confirm-dialog-cancel')));

    expect(dialogs()).toHaveLength(0);
    expect(onCancel).toHaveBeenCalledExactlyOnceWith();
    expect(onOpenChange.mock.calls).toEqual([[true], [false]]);
  });

  it('still opens and closes by itself when the caller only wants to hear about it', async () => {
    const onOpenChange = vi.fn();
    render(<ConfirmDialog {...baseProps} onConfirm={vi.fn()} onOpenChange={onOpenChange} />);

    await openFromTrigger();
    expect(dialogs()).toHaveLength(1);
    expect(onOpenChange).toHaveBeenLastCalledWith(true);
    await act(async () => fireEvent.click(screen.getByTestId('confirm-dialog-cancel')));

    expect(dialogs()).toHaveLength(0);
    expect(onOpenChange).toHaveBeenLastCalledWith(false);
  });

  it('leaves the state to the caller once it passes `open`', async () => {
    const onOpenChange = vi.fn();
    render(<ConfirmDialog {...baseProps} open={false} onConfirm={vi.fn()} onOpenChange={onOpenChange} />);

    await openFromTrigger();

    expect(onOpenChange).toHaveBeenCalledExactlyOnceWith(true);
    expect(dialogs()).toHaveLength(0);
  });

  it('confirms, keeps both buttons blocked meanwhile, then closes', async () => {
    const pending = deferred<void>();
    const onConfirm = vi.fn(() => pending.promise);
    const onOpenChange = vi.fn();
    render(
      <ConfirmDialog {...baseProps} loadingText="Deleting..." onConfirm={onConfirm} onOpenChange={onOpenChange} />,
    );
    await openFromTrigger();
    expect(screen.getByTestId('confirm-dialog-confirm')).toHaveTextContent('Delete');

    await act(async () => fireEvent.click(screen.getByTestId('confirm-dialog-confirm')));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('confirm-dialog-confirm')).toHaveTextContent('Deleting...');
    expect(screen.getByTestId('confirm-dialog-confirm')).toBeDisabled();
    expect(screen.getByTestId('confirm-dialog-cancel')).toBeDisabled();
    await act(async () => pending.resolve());

    expect(dialogs()).toHaveLength(0);
    expect(onOpenChange).toHaveBeenLastCalledWith(false);
  });

  it('stays open, and unblocks, when the confirmed action fails', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    render(<ConfirmDialog {...baseProps} onConfirm={vi.fn().mockRejectedValue(new Error('refused'))} />);
    await openFromTrigger();

    await act(async () => fireEvent.click(screen.getByTestId('confirm-dialog-confirm')));

    expect(dialogs()).toHaveLength(1);
    expect(screen.getByTestId('confirm-dialog-confirm')).toBeEnabled();
  });
});
