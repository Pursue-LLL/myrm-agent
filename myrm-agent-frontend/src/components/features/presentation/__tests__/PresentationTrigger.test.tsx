/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PresentationTrigger } from '../PresentationTrigger';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('PresentationTrigger component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    if (!HTMLDialogElement.prototype.showModal) {
      HTMLDialogElement.prototype.showModal = function showModalMock(this: HTMLDialogElement) {
        this.open = true;
      };
    }
    if (!HTMLDialogElement.prototype.close) {
      HTMLDialogElement.prototype.close = function closeMock(this: HTMLDialogElement) {
        this.open = false;
      };
    }
  });

  it('renders HUD trigger button with accessible label and shortcut', () => {
    render(<PresentationTrigger />);
    const triggerBtn = screen.getByLabelText('triggerAriaLabel');
    expect(triggerBtn).toBeInTheDocument();
    expect(screen.getByText('PPT')).toBeInTheDocument();
    expect(screen.getByText('⌥⌘P')).toBeInTheDocument();
  });

  it('opens generator modal when button is clicked', () => {
    render(<PresentationTrigger />);
    const triggerBtn = screen.getByLabelText('triggerAriaLabel');

    fireEvent.click(triggerBtn);
    expect(screen.getByText('modalTitle')).toBeInTheDocument();
  });

  it('opens generator modal when global shortcut Option+Cmd+P is pressed', () => {
    render(<PresentationTrigger />);

    fireEvent.keyDown(window, {
      key: 'p',
      altKey: true,
      metaKey: true,
    });

    expect(screen.getByText('modalTitle')).toBeInTheDocument();
  });
});
