/** @vitest-environment jsdom */
import { StrictMode } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import ImeEnterGuardInitializer from '../ime-enter-guard-initializer';

/** A field that submits on Enter, the way the sidebar rename input does. */
function SubmitOnEnterField({ onSubmit }: { onSubmit: () => void }) {
  return (
    <input
      aria-label="title"
      onKeyDown={(event) => {
        if (event.key === 'Enter') {
          onSubmit();
        }
      }}
    />
  );
}

const confirmCandidate = { key: 'Enter', keyCode: 229, isComposing: true };

describe('ImeEnterGuardInitializer', () => {
  it('keeps the Enter that confirms an input-method candidate from submitting any field of the page', () => {
    const onSubmit = vi.fn();
    render(
      <>
        <ImeEnterGuardInitializer />
        <SubmitOnEnterField onSubmit={onSubmit} />
      </>,
    );
    const field = screen.getByLabelText('title');

    fireEvent.keyDown(field, confirmCandidate);
    expect(onSubmit).not.toHaveBeenCalled();

    fireEvent.keyDown(field, { key: 'Enter', keyCode: 13 });
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it('removes the guard when it unmounts', () => {
    const onSubmit = vi.fn();
    const { rerender } = render(
      <>
        <ImeEnterGuardInitializer />
        <SubmitOnEnterField onSubmit={onSubmit} />
      </>,
    );

    rerender(<SubmitOnEnterField onSubmit={onSubmit} />);
    fireEvent.keyDown(screen.getByLabelText('title'), confirmCandidate);

    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it('stays installed under React StrictMode double mounting', () => {
    const onSubmit = vi.fn();
    render(
      <StrictMode>
        <ImeEnterGuardInitializer />
        <SubmitOnEnterField onSubmit={onSubmit} />
      </StrictMode>,
    );

    fireEvent.keyDown(screen.getByLabelText('title'), confirmCandidate);

    expect(onSubmit).not.toHaveBeenCalled();
  });
});
