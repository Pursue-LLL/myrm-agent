/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { renderToString } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { useNoticeSlot, type NoticeId } from '../useNoticeSlot';

function Notice({ id, wants }: { id: NoticeId; wants: boolean }) {
  const holdsSlot = useNoticeSlot(id, wants);
  return holdsSlot ? <p>{id}</p> : null;
}

/** A notice that closes itself, so its siblings only learn about it through the slot and are not re-rendered. */
function ClosableNotice({ id }: { id: NoticeId }) {
  const [wants, setWants] = useState(true);
  const holdsSlot = useNoticeSlot(id, wants);
  return holdsSlot ? (
    <button type="button" onClick={() => setWants(false)}>
      {id}
    </button>
  ) : null;
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

  it('tells the waiting notice when the holder closes itself', () => {
    render(
      <>
        <ClosableNotice id="update-nudge" />
        <ClosableNotice id="migration-discovery" />
      </>,
    );
    expect(shown('migration-discovery')).toBe(false);

    fireEvent.click(screen.getByText('update-nudge'));

    expect(shown('update-nudge')).toBe(false);
    expect(shown('migration-discovery')).toBe(true);
  });

  it('tells a waiting notice elsewhere on the page when the holder unmounts', () => {
    const holder = render(<Notice id="update-nudge" wants />);
    render(<Notice id="migration-discovery" wants />);
    expect(shown('migration-discovery')).toBe(false);

    holder.unmount();

    expect(shown('migration-discovery')).toBe(true);
  });

  it('renders no notice on the server, so the first client render matches it', () => {
    expect(renderToString(<Notice id="update-nudge" wants />)).toBe('');
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
