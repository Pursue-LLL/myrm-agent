/** @vitest-environment jsdom */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode, RefObject } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { confirmAction } from '@/lib/app-dialog';
import {
  downloadMessageAsDocx,
  downloadMessageAsHtml,
  downloadMessageAsImage,
  downloadMessageAsMarkdown,
  getExportLang,
} from '@/lib/utils/chat-export';
import type { Message } from '@/store/chat/types';
import ExportMenu from '../ExportMenu';

// Keys of the `sources` and `MessageSources` namespaces carry a prefix, so a test can tell which namespace a label was
// read from.
const stableT = (key: string) => key;
const prefixed: Record<string, (key: string) => string> = {
  sources: (key) => `sources.${key}`,
  MessageSources: (key) => `MessageSources.${key}`,
};
vi.mock('next-intl', () => ({
  useTranslations: (namespace: string) => prefixed[namespace] ?? stableT,
}));
vi.mock('next-themes', () => ({ useTheme: () => ({ resolvedTheme: 'light' }) }));
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));
vi.mock('@/lib/app-dialog', () => ({ confirmAction: vi.fn() }));
vi.mock('@/lib/utils/chat-export', () => ({
  downloadMessageAsMarkdown: vi.fn(),
  downloadMessageAsDocx: vi.fn(),
  downloadMessageAsHtml: vi.fn(),
  downloadMessageAsImage: vi.fn(),
  getExportLang: vi.fn(),
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

const exportAs = (item: string) => fireEvent.click(screen.getByRole('button', { name: item }));
const exportAsImage = () => exportAs('exportMessage.image');

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

describe('ExportMenu text exports', () => {
  // The interface wording as the mocks above give it back: reasoning from `chat`, sources from `sources`.
  const LABELS = {
    reasoning: 'reasoningTitle',
    sources: 'sources.title',
    untitledSource: 'sources.untitled',
    sectionLabel: expect.any(Function),
  };
  const markdownRef: RefObject<HTMLDivElement | null> = { current: null };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getExportLang).mockReturnValue('zh');
  });

  it('hands the interface wording to the Markdown export', () => {
    const message = messageOfLength(100);
    render(<ExportMenu message={message} markdownRef={markdownRef} />);

    exportAs('exportMessage.markdown');

    expect(downloadMessageAsMarkdown).toHaveBeenCalledExactlyOnceWith(message, false, LABELS);
  });

  it('words a wiki section from the namespace that holds its translation', () => {
    render(<ExportMenu message={messageOfLength(100)} markdownRef={markdownRef} />);

    exportAs('exportMessage.markdown');

    const labels = vi.mocked(downloadMessageAsMarkdown).mock.calls[0][2];
    expect(labels.sectionLabel?.('index_routing')).toBe('MessageSources.kb_section_index_routing');
  });

  it('hands the interface wording, the theme and the interface language to the HTML export', async () => {
    const message = messageOfLength(100);
    render(<ExportMenu message={message} markdownRef={markdownRef} />);

    exportAs('exportMessage.html');
    await settle();

    expect(downloadMessageAsHtml).toHaveBeenCalledExactlyOnceWith(message, false, LABELS, 'light', 'zh');
  });

  it('hands the interface wording to the Word export', async () => {
    const message = messageOfLength(100);
    render(<ExportMenu message={message} markdownRef={markdownRef} />);

    exportAs('exportMessage.word');
    await settle();

    expect(downloadMessageAsDocx).toHaveBeenCalledExactlyOnceWith(message, false, LABELS);
  });

  it.each([
    ['exportMessage.markdown', downloadMessageAsMarkdown],
    ['exportMessage.word', downloadMessageAsDocx],
    ['exportMessage.html', downloadMessageAsHtml],
  ] as const)('passes the choice to include the reasoning on to the %s export', async (item, exporter) => {
    const message = { ...messageOfLength(100), reasoning: 'Because.' };
    render(<ExportMenu message={message} markdownRef={markdownRef} />);

    fireEvent.click(screen.getByRole('checkbox'));
    exportAs(item);
    await settle();

    expect(exporter).toHaveBeenCalledOnce();
    expect(vi.mocked(exporter).mock.calls[0].slice(0, 3)).toEqual([message, true, LABELS]);
  });
});
