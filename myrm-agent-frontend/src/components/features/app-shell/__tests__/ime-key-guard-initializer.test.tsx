/** @vitest-environment jsdom */
import { StrictMode } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/primitives/dialog';
import { useComputerUseEscapeAbort } from '@/hooks/shell/useComputerUseEscapeAbort';
import useChatStore from '@/store/useChatStore';
import useDesktopInspectorStore from '@/store/useDesktopInspectorStore';
import ImeKeyGuardInitializer from '../ime-key-guard-initializer';

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

/** Mounts the window-level listener that aborts a running Computer Use turn on Escape. */
function ComputerUseEscapeHost() {
  useComputerUseEscapeAbort();
  return <input aria-label="composer" />;
}

const confirmCandidate = { key: 'Enter', keyCode: 229, isComposing: true };
const cancelComposition = { key: 'Escape', keyCode: 229, isComposing: true };

describe('ImeKeyGuardInitializer', () => {
  it('keeps the Enter that confirms an input-method candidate from submitting any field of the page', () => {
    const onSubmit = vi.fn();
    render(
      <>
        <ImeKeyGuardInitializer />
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
        <ImeKeyGuardInitializer />
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
        <ImeKeyGuardInitializer />
        <SubmitOnEnterField onSubmit={onSubmit} />
      </StrictMode>,
    );

    fireEvent.keyDown(screen.getByLabelText('title'), confirmCandidate);

    expect(onSubmit).not.toHaveBeenCalled();
  });
});

describe('Escape pressed to drop a composition', () => {
  function OpenDialog({ onOpenChange }: { onOpenChange: (open: boolean) => void }) {
    return (
      <Dialog open onOpenChange={onOpenChange}>
        <DialogContent>
          <DialogTitle>Search</DialogTitle>
          <DialogDescription>Type to search</DialogDescription>
          <input aria-label="query" />
        </DialogContent>
      </Dialog>
    );
  }

  it('does not close a dialog, while a plain Escape still does', () => {
    const onOpenChange = vi.fn();
    render(
      <>
        <ImeKeyGuardInitializer />
        <OpenDialog onOpenChange={onOpenChange} />
      </>,
    );
    const query = screen.getByLabelText('query');

    fireEvent.keyDown(query, cancelComposition);
    expect(onOpenChange).not.toHaveBeenCalled();

    fireEvent.keyDown(query, { key: 'Escape', keyCode: 27 });
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  describe('while a Computer Use turn runs', () => {
    const stopMessage = vi.fn();

    beforeEach(() => {
      stopMessage.mockReset();
      useChatStore.setState({
        chatId: 'chat-1',
        loading: true,
        currentBuiltinTools: ['computer_use'],
        stopMessage,
      } as Partial<ReturnType<typeof useChatStore.getState>>);
      useDesktopInspectorStore.setState({ engagedChatId: null });
    });

    afterEach(() => {
      useChatStore.setState({ loading: false, currentBuiltinTools: [] } as Partial<
        ReturnType<typeof useChatStore.getState>
      >);
    });

    it.each([
      ['before', true],
      ['after', false],
    ])('does not abort the turn, wherever the guard is mounted %s the abort listener', (_name, guardFirst) => {
      render(
        <>
          {guardFirst && <ImeKeyGuardInitializer />}
          <ComputerUseEscapeHost />
          {!guardFirst && <ImeKeyGuardInitializer />}
        </>,
      );
      const composer = screen.getByLabelText('composer');

      fireEvent.keyDown(composer, cancelComposition);
      expect(stopMessage).not.toHaveBeenCalled();

      fireEvent.keyDown(composer, { key: 'Escape', keyCode: 27 });
      expect(stopMessage).toHaveBeenCalledTimes(1);
    });
  });
});
