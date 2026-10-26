/** @vitest-environment jsdom */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode, RefObject } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { confirmAction } from '@/lib/app-dialog';
import { downloadMessageAsImage } from '@/lib/utils/chat-export';
import type { Message } from '@/store/chat/types';
import ExportMenu from '../ExportMenu';

const stableT = (key: string) => key;
vi.mock('next-intl', () => ({ useTranslations: () => stableT }));
vi.mock('next-themes', () => ({ useTheme: () => ({ resolvedTheme: 'light' }) }));
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));
vi.mock('@/lib/app-dialog', () => ({ confirmAction: vi.fn() }));
vi.mock('@/lib/utils/chat-export', () => ({
  downloadMessageAsMarkdown: vi.fn(),
  downloadMessageAsDocx: vi.fn(),
  downloadMessageAsHtml: vi.fn(),
  downloadMessageAsImage: vi.fn(),
}));
// The menu's items are plain buttons here: opening a Radix menu is not what is under test.
vi.mock('@/components/primitives/dropdown-menu', () => ({
  DropdownMenu: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: { children: ReactNode }) => <>{children}</>,
  DropdownMenuContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DropdownMenuSeparator: () => <hr />,
  DropdownMenuItem: ({ children, onClick }: { children: ReactNode; onClick?: () => void }) => (
    <button type="button" onClick={onClick}>
      {children}
    </button>
  ),
}));

const messageOfLength = (length: number): Message => ({
  messageId: 'msg-1',
  chatId: 'chat-1',
  createdAt: new Date('2026-01-01T00:00:00Z'),
  role: 'assistant',
  content: 'x'.repeat(length),
});
const LONG = 50_001;

const settle = () =>
  act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });

const exportAsImage = () => fireEvent.click(screen.getByRole('button', { name: 'exportMessage.image' }));

describe('ExportMenu image export', () => {
  let element: HTMLDivElement;
  let markdownRef: RefObject<HTMLDivElement | null>;

  beforeEach(() => {
    vi.clearAllMocks();
    element = document.createElement('div');
    markdownRef = { current: element };
  });

  it('exports a normal message straight away, without a question', async () => {
    const message = messageOfLength(100);
    render(<ExportMenu message={message} markdownRef={markdownRef} />);

    exportAsImage();

    expect(downloadMessageAsImage).toHaveBeenCalledExactlyOnceWith(element, message);
    expect(confirmAction).not.toHaveBeenCalled();
  });

  it('warns about a very long message and exports it once the user agrees', async () => {
    vi.mocked(confirmAction).mockResolvedValue(true);
    const message = messageOfLength(LONG);
    render(<ExportMenu message={message} markdownRef={markdownRef} />);

    exportAsImage();

    await waitFor(() => expect(downloadMessageAsImage).toHaveBeenCalledExactlyOnceWith(element, message));
    expect(confirmAction).toHaveBeenCalledExactlyOnceWith({
      variant: 'warning',
      description: 'exportMessage.longContentWarning',
      confirmText: 'exportMessage.image',
    });
  });

  it('exports nothing when the user declines the warning', async () => {
    vi.mocked(confirmAction).mockResolvedValue(false);
    render(<ExportMenu message={messageOfLength(LONG)} markdownRef={markdownRef} />);

    exportAsImage();
    await waitFor(() => expect(confirmAction).toHaveBeenCalledTimes(1));
    await settle();

    expect(downloadMessageAsImage).not.toHaveBeenCalled();
  });

  it('exports nothing when the message left the screen while the question was open', async () => {
    vi.mocked(confirmAction).mockImplementation(async () => {
      markdownRef.current = null;
      return true;
    });
    render(<ExportMenu message={messageOfLength(LONG)} markdownRef={markdownRef} />);

    exportAsImage();
    await waitFor(() => expect(confirmAction).toHaveBeenCalledTimes(1));
    await settle();

    expect(downloadMessageAsImage).not.toHaveBeenCalled();
  });

  it('does nothing, and asks nothing, when there is no rendered message to capture', async () => {
    markdownRef.current = null;
    render(<ExportMenu message={messageOfLength(LONG)} markdownRef={markdownRef} />);

    exportAsImage();
    await settle();

    expect(confirmAction).not.toHaveBeenCalled();
    expect(downloadMessageAsImage).not.toHaveBeenCalled();
  });
});
