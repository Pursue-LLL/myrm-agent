import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { REVEAL_ON_HOVER } from '@/lib/utils/a11y';
import { PASTE_CARD_MIN_CHARS } from '@/lib/utils/spillover';
import type { File as FileType } from '@/store/chat/types';

import UserMessage from '../UserMessage';

const quote = vi.hoisted(() => ({ selection: { state: null, dismiss: () => undefined } }));

vi.mock('../QuoteToolbar', () => ({
  QuoteToolbar: () => null,
  useQuoteSelection: () => quote.selection,
}));
vi.mock('../SkillActivationChips', () => ({ SkillActivationChips: () => null }));
vi.mock('../../chat-window/ForkButton', () => ({ ForkButton: () => null }));
vi.mock('../../chat-window/RewindButton', () => ({ RewindButton: () => null }));
vi.mock('../../message-input-actions/ImageLightbox', () => ({ ImageLightbox: () => null }));
const portal = vi.hoisted(() => ({ open: vi.fn() }));
vi.mock('@/services/deliverable/openWorkspaceDeliverable', () => ({ openWorkspaceDeliverable: portal.open }));

// The global next-intl stub renders every translation key as itself.
const RETRY = 'retry';
const bubble = { content: 'hello there', messageId: 'u-1', isFirst: false };

describe('UserMessage failed send', () => {
  it('offers a retry under a bubble whose send failed', () => {
    const onRetry = vi.fn();
    render(<UserMessage {...bubble} sendFailed onRetry={onRetry} />);

    fireEvent.click(screen.getByRole('button', { name: RETRY }));

    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('offers no retry under a delivered bubble', () => {
    render(<UserMessage {...bubble} onRetry={vi.fn()} />);

    expect(screen.queryByRole('button', { name: RETRY })).toBeNull();
  });

  it('offers no retry while the bubble is being edited', () => {
    render(<UserMessage {...bubble} sendFailed isEditing onRetry={vi.fn()} />);

    expect(screen.queryByRole('button', { name: RETRY })).toBeNull();
  });
});

describe('UserMessage @links', () => {
  it('opens a bare domain over https in a new tab that cannot reach back to the page', () => {
    render(<UserMessage {...bubble} content="see @example.com/docs now" />);

    const link = screen.getByRole('link', { name: '@example.com/docs' });

    expect(link.getAttribute('href')).toBe('https://example.com/docs');
    expect(link.getAttribute('target')).toBe('_blank');
    expect(link.getAttribute('rel')).toBe('noopener noreferrer');
  });

  it('keeps the address of an @link that already carries a scheme', () => {
    render(<UserMessage {...bubble} content="open @http://localhost:3000/x" />);

    expect(screen.getByRole('link', { name: '@http://localhost:3000/x' }).getAttribute('href')).toBe(
      'http://localhost:3000/x',
    );
  });
});

describe('UserMessage action row', () => {
  it('reveals on touch and keyboard focus as well as on hover, so rewind stays reachable without a mouse', () => {
    render(<UserMessage {...bubble} />);

    const row = screen.getByTitle('Copy').parentElement;

    expect(row).toHaveClass(...REVEAL_ON_HOVER.split(' '));
  });
});

describe('UserMessage document attachments', () => {
  const document = (fileName: string, fileExtension: string): FileType => ({
    fileName,
    fileExtension,
    fileType: 'uploaded',
    fileUrl: `https://files.test/${fileName}`,
  });

  it('captions a document card by its extension and names the download action', () => {
    render(<UserMessage {...bubble} files={[document('plan.pdf', '.pdf')]} />);

    expect(screen.getByText('attachment_document')).not.toBeNull();
    expect(screen.getByRole('button', { name: 'attachment_download' })).not.toBeNull();
  });

  it('captions a document without an extension generically', () => {
    render(<UserMessage {...bubble} files={[document('LICENSE', '')]} />);

    expect(screen.getByText('attachment_document_generic')).not.toBeNull();
    expect(screen.queryByText('attachment_document')).toBeNull();
  });
});

describe('UserMessage pasted text', () => {
  const stored = { path: '/work/.myrm/pastes/payload_1.md', chars: 48_000, preview: 'Q3 review of the roadmap' };
  const stub = '<file_spillover path="/work/.myrm/pastes/payload_1.md" total_chars="48000"></file_spillover>';

  it('shows a stored paste as a card that opens its file, not as the stub the chat keeps', () => {
    portal.open.mockClear();
    render(<UserMessage {...bubble} content={stub} chatId="chat-1" spillover={stored} />);

    expect(screen.getByText(stored.preview)).not.toBeNull();
    expect(screen.queryByText(/file_spillover/)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'pastedText.viewFull' }));

    expect(portal.open).toHaveBeenCalledWith({ path: stored.path, chatId: 'chat-1' });
  });

  it('offers neither copy nor edit for a stored paste, whose stored text is only a pointer', () => {
    render(<UserMessage {...bubble} content={stub} chatId="chat-1" spillover={stored} onEdit={vi.fn()} />);

    expect(screen.queryByTitle('Copy')).toBeNull();
    expect(screen.queryByTitle('message.edit')).toBeNull();
  });

  it('offers no way to open the file where the message has no chat to resolve it in', () => {
    render(<UserMessage {...bubble} content={stub} spillover={stored} />);

    expect(screen.queryByRole('button', { name: 'pastedText.viewFull' })).toBeNull();
  });

  it('folds a long text the server did not park, in memory or from history, keeping copy and edit', () => {
    const text = 'x'.repeat(PASTE_CARD_MIN_CHARS + 1);
    render(<UserMessage {...bubble} content={text} onEdit={vi.fn()} />);

    expect(screen.getByTestId('pasted-text-card')).not.toBeNull();
    expect(screen.queryByText(text)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'pastedText.expand' }));

    expect(screen.getByText(text)).not.toBeNull();
    expect(screen.getByTitle('Copy')).not.toBeNull();
    expect(screen.getByTitle('message.edit')).not.toBeNull();
  });

  it('leaves a message at the limit as plain text', () => {
    render(<UserMessage {...bubble} content={'x'.repeat(PASTE_CARD_MIN_CHARS)} />);

    expect(screen.queryByTestId('pasted-text-card')).toBeNull();
  });
});
