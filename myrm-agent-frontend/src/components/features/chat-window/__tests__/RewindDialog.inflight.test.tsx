/** @vitest-environment jsdom */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { usePlanStore } from '@/store/chat/goals/usePlanStore';
import type { Message } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';
import { RewindDialog } from '../RewindDialog';

const { toastMock, rewindToMessageMock } = vi.hoisted(() => ({
  toastMock: vi.fn(),
  rewindToMessageMock: vi.fn(),
}));

const stableT = (key: string): string => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/hooks/shared/useToast', () => ({
  useToast: () => ({ toast: toastMock }),
}));

vi.mock('@/services/chat', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/chat')>();
  return {
    ...actual,
    rewindToMessage: (...args: unknown[]) => rewindToMessageMock(...args),
  };
});

const makeMessage = (id: string, role: Message['role']): Message => ({
  messageId: id,
  chatId: 'c1',
  createdAt: new Date(),
  content: '',
  role,
});

const rewound = {
  data: {
    success: true,
    deleted_count: 2,
    composer_text: 'second',
    message_index: 1,
    goal_paused: false,
    reverted_files: [],
  },
};

/** A rewind request the test settles by hand, so the dialog stays in flight until then. */
function deferredRewind() {
  let settle!: (value: unknown) => void;
  let fail!: (reason: unknown) => void;
  rewindToMessageMock.mockReturnValue(
    new Promise((resolve, reject) => {
      settle = resolve;
      fail = reject;
    }),
  );
  return { settle, fail };
}

/**
 * The page around the dialog: a textarea that precedes the composer (a queued message being edited, a card's reason
 * box), the composer, and the dialog, which Chat unmounts once it is closed.
 */
function Page({ onClosed }: { onClosed: () => void }) {
  const [open, setOpen] = useState(true);
  return (
    <>
      <textarea data-testid="draft-elsewhere" />
      <div data-chat-composer>
        <textarea data-chat-input data-testid="composer" />
      </div>
      {open && (
        <RewindDialog
          open
          onOpenChange={(next) => {
            if (!next) {
              setOpen(false);
              onClosed();
            }
          }}
          chatId="c1"
          messageId="u2"
          messageIndex={2}
        />
      )}
    </>
  );
}

/** Confirms the rewind and waits until the dialog shows it is in flight. */
async function confirmRewind() {
  fireEvent.click(screen.getByText('scopeConversation'));
  fireEvent.click(screen.getByText('confirm'));
  await screen.findByText('rewinding');
}

const nextFrame = () =>
  act(async () => {
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
  });

describe('RewindDialog around the request', () => {
  beforeEach(() => {
    rewindToMessageMock.mockReset();
    toastMock.mockReset();
    usePlanStore.setState({ fetchPlan: vi.fn(async (_chatId: string): Promise<void> => undefined) });
    useChatStore.setState({
      chatId: 'c1',
      messages: [makeMessage('u0', 'user'), makeMessage('a0', 'assistant'), makeMessage('u2', 'user')],
      loading: false,
      inputMessage: '',
      pendingExplicitSkillActivation: null,
    });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => [] }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('stays open and offers no close button while the request is in flight', async () => {
    const request = deferredRewind();
    const onClosed = vi.fn();
    render(<Page onClosed={onClosed} />);
    expect(screen.getByText('Close')).toBeInTheDocument();

    await confirmRewind();
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });

    expect(onClosed).not.toHaveBeenCalled();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.queryByText('Close')).not.toBeInTheDocument();

    await act(async () => {
      request.settle(rewound);
    });
    await waitFor(() => {
      expect(onClosed).toHaveBeenCalledTimes(1);
    });
  });

  it('can be dismissed again once the request has failed', async () => {
    const request = deferredRewind();
    const onClosed = vi.fn();
    render(<Page onClosed={onClosed} />);

    await confirmRewind();
    await act(async () => {
      request.fail(new Error('boom'));
    });
    await screen.findByText('confirm');
    expect(toastMock).toHaveBeenCalledWith(expect.objectContaining({ description: 'boom', variant: 'destructive' }));

    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(onClosed).toHaveBeenCalledTimes(1);
  });

  it('puts the focus on the composer, not on an earlier textarea, once the rewind has gone through', async () => {
    rewindToMessageMock.mockResolvedValue(rewound);
    render(<Page onClosed={vi.fn()} />);

    await confirmRewind();

    await waitFor(() => {
      expect(screen.getByTestId('composer')).toHaveFocus();
    });
    expect(screen.getByTestId('draft-elsewhere')).not.toHaveFocus();
  });

  it('leaves the focus alone when the open chat changed while the request was in flight', async () => {
    const request = deferredRewind();
    const onClosed = vi.fn();
    render(<Page onClosed={onClosed} />);

    await confirmRewind();
    useChatStore.setState({ chatId: 'other-chat' });
    await act(async () => {
      request.settle(rewound);
    });
    await waitFor(() => {
      expect(onClosed).toHaveBeenCalledTimes(1);
    });
    await nextFrame();
    await nextFrame();

    expect(screen.getByTestId('composer')).not.toHaveFocus();
  });
});
