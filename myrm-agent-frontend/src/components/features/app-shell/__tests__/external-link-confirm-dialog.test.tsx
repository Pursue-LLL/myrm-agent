/** @vitest-environment jsdom */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from 'vitest';

import { desktopBridge, type IShellBridge } from '@/lib/desktop-bridge';
import { useExternalLinkConfirmStore } from '@/store/useExternalLinkConfirmStore';
import en from '../../../../../locales/en.json';
import ExternalLinkConfirmDialog from '../external-link-confirm-dialog';

const messages: Record<string, string> = en.externalLinkConfirm;

/** Resolves keys against the shipped English messages, so a missing key fails these tests. */
const stableT = (key: string, values?: Record<string, string>): string =>
  (messages[key] ?? key).replace(/\{(\w+)\}/g, (_, name: string) => values?.[name] ?? '');

vi.mock('next-intl', () => ({ useTranslations: () => stableT, useLocale: () => 'en' }));

function requestLink(url: string, source: string | null): void {
  act(() => {
    useExternalLinkConfirmStore.getState().request({ url, source });
  });
}

describe('ExternalLinkConfirmDialog', () => {
  let openExternalUrl: MockInstance<IShellBridge['openExternalUrl']>;

  beforeEach(() => {
    useExternalLinkConfirmStore.setState({ open: false, link: null, declinedAt: 0 });
    openExternalUrl = vi.spyOn(desktopBridge.shell, 'openExternalUrl').mockResolvedValue(true);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders nothing until a link is requested', () => {
    render(<ExternalLinkConfirmDialog />);

    expect(screen.queryByRole('alertdialog')).toBeNull();
  });

  it('names the requesting app and shows the full address in a read-only field', async () => {
    render(<ExternalLinkConfirmDialog />);
    const url = 'https://example.com/docs?token=abc&next=%2Fhome#section';

    requestLink(url, 'Linear');

    const dialog = await screen.findByRole('alertdialog');
    expect(dialog).toHaveTextContent(messages.title);
    expect(dialog).toHaveTextContent('Linear wants to open the address below.');
    const field = screen.getByLabelText(messages.urlLabel) as HTMLTextAreaElement;
    expect(field.value).toBe(url);
    expect(field.readOnly).toBe(true);
  });

  it('falls back to an anonymous description when the request cannot be attributed', async () => {
    render(<ExternalLinkConfirmDialog />);

    requestLink('https://example.com/', null);

    expect(await screen.findByRole('alertdialog')).toHaveTextContent('This content wants to open the address below.');
  });

  it('puts the initial focus on the safe choice', async () => {
    render(<ExternalLinkConfirmDialog />);

    requestLink('https://example.com/', null);

    const cancel = await screen.findByRole('button', { name: messages.cancel });
    await waitFor(() => expect(cancel).toHaveFocus());
  });

  it('opens the address in the system browser on approval and starts no quiet period', async () => {
    render(<ExternalLinkConfirmDialog />);
    requestLink('https://example.com/go', 'Linear');

    fireEvent.click(await screen.findByRole('button', { name: messages.open }));

    expect(openExternalUrl).toHaveBeenCalledExactlyOnceWith('https://example.com/go');
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull());
    expect(useExternalLinkConfirmStore.getState().declinedAt).toBe(0);
  });

  it('opens nothing and starts the quiet period when the user cancels', async () => {
    render(<ExternalLinkConfirmDialog />);
    requestLink('https://example.com/go', 'Linear');

    fireEvent.click(await screen.findByRole('button', { name: messages.cancel }));

    expect(openExternalUrl).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull());
    expect(useExternalLinkConfirmStore.getState().declinedAt).toBeGreaterThan(0);
  });

  it('treats Escape as a refusal', async () => {
    render(<ExternalLinkConfirmDialog />);
    requestLink('https://example.com/go', 'Linear');
    await screen.findByRole('alertdialog');

    fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape' });

    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull());
    expect(openExternalUrl).not.toHaveBeenCalled();
    expect(useExternalLinkConfirmStore.getState().declinedAt).toBeGreaterThan(0);
  });

  it('is not dismissed by a click outside the dialog', async () => {
    render(<ExternalLinkConfirmDialog />);
    requestLink('https://example.com/go', 'Linear');
    await screen.findByRole('alertdialog');

    fireEvent.pointerDown(document.body);
    fireEvent.click(document.body);

    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    expect(useExternalLinkConfirmStore.getState().open).toBe(true);
  });
});
