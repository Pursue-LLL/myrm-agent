import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { LinkDetectionDialog } from '../LinkDetectionDialog';

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'en'));

function renderDialog(props: Partial<React.ComponentProps<typeof LinkDetectionDialog>> = {}) {
  const handlers = { setDontRemindAgain: vi.fn(), onAddAtSymbol: vi.fn(), onSkip: vi.fn() };
  render(<LinkDetectionDialog open dontRemindAgain={false} {...handlers} {...props} />);
  return handlers;
}

describe('LinkDetectionDialog', () => {
  it('renders nothing while closed', () => {
    renderDialog({ open: false });

    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('asks whether to reference the link, and explains what the @ does', () => {
    renderDialog();

    expect(screen.getByRole('dialog', { name: 'Do you want to use external resources?' })).toBeInTheDocument();
    expect(screen.getByText(/^Use @ symbol to reference external resources/)).toBeInTheDocument();
  });

  it('answers yes and no through their own buttons', () => {
    const { onAddAtSymbol, onSkip } = renderDialog();

    fireEvent.click(screen.getByRole('button', { name: 'Yes' }));
    expect(onAddAtSymbol).toHaveBeenCalledTimes(1);
    expect(onSkip).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'No' }));
    expect(onSkip).toHaveBeenCalledTimes(1);
    expect(onAddAtSymbol).toHaveBeenCalledTimes(1);
  });

  it('counts closing it any other way as no', () => {
    const { onAddAtSymbol, onSkip } = renderDialog();

    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(onSkip).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(onSkip).toHaveBeenCalledTimes(2);
    expect(onAddAtSymbol).not.toHaveBeenCalled();
  });

  it('shows the "do not remind" box as the state says and reports ticking it', () => {
    const { setDontRemindAgain } = renderDialog();
    const box = screen.getByRole('checkbox', { name: "Don't remind me again" });
    expect(box).not.toBeChecked();

    fireEvent.click(box);

    expect(setDontRemindAgain).toHaveBeenCalledExactlyOnceWith(true);
  });

  it('reports unticking it, too', () => {
    const { setDontRemindAgain } = renderDialog({ dontRemindAgain: true });
    const box = screen.getByRole('checkbox', { name: "Don't remind me again" });
    expect(box).toBeChecked();

    fireEvent.click(box);

    expect(setDontRemindAgain).toHaveBeenCalledExactlyOnceWith(false);
  });
});
