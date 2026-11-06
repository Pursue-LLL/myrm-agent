/** @vitest-environment jsdom */
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { useNoticeSlot, type NoticeId } from '../useNoticeSlot';

function Notice({ id, wants }: { id: NoticeId; wants: boolean }) {
  const holdsSlot = useNoticeSlot(id, wants);
  return holdsSlot ? <p>{id}</p> : null;
}

const shown = (id: NoticeId) => screen.queryByText(id) !== null;

describe('useNoticeSlot', () => {
  it('lets the notice that asks first keep the slot while the other waits', () => {
    render(
      <>
        <Notice id="update-nudge" wants />
        <Notice id="migration-discovery" wants />
      </>,
    );

    expect(shown('update-nudge')).toBe(true);
    expect(shown('migration-discovery')).toBe(false);
  });

  it('does not take the slot from a notice that is already on screen when a later one arrives', () => {
    const { rerender } = render(
      <>
        <Notice id="migration-discovery" wants />
        <Notice id="update-nudge" wants={false} />
      </>,
    );

    rerender(
      <>
        <Notice id="migration-discovery" wants />
        <Notice id="update-nudge" wants />
      </>,
    );

    expect(shown('migration-discovery')).toBe(true);
    expect(shown('update-nudge')).toBe(false);
  });

  it('hands the slot to the waiting notice once the holder is closed', () => {
    const { rerender } = render(
      <>
        <Notice id="update-nudge" wants />
        <Notice id="migration-discovery" wants />
      </>,
    );

    rerender(
      <>
        <Notice id="update-nudge" wants={false} />
        <Notice id="migration-discovery" wants />
      </>,
    );

    expect(shown('update-nudge')).toBe(false);
    expect(shown('migration-discovery')).toBe(true);
  });

  it('hands the slot over when the holder unmounts, and leaves nothing behind for the next page', () => {
    const first = render(
      <>
        <Notice id="update-nudge" wants />
        <Notice id="migration-discovery" wants />
      </>,
    );
    first.unmount();

    render(<Notice id="migration-discovery" wants />);

    expect(shown('migration-discovery')).toBe(true);
  });

  it('is never blocked by a notice that has nothing to show', () => {
    render(
      <>
        <Notice id="update-nudge" wants={false} />
        <Notice id="migration-discovery" wants />
      </>,
    );

    expect(shown('update-nudge')).toBe(false);
    expect(shown('migration-discovery')).toBe(true);
  });
});
