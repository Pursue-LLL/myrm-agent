/** @vitest-environment jsdom */
import { fireEvent, render, screen, act } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import SessionExportButton from '../SessionExportButton';

const modalPropsSpy = vi.fn();

const stableT = (key: string, values?: { defaultMessage?: string }): string => values?.defaultMessage ?? key;

vi.mock('../SessionExportModal', () => ({
  SessionExportModal: (props: unknown) => {
    modalPropsSpy(props);
    return <div data-testid="mock-session-export-modal" />;
  },
}));

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/store/useChatStore', () => ({
  default: () => 'Store Chat Title',
}));

describe('SessionExportButton', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders export button and opens modal on click', () => {
    render(<SessionExportButton chatId="chat-1" chatTitle="Custom Title" />);
    const button = screen.getByRole('button', { name: '导出' });
    expect(button).toBeInTheDocument();

    fireEvent.click(button);

    expect(modalPropsSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        open: true,
        chatId: 'chat-1',
        chatTitle: 'Custom Title',
        initialFormat: undefined,
      }),
    );
  });

  it('handles myrm:open-session-export event and passes initialFormat', () => {
    render(<SessionExportButton chatId="chat-1" />);

    act(() => {
      window.dispatchEvent(
        new CustomEvent('myrm:open-session-export', {
          detail: { chatId: 'chat-1', format: 'zip' },
        }),
      );
    });

    expect(modalPropsSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        open: true,
        chatId: 'chat-1',
        initialFormat: 'zip',
      }),
    );
  });

  it('correctly maps md alias to markdown format', () => {
    render(<SessionExportButton chatId="chat-1" />);

    act(() => {
      window.dispatchEvent(
        new CustomEvent('myrm:open-session-export', {
          detail: { chatId: 'chat-1', format: 'md' },
        }),
      );
    });

    expect(modalPropsSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        open: true,
        chatId: 'chat-1',
        initialFormat: 'markdown',
      }),
    );
  });

  it('ignores event targeting a different chatId', () => {
    render(<SessionExportButton chatId="chat-1" />);

    act(() => {
      window.dispatchEvent(
        new CustomEvent('myrm:open-session-export', {
          detail: { chatId: 'chat-999', format: 'json' },
        }),
      );
    });

    expect(modalPropsSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        open: false,
      }),
    );
  });
});
