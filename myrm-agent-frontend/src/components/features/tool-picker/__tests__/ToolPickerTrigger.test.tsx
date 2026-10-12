/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ToolPickerTrigger } from '../ToolPickerTrigger';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/components/features/icons/PremiumIcons', () => ({
  IconWrench: () => <span data-testid="icon-wrench" />,
  IconSearch: () => <span data-testid="icon-search" />,
  IconX: () => <span data-testid="icon-x" />,
}));

describe('ToolPickerTrigger component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    if (!HTMLDialogElement.prototype.showModal) {
      HTMLDialogElement.prototype.showModal = function showModalMock(
        this: HTMLDialogElement,
      ) {
        this.open = true;
      };
    }
    if (!HTMLDialogElement.prototype.close) {
      HTMLDialogElement.prototype.close = function closeMock(
        this: HTMLDialogElement,
      ) {
        this.open = false;
      };
    }
  });

  it('renders trigger capsule button with label and shortcut hint', () => {
    render(<ToolPickerTrigger />);

    expect(screen.getByText('Tools')).toBeDefined();
    expect(screen.getByText('⌘⇧T')).toBeDefined();
    expect(screen.getByRole('button', { name: /triggerAriaLabel/i })).toBeDefined();
  });

  it('opens tool picker drawer when trigger button is clicked', () => {
    render(<ToolPickerTrigger />);

    const triggerBtn = screen.getByRole('button', { name: /triggerAriaLabel/i });
    fireEvent.click(triggerBtn);

    expect(screen.getByText('modalTitle')).toBeDefined();
    expect(screen.getByPlaceholderText('searchPlaceholder')).toBeDefined();
  });

  it('toggles tool drawer on Cmd+Shift+T shortcut', () => {
    render(<ToolPickerTrigger />);

    // Press Cmd+Shift+T to open
    fireEvent.keyDown(window, {
      key: 't',
      metaKey: true,
      shiftKey: true,
    });

    expect(screen.getByText('modalTitle')).toBeDefined();

    // Press again to close
    fireEvent.keyDown(window, {
      key: 't',
      metaKey: true,
      shiftKey: true,
    });

    expect(screen.queryByText('modalTitle')).toBeNull();
  });
});
