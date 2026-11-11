/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode, RefObject } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { writeRichToClipboard, writeToClipboard } from '@/lib/utils/clipboardUtils';
import type { Message, Source } from '@/store/chat/types';
import type { MockLocale } from '@/test-utils/realIntl';
import Copy from '../Copy';

const intl = vi.hoisted(() => ({ locale: 'zh' as MockLocale }));
vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => intl.locale));
vi.mock('@/lib/utils/clipboardUtils', () => ({ writeToClipboard: vi.fn(), writeRichToClipboard: vi.fn() }));
// The menu's items are plain buttons here: opening a Radix menu is not what is under test.
vi.mock('@/components/primitives/dropdown-menu', () => ({
  DropdownMenu: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: { children: ReactNode }) => <>{children}</>,
  DropdownMenuContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DropdownMenuItem: ({ children, onClick }: { children: ReactNode; onClick?: () => void }) => (
    <button type="button" onClick={onClick}>
      {children}
    </button>
  ),
}));

const COPY_MARKDOWN: Record<MockLocale, string> = { zh: '复制 Markdown', en: 'Copy Markdown' };
const COPY_TEXT: Record<MockLocale, string> = { zh: '复制纯文本', en: 'Copy Plain Text' };

const SOURCES: Source[] = [
  { index: 1, type: 'web_search', url: 'https://one.example/a', title: 'One' },
  { index: 2, type: 'web_search', title: 'Titled, with no address' },
  { index: 3, type: 'web_search' },
];

const messageOf = (overrides: Partial<Message>): Message => ({
  messageId: 'msg-copy',
  chatId: 'chat-copy',
  createdAt: new Date('2026-01-01T00:00:00Z'),
  role: 'assistant',
  content: 'The answer.',
  ...overrides,
});

/** The rendered message the buttons take their page from; `text` is what the browser would give as its inner text. */
function renderedAnswer(html: string, text = ''): RefObject<HTMLDivElement | null> {
  const element = document.createElement('div');
  element.innerHTML = html;
  Object.defineProperty(element, 'innerText', { value: text });
  return { current: element };
}

const copyAs = (item: string) => fireEvent.click(screen.getByRole('button', { name: item }));

beforeEach(() => {
  vi.clearAllMocks();
  intl.locale = 'zh';
});

describe('Copy as Markdown', () => {
  it.each([
    ['zh', '来源', '未命名'],
    ['en', 'Sources', 'Untitled'],
  ] as const)('writes the answer and its sources in the interface language (%s)', (locale, heading, untitled) => {
    intl.locale = locale;
    render(
      <Copy
        message={messageOf({ sources: SOURCES })}
        markdownRef={renderedAnswer('<p>The answer.</p><button>Copy code</button>')}
      />,
    );

    copyAs(COPY_MARKDOWN[locale]);

    expect(writeRichToClipboard).toHaveBeenCalledExactlyOnceWith(
      `The answer.\n\n${heading}:  \n[1] https://one.example/a  \n[2] Titled, with no address  \n[3] ${untitled}`,
      '<p>The answer.</p>',
    );
  });

  it.each([[undefined], [[]]])('writes the answer alone when it has no sources (%j)', (sources) => {
    render(<Copy message={messageOf({ sources })} markdownRef={renderedAnswer('<p>The answer.</p>')} />);

    copyAs(COPY_MARKDOWN.zh);

    expect(writeRichToClipboard).toHaveBeenCalledExactlyOnceWith('The answer.', '<p>The answer.</p>');
  });

  it('writes plain Markdown when there is no rendered page to take from', () => {
    render(<Copy message={messageOf({ sources: SOURCES.slice(0, 1) })} markdownRef={{ current: null }} />);

    copyAs(COPY_MARKDOWN.zh);

    expect(writeToClipboard).toHaveBeenCalledExactlyOnceWith('The answer.\n\n来源:  \n[1] https://one.example/a');
    expect(writeRichToClipboard).not.toHaveBeenCalled();
  });
});

describe('Copy as plain text', () => {
  it('writes the rendered text without the space around it', () => {
    render(<Copy message={messageOf({})} markdownRef={renderedAnswer('<p>The answer.</p>', '  The answer.\n')} />);

    copyAs(COPY_TEXT.zh);

    expect(writeToClipboard).toHaveBeenCalledExactlyOnceWith('The answer.');
  });

  it('writes nothing when nothing is rendered', () => {
    render(<Copy message={messageOf({})} markdownRef={renderedAnswer('')} />);

    copyAs(COPY_TEXT.zh);

    expect(writeToClipboard).not.toHaveBeenCalled();
  });
});
