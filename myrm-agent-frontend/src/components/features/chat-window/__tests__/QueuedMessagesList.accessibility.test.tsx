import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { QueuedMessage } from '@/store/chat/useMessageQueueStore';
import { expectDefined } from '@/test-utils/expectDefined';
import { QueuedMessagesList } from '../QueuedMessagesList';

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'zh'));

const queue: QueuedMessage[] = [
  { id: 'q-7a1f', text: '先整理需求', files: [], timestamp: 1000 },
  { id: 'q-9b2c', text: '再写测试', files: [], timestamp: 2000 },
];

describe('QueuedMessagesList keyboard reordering', () => {
  it('announces the queue position instead of the internal message id', async () => {
    const user = userEvent.setup();
    render(
      <QueuedMessagesList
        queue={queue}
        pausedReason={null}
        editingId={null}
        setEditingId={vi.fn()}
        editMessage={vi.fn()}
        removeMessage={vi.fn()}
        reorder={vi.fn()}
        resume={vi.fn()}
      />,
    );

    const [handle] = screen.getAllByRole('button', { name: '拖动调整顺序' });
    expectDefined(handle, 'first drag handle');
    expect(handle).toHaveAttribute('aria-roledescription', '可拖动项');

    await act(async () => handle.focus());
    await user.keyboard(' ');

    const liveRegion = screen.getByRole('status');
    expect(liveRegion).toHaveTextContent('已拾起“排队中 (1/2)”。');
    expect(liveRegion).not.toHaveTextContent('q-7a1f');
  });
});
