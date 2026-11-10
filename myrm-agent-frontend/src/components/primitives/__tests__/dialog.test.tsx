import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { Dialog, DialogContent, DialogDescription, DialogTitle } from '../dialog';

function renderDialog(props: { hideCloseButton?: boolean; onOpenChange?: (open: boolean) => void } = {}) {
  const { onOpenChange, ...contentProps } = props;
  return render(
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent {...contentProps}>
        <DialogTitle>Title</DialogTitle>
        <DialogDescription>Description</DialogDescription>
      </DialogContent>
    </Dialog>,
  );
}

describe('DialogContent', () => {
  it('offers a close button that asks to close', () => {
    const onOpenChange = vi.fn();
    renderDialog({ onOpenChange });

    fireEvent.click(screen.getByRole('button', { name: 'Close' }));

    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('can leave the close button out for dialogs that only close by answering', () => {
    renderDialog({ hideCloseButton: true });

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Close' })).toBeNull();
  });
});
