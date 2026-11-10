/** @vitest-environment jsdom */
import { act, fireEvent, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useFeatureGateStore } from '@/store/useFeatureGateStore';
import { useFlowPadStore } from '@/store/useFlowPadStore';
import {
  chatState,
  click,
  deferred,
  mocks,
  openChatPad,
  openInlinePad,
  renderFlowPad,
  resetFlowPadKit,
  simulateChatChange,
  submitText,
} from './flowPadTestKit';

vi.mock('@/components/features/message-input-actions/SpeechInputButton', () => ({
  default: ({ onTranscript }: { onTranscript: (transcript: string) => void }) => (
    <button type="button" onClick={() => onTranscript('spoken words')}>
      speak
    </button>
  ),
}));

function showInlineResult(content: string): void {
  openInlinePad();
  useFlowPadStore.setState({ inlineResult: content, inlineGenerating: false });
}

function stubClipboard(writeText: (text: string) => Promise<void>): void {
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
}

describe('FlowPadModal: sending, results and drafting', () => {
  beforeEach(() => {
    resetFlowPadKit();
    useFeatureGateStore.setState({ enabledFeatures: new Set() });
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('session route label', () => {
    it.each([
      ['no agent config', null, 'defaultAgent'],
      ['an unnamed config', {}, 'defaultAgent'],
      ['a padded name', { agentName: '  Alice  ' }, 'Alice'],
      ['a legacy name', { name: 'Legacy Name' }, 'Legacy Name'],
      ['a blank legacy name', { name: '   ' }, 'defaultAgent'],
      ['a blank name beside a legacy name', { agentName: '   ', name: 'Fallback' }, 'Fallback'],
      ['a built-in agent', { agentId: 'builtin-general', agentName: 'General Agent' }, 'General Assistant'],
    ])('names the current route after %s', (_case, config, label) => {
      chatState.agentConfig = config;
      openInlinePad();
      renderFlowPad();

      const trigger = screen.getByTestId('flowpad-inline-route-trigger');
      expect(trigger).toHaveTextContent(label);
      expect(within(trigger).getByText(label).textContent).toBe(label);
    });
  });

  describe('sending', () => {
    it('sends the screenshot of a chat capture with the quick action prompt and closes the pad', async () => {
      openChatPad({ screenshot: 'abc', windowTitle: 'Win', extractedText: 'ctx' });
      renderFlowPad();

      await click(screen.getByText('quickSummarize'));

      const [message] = chatState.sendMessage.mock.calls[0];
      expect(message).toContain('**Win**');
      expect(message.endsWith('summarizePrompt')).toBe(true);
      expect(chatState.setFiles).toHaveBeenCalledWith([
        {
          fileName: 'appshot_1.jpg',
          fileExtension: 'jpg',
          fileUrl: 'data:image/jpeg;base64,abc',
          fileType: 'uploaded',
        },
      ]);
      expect(mocks.toast.success).toHaveBeenCalledWith('submitted', { duration: 3000 });
      expect(useFlowPadStore.getState().isOpen).toBe(false);
    });

    it('ignores a second Enter while the first message is still being sent', async () => {
      const pending = deferred<boolean>();
      chatState.sendMessage.mockReturnValueOnce(pending.promise);
      openInlinePad();
      renderFlowPad();

      await submitText('first');
      await submitText('second');
      expect(chatState.sendMessage).toHaveBeenCalledTimes(1);

      await act(async () => {
        pending.resolve(true);
      });
      await submitText('third');
      expect(chatState.sendMessage).toHaveBeenCalledTimes(2);
    });

    it('keeps the inline pad open after a quick action so the result can be pasted back', async () => {
      openInlinePad({ screenshot: 'abc' });
      renderFlowPad();

      await click(screen.getByText('quickSummarize'));

      expect(mocks.toast.success).toHaveBeenCalledWith('inlineSubmitted', { duration: 2000 });
      expect(useFlowPadStore.getState().isOpen).toBe(true);
    });
  });

  describe('submitting', () => {
    it('does nothing when there is neither text nor a capture', async () => {
      openChatPad();
      renderFlowPad();

      await act(async () => {
        fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Enter' });
      });

      expect(chatState.sendMessage).not.toHaveBeenCalled();
      expect(mocks.toast.success).not.toHaveBeenCalled();
      expect(useFlowPadStore.getState().isOpen).toBe(true);
    });

    it('submits on Enter without a line break, while Shift+Enter submits nothing', async () => {
      openInlinePad();
      renderFlowPad();
      const textbox = screen.getByRole('textbox');
      fireEvent.change(textbox, { target: { value: 'hello' } });
      let lineBreakAllowed = false;

      await act(async () => {
        lineBreakAllowed = fireEvent.keyDown(textbox, { key: 'Enter', shiftKey: true });
      });
      expect(lineBreakAllowed).toBe(true);
      expect(chatState.sendMessage).not.toHaveBeenCalled();

      await act(async () => {
        lineBreakAllowed = fireEvent.keyDown(textbox, { key: 'Enter' });
      });
      expect(lineBreakAllowed).toBe(false);
      expect(chatState.sendMessage).toHaveBeenCalledTimes(1);
    });

    it('tells the user a typed message did not go out and keeps the pad and the text', async () => {
      const errorLog = vi.spyOn(console, 'error').mockImplementation(() => {});
      chatState.sendMessage.mockRejectedValueOnce(new Error('network down'));
      openChatPad({ screenshot: 'abc' });
      renderFlowPad();

      await submitText('hello');

      expect(errorLog).toHaveBeenCalledWith('FlowPad submit failed:', expect.any(Error));
      expect(mocks.toast.error).toHaveBeenCalledWith('submitFailed', { duration: 3000 });
      expect(useFlowPadStore.getState().isOpen).toBe(true);
      expect(screen.getByRole('textbox')).toHaveValue('hello');
    });

    it('tells the user a quick action did not go out and keeps the pad', async () => {
      const errorLog = vi.spyOn(console, 'error').mockImplementation(() => {});
      chatState.sendMessage.mockRejectedValueOnce(new Error('network down'));
      openChatPad({ screenshot: 'abc' });
      renderFlowPad();

      await click(screen.getByText('quickSummarize'));

      expect(errorLog).toHaveBeenCalledWith('FlowPad quick action failed:', expect.any(Error));
      expect(mocks.toast.error).toHaveBeenCalledWith('submitFailed', { duration: 3000 });
      expect(useFlowPadStore.getState().isOpen).toBe(true);
    });

    it('disables the quick actions while a message is being sent', async () => {
      const pending = deferred<boolean>();
      chatState.sendMessage.mockReturnValueOnce(pending.promise);
      openInlinePad({ screenshot: 'abc' });
      renderFlowPad();

      await submitText('hello');
      expect(screen.getByText('quickSummarize').closest('button')).toBeDisabled();

      await act(async () => {
        pending.resolve(true);
      });
      expect(screen.getByText('quickSummarize').closest('button')).toBeEnabled();
    });

    it('attaches screenshots after the files already in the composer and takes only its own back when refused', async () => {
      const existing = { fileName: 'notes.pdf', fileExtension: 'pdf', fileUrl: 'blob:notes', fileType: 'uploaded' };
      chatState.files = [existing];
      chatState.sendMessage.mockResolvedValueOnce(false);
      openChatPad({ screenshot: 'abc' });
      renderFlowPad();

      await click(screen.getByText('quickSummarize'));

      expect(chatState.setFiles.mock.calls[0][0]).toEqual([
        existing,
        expect.objectContaining({ fileName: 'appshot_1.jpg' }),
      ]);
      expect(chatState.setFiles.mock.calls[1][0]).toEqual([existing]);
    });
  });

  describe('inline result', () => {
    it('clears the previous result while the next request is in flight', async () => {
      const pending = deferred<boolean>();
      chatState.sendMessage.mockReturnValueOnce(pending.promise);
      showInlineResult('Old answer');
      renderFlowPad();

      await submitText('again');

      expect(useFlowPadStore.getState()).toMatchObject({ inlineResult: '', inlineGenerating: true });
      await act(async () => {
        pending.resolve(true);
      });
    });

    it('forgets the request of a closed pad so its late stream does not fill the next pad', async () => {
      openInlinePad();
      renderFlowPad();
      await submitText('question');

      act(() => useFlowPadStore.getState().close());
      act(() => openInlinePad());
      act(() =>
        simulateChatChange({
          loading: true,
          messages: [{ role: 'assistant', content: 'stale answer', messageId: 'inline-msg-1' }],
        }),
      );

      expect(useFlowPadStore.getState().inlineResult).toBe('');
    });

    it('ends the generating state when the turn finishes without any assistant text', async () => {
      openInlinePad();
      renderFlowPad();
      await submitText('question');
      expect(useFlowPadStore.getState().inlineGenerating).toBe(true);

      act(() => simulateChatChange({ loading: true }));
      act(() => simulateChatChange({ loading: false }));

      expect(useFlowPadStore.getState().inlineGenerating).toBe(false);
    });
  });

  describe('result actions', () => {
    it('pastes the result back through the desktop shell, hides the window and closes the pad', async () => {
      mocks.isTauriRuntime.mockReturnValue(true);
      showInlineResult('Final text');
      renderFlowPad();

      await click(screen.getByText('pasteBack'));

      expect(mocks.invoke).toHaveBeenCalledWith('inline_paste_back', { content: 'Final text' });
      expect(mocks.toast.success).toHaveBeenCalledWith('pastedBack', { duration: 2000 });
      expect(mocks.hideWindow).toHaveBeenCalledTimes(1);
      expect(useFlowPadStore.getState().isOpen).toBe(false);
    });

    it('leaves the window alone when it is not the desktop shell', async () => {
      showInlineResult('Final text');
      renderFlowPad();

      await click(screen.getByText('pasteBack'));

      expect(mocks.hideWindow).not.toHaveBeenCalled();
      expect(useFlowPadStore.getState().isOpen).toBe(false);
    });

    it('reports a failed paste-back and keeps the pad open', async () => {
      const errorLog = vi.spyOn(console, 'error').mockImplementation(() => {});
      mocks.invoke.mockRejectedValueOnce(new Error('no focus target'));
      showInlineResult('Final text');
      renderFlowPad();

      await click(screen.getByText('pasteBack'));

      expect(errorLog).toHaveBeenCalledWith('Paste back failed:', expect.any(Error));
      expect(mocks.toast.error).toHaveBeenCalledWith('pasteBackFailed', { duration: 3000 });
      expect(useFlowPadStore.getState().isOpen).toBe(true);
    });

    it('copies the result and reports a clipboard that refuses', async () => {
      const writeText = vi.fn().mockResolvedValueOnce(undefined).mockRejectedValueOnce(new Error('denied'));
      stubClipboard(writeText);
      showInlineResult('Final text');
      renderFlowPad();

      await click(screen.getByText('copyResult'));
      expect(writeText).toHaveBeenCalledWith('Final text');
      expect(mocks.toast.success).toHaveBeenCalledWith('copied', { duration: 2000 });

      await click(screen.getByText('copyResult'));
      expect(mocks.toast.error).toHaveBeenCalledWith('copyFailed', { duration: 3000 });
    });

    it('does nothing with a result that is only whitespace', async () => {
      const writeText = vi.fn().mockResolvedValue(undefined);
      stubClipboard(writeText);
      showInlineResult('   ');
      renderFlowPad();

      await click(screen.getByText('pasteBack'));
      await click(screen.getByText('copyResult'));

      expect(mocks.invoke).not.toHaveBeenCalled();
      expect(writeText).not.toHaveBeenCalled();
      expect(mocks.toast.success).not.toHaveBeenCalled();
    });
  });

  describe('dictation', () => {
    it('starts an empty draft with the transcript and appends to a draft that exists', async () => {
      useFeatureGateStore.setState({ enabledFeatures: new Set(['voice_interaction']) });
      openInlinePad();
      renderFlowPad();
      const textbox = screen.getByRole('textbox');

      await click(screen.getByText('speak'));
      expect(textbox).toHaveValue('spoken words');

      fireEvent.change(textbox, { target: { value: 'hello' } });
      await act(async () => {
        fireEvent.click(screen.getByText('speak'));
      });
      expect(textbox).toHaveValue('hello spoken words');
      expect(textbox).toHaveFocus();
    });

    it('offers no microphone while the voice feature is off', () => {
      openInlinePad();
      renderFlowPad();

      expect(screen.queryByText('speak')).not.toBeInTheDocument();
    });
  });

  describe('dialog chrome', () => {
    it('shows the selected text of a capture, shortened when it is long', () => {
      openChatPad({ selectedText: 'x'.repeat(100) });
      renderFlowPad();

      expect(screen.getByText(`${'x'.repeat(80)}...`)).toBeInTheDocument();
    });

    it('opens a screenshot full size and closes it from the backdrop without closing the pad', async () => {
      openChatPad({ screenshot: 'abc', windowTitle: 'Win' });
      renderFlowPad();

      await click(screen.getByAltText('Win'));
      const fullSize = screen.getByAltText('appshotAlt');
      expect(fullSize).toHaveAttribute('src', 'data:image/jpeg;base64,abc');

      await click(fullSize);
      expect(screen.getByAltText('appshotAlt')).toBeInTheDocument();
      await click(fullSize.parentElement as HTMLElement);
      expect(screen.queryByAltText('appshotAlt')).not.toBeInTheDocument();
      expect(useFlowPadStore.getState().isOpen).toBe(true);
    });

    it('closes the full-size screenshot on Escape and leaves the pad open for the next Escape', async () => {
      openChatPad({ screenshot: 'abc', windowTitle: 'Win' });
      renderFlowPad();
      await click(screen.getByAltText('Win'));
      const keysSeenByDocument: string[] = [];
      const recordKey = (event: KeyboardEvent) => keysSeenByDocument.push(event.key);
      document.addEventListener('keydown', recordKey, true);

      try {
        fireEvent.keyDown(document.body, { key: 'a' });
        expect(screen.getByAltText('appshotAlt')).toBeInTheDocument();
        fireEvent.keyDown(document.body, { key: 'Escape' });
        expect(screen.queryByAltText('appshotAlt')).not.toBeInTheDocument();
        expect(useFlowPadStore.getState().isOpen).toBe(true);
        expect(keysSeenByDocument).toEqual(['a']);

        fireEvent.keyDown(document.body, { key: 'Escape' });
        expect(useFlowPadStore.getState().isOpen).toBe(false);
        expect(keysSeenByDocument).toEqual(['a', 'Escape']);
      } finally {
        document.removeEventListener('keydown', recordKey, true);
      }
    });

    it('does not keep a screenshot full size across pad sessions', async () => {
      openChatPad({ screenshot: 'abc', windowTitle: 'Win' });
      renderFlowPad();
      await click(screen.getByAltText('Win'));
      expect(screen.getByAltText('appshotAlt')).toBeInTheDocument();

      act(() => useFlowPadStore.getState().close());
      act(() => openChatPad({ screenshot: 'abc', windowTitle: 'Win' }));

      expect(screen.queryByAltText('appshotAlt')).not.toBeInTheDocument();
    });

    it('shows the first selected text among several captures', () => {
      openChatPad({}, { selectedText: 'later selection' });
      renderFlowPad();

      expect(screen.getByText('later selection')).toBeInTheDocument();
    });

    it('puts the cursor in the draft box shortly after the pad opens', () => {
      vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
      try {
        openInlinePad();
        renderFlowPad();
        expect(screen.getByRole('textbox')).not.toHaveFocus();

        act(() => {
          vi.advanceTimersByTime(100);
        });

        expect(screen.getByRole('textbox')).toHaveFocus();
      } finally {
        vi.useRealTimers();
      }
    });

    it('closes the pad on Escape', () => {
      openChatPad();
      renderFlowPad();

      fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Escape' });

      expect(useFlowPadStore.getState().isOpen).toBe(false);
    });
  });
});
