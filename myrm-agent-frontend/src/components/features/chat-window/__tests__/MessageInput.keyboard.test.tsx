/**
 * [INPUT]
 * - ./messageInputHarness (POS: 输入区集成测试的共享替身)
 * - ../MessageInput (POS: 聊天输入区视图层)
 *
 * [OUTPUT]
 * Vitest: 输入区的键盘分流与文本框接线：回车提交与排队、输入法组合、全屏编辑器、芯片退格、斜杠与 @ 面板、历史弹窗、
 * 打字上报、光标跟踪、占位提示、聚焦预热与失焦取消。
 *
 * [POS]
 * 守住输入区拆分前后的行为：每个用例只经由 DOM 事件与替身记录的调用来断言。
 */
import { act, fireEvent, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  chip,
  expandEditor,
  history,
  hookOf,
  h,
  mention,
  prewarm,
  renderInput,
  setHook,
  slash,
  stubProps,
  installMessageInputHarness,
} from './messageInputHarness';
import type { AgentConfig, File as ChatFile } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';

installMessageInputHarness();

describe('MessageInput keyboard routing', () => {
  it('sends on Enter and keeps Shift+Enter as a newline', () => {
    const { textarea } = renderInput();

    expect(fireEvent.keyDown(textarea, { key: 'Enter' })).toBe(false);
    expect(hookOf().handleSubmit).toHaveBeenCalledTimes(1);

    expect(fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: true })).toBe(true);
    expect(hookOf().handleSubmit).toHaveBeenCalledTimes(1);
  });

  it('leaves Enter to the input method while composing', () => {
    const { textarea } = renderInput();

    fireEvent.keyDown(textarea, { key: 'Enter', isComposing: true });

    expect(hookOf().handleSubmit).not.toHaveBeenCalled();
  });

  it('queues on Alt+Enter while the agent runs and sends otherwise', () => {
    const { textarea, rerender } = renderInput({ loading: true });

    fireEvent.keyDown(textarea, { key: 'Enter', altKey: true });
    expect(hookOf().handleQueueSubmit).toHaveBeenCalledTimes(1);
    expect(hookOf().handleSubmit).not.toHaveBeenCalled();

    fireEvent.keyDown(textarea, { key: 'Enter' });
    expect(hookOf().handleSubmit).toHaveBeenCalledTimes(1);

    rerender();
    fireEvent.keyDown(textarea, { key: 'Enter', altKey: true });
    expect(hookOf().handleSubmit).toHaveBeenCalledTimes(2);
  });

  it('keeps Enter as a newline in the full-screen editor and sends on Ctrl+Enter', () => {
    const { textarea } = renderInput();
    expandEditor();
    expect(stubProps('ComposerPrimaryControls').editorExpanded).toBe(true);

    fireEvent.keyDown(textarea, { key: 'Enter' });
    expect(hookOf().handleSubmit).not.toHaveBeenCalled();

    fireEvent.keyDown(textarea, { key: 'Enter', ctrlKey: true });
    expect(hookOf().handleSubmit).toHaveBeenCalledTimes(1);
  });

  it('closes the full-screen editor on Escape and toggles it on Ctrl/Cmd+Shift+Enter', () => {
    const { textarea } = renderInput();
    expandEditor();

    fireEvent.keyDown(textarea, { key: 'Escape' });
    expect(stubProps('ComposerPrimaryControls').editorExpanded).toBe(false);

    fireEvent.keyDown(textarea, { key: 'Enter', ctrlKey: true, shiftKey: true });
    expect(stubProps('ComposerPrimaryControls').editorExpanded).toBe(true);
    fireEvent.keyDown(textarea, { key: 'Enter', metaKey: true, shiftKey: true });
    expect(stubProps('ComposerPrimaryControls').editorExpanded).toBe(false);
    expect(hookOf().handleSubmit).not.toHaveBeenCalled();
  });

  it('removes the last removable context chip on Backspace in an empty input only', () => {
    const first = vi.fn();
    const last = vi.fn();
    h.chips.current = [chip('a', true, first), chip('b', true, last), chip('c', false)];
    const { textarea, rerender } = renderInput();

    expect(fireEvent.keyDown(textarea, { key: 'Backspace' })).toBe(false);
    expect(last).toHaveBeenCalledTimes(1);
    expect(first).not.toHaveBeenCalled();

    setHook({ inputMessage: 'text' });
    rerender();
    expect(fireEvent.keyDown(textarea, { key: 'Backspace' })).toBe(true);
    expect(last).toHaveBeenCalledTimes(1);
  });

  it('hands every key to the slash palette while it is open', () => {
    slash().showCommandPalette = true;
    const { textarea } = renderInput();

    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(slash().handleKeyDown).toHaveBeenCalledTimes(1);
    expect(hookOf().handleSubmit).not.toHaveBeenCalled();
    expect(stubProps('CommandPalette').open).toBe(true);
  });

  it('lets the @ mention list consume a key only when it reports so', () => {
    mention().isOpen = true;
    const { textarea } = renderInput();

    mention().handleKeyDown.mockReturnValue(true);
    fireEvent.keyDown(textarea, { key: 'Enter' });
    expect(hookOf().handleSubmit).not.toHaveBeenCalled();

    mention().handleKeyDown.mockReturnValue(false);
    fireEvent.keyDown(textarea, { key: 'Enter' });
    expect(hookOf().handleSubmit).toHaveBeenCalledTimes(1);
  });

  it('confirms the history entry on Tab and ignores the other keys it owns', () => {
    history().popup.open = true;
    history().handleKeyDown.mockReturnValue(true);
    history().confirm.mockReturnValue('an earlier message');
    const { textarea } = renderInput();

    fireEvent.keyDown(textarea, { key: 'Tab' });
    expect(hookOf().setInputMessage).toHaveBeenCalledWith('an earlier message');

    fireEvent.keyDown(textarea, { key: 'ArrowDown' });
    expect(history().confirm).toHaveBeenCalledTimes(1);
    expect(hookOf().handleSubmit).not.toHaveBeenCalled();
  });
});

describe('MessageInput textarea', () => {
  it('forwards edits, reports typing at most every five seconds and closes the history popup', () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2031-01-01T00:00:00Z'));
    useChatStore.setState({ chatId: 'chat-1' });
    history().popup.open = true;
    const { textarea } = renderInput();

    fireEvent.change(textarea, { target: { value: 'a' } });
    expect(hookOf().handleInputChange).toHaveBeenCalledTimes(1);
    expect(h.reportUserActivity).toHaveBeenCalledWith('chat-1', 'typing');
    expect(history().close).toHaveBeenCalledTimes(1);

    vi.setSystemTime(new Date('2031-01-01T00:00:04Z'));
    fireEvent.change(textarea, { target: { value: 'ab' } });
    expect(h.reportUserActivity).toHaveBeenCalledTimes(1);

    vi.setSystemTime(new Date('2031-01-01T00:00:06Z'));
    fireEvent.change(textarea, { target: { value: 'abc' } });
    expect(h.reportUserActivity).toHaveBeenCalledTimes(2);
  });

  it('forwards paste to the submit hook', () => {
    const { textarea } = renderInput();

    fireEvent.paste(textarea);

    expect(hookOf().handlePaste).toHaveBeenCalledTimes(1);
  });

  it('tracks the caret for the slash and mention detectors', () => {
    setHook({ inputMessage: 'hello world' });
    const { textarea } = renderInput();

    textarea.setSelectionRange(5, 5);
    fireEvent.keyUp(textarea);
    expect(h.useSlashCommand).toHaveBeenLastCalledWith('hello world', 5);
    expect(h.useReferenceMention).toHaveBeenLastCalledWith('hello world', 5);

    textarea.setSelectionRange(2, 2);
    fireEvent.click(textarea);
    expect(h.useSlashCommand).toHaveBeenLastCalledWith('hello world', 2);
  });

  it('explains what Enter does: idle, full-screen, busy and history hints', () => {
    const { textarea, rerender } = renderInput();
    expect(textarea.placeholder).toBe('input.placeholder');

    expandEditor();
    expect(textarea.placeholder).toBe('input.expandedPlaceholder');
    expandEditor();

    rerender({ loading: true });
    expect(textarea.placeholder).toBe('queue.busyPlaceholder.redirect');

    act(() => useChatStore.setState({ agentConfig: { agentId: 'a', busyInputMode: 'steer' } as AgentConfig }));
    expect(textarea.placeholder).toBe('queue.busyPlaceholder.steer');

    setHook({ files: [{ id: 'f' } as ChatFile] });
    rerender({ loading: true });
    expect(textarea.placeholder).toBe('queue.busyPlaceholder.queue');

    history().ghostText = 'an earlier message';
    rerender({ loading: true });
    expect(textarea.placeholder).toBe('an earlier message');
  });

  it('grows taller in the full-screen editor', () => {
    const { textarea } = renderInput();
    expect(textarea.className).toContain('max-h-24');

    expandEditor();

    expect(textarea.className).toContain('max-h-[75vh]');
  });

  it('prewarms the turn on focus only when the chat is prewarmable', () => {
    const { textarea, rerender } = renderInput();

    fireEvent.focus(textarea);
    expect(prewarm().triggerPrewarm).toHaveBeenCalledTimes(1);

    prewarm().shouldPrewarm = false;
    rerender();
    fireEvent.focus(textarea);
    expect(prewarm().triggerPrewarm).toHaveBeenCalledTimes(1);
  });

  it('cancels the prewarm 120 ms after focus left the composer, but not while it stays inside', () => {
    vi.useFakeTimers();
    setHook({ inputMessage: 'hi' });
    const { textarea } = renderInput();

    fireEvent.blur(textarea);
    vi.advanceTimersByTime(119);
    expect(prewarm().cancelPrewarm).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(prewarm().cancelPrewarm).toHaveBeenCalledTimes(1);

    fireEvent.blur(textarea);
    screen.getByRole('button', { name: 'send' }).focus();
    vi.advanceTimersByTime(120);
    expect(prewarm().cancelPrewarm).toHaveBeenCalledTimes(1);
  });
});
