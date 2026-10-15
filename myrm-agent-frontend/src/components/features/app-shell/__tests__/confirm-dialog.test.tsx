/** @vitest-environment jsdom */
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

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
