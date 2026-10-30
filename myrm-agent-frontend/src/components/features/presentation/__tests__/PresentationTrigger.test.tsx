/** @vitest-environment jsdom */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PresentationTrigger } from '../PresentationTrigger';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

// The generator dialog and its content stay mounted while closed, so only `open` tells the two states apart.
const getGeneratorDialog = (): HTMLDialogElement => {
  const dialog = document.querySelector('dialog');
  if (!dialog) {
    throw new Error('presentation generator dialog is not mounted');
  }
  return dialog;
};

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
    expect(getGeneratorDialog().open).toBe(false);

    fireEvent.click(screen.getByLabelText('triggerAriaLabel'));

    expect(getGeneratorDialog().open).toBe(true);
  });

  // macOS rewrites `key` while Option is held (Option+P yields 'π'), so the shortcut has to follow the physical key.
  it.each([
    ['Option+Cmd+P on macOS', { key: 'π', code: 'KeyP', altKey: true, metaKey: true }],
    ['Alt+Ctrl+P on Windows/Linux', { key: 'p', code: 'KeyP', altKey: true, ctrlKey: true }],
    ['Option+Cmd+P from a source without a physical code', { key: 'P', altKey: true, metaKey: true }],
  ])('opens generator modal on %s', (_label, keys) => {
    render(<PresentationTrigger />);
    expect(getGeneratorDialog().open).toBe(false);

    fireEvent.keyDown(window, keys);

    expect(getGeneratorDialog().open).toBe(true);
  });

  it.each([
    ['Cmd+P without Option (browser print)', { key: 'p', code: 'KeyP', metaKey: true }],
    ['Option+P without Cmd/Ctrl', { key: 'π', code: 'KeyP', altKey: true }],
    ['Option+Cmd+Q (a different physical key)', { key: 'œ', code: 'KeyQ', altKey: true, metaKey: true }],
  ])('ignores %s', (_label, keys) => {
    render(<PresentationTrigger />);

    fireEvent.keyDown(window, keys);

    expect(getGeneratorDialog().open).toBe(false);
  });

  it('menu mode hides the floating pill and opens from the utility event', () => {
    render(<PresentationTrigger showTrigger={false} />);
    expect(screen.queryByLabelText('triggerAriaLabel')).toBeNull();
    expect(getGeneratorDialog().open).toBe(false);

    act(() => {
      window.dispatchEvent(new Event('myrm:open-presentation'));
    });

    expect(getGeneratorDialog().open).toBe(true);
  });
});
