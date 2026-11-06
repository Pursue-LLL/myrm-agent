/**
 * [INPUT]
 * - ./messageInputHarness (POS: 输入区集成测试的共享替身)
 * - ../MessageInput (POS: 聊天输入区视图层)
 *
 * [OUTPUT]
 * Vitest: 输入区的发送控件：发送、停止、纠偏、引导、排队，以及语音与附件入口。
 *
 * [POS]
 * 守住输入区拆分前后的行为：每个用例只经由 DOM 与替身记录的属性来断言。
 */
import { act, fireEvent, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
  callStubProp,
  h,
  hookOf,
  installMessageInputHarness,
  renderInput,
  setHook,
  stubProps,
} from './messageInputHarness';
import type { File as ChatFile } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';
import { useFeatureGateStore } from '@/store/useFeatureGateStore';

installMessageInputHarness();

const PENDING_SKILL = { skillNames: ['x'], instruction: null, userText: '' };

function enableVoice(): void {
  act(() => useFeatureGateStore.setState({ enabledFeatures: new Set(['voice_interaction']) }));
}

describe('MessageInput send controls', () => {
  it('disables Send until there is text, a file or a pending skill', () => {
    const { rerender } = renderInput();
    const send = () => screen.getByRole('button', { name: 'send' });
    expect(send()).toBeDisabled();

    setHook({ inputMessage: '  ' });
    rerender();
    expect(send()).toBeDisabled();

    setHook({ inputMessage: 'hi' });
    rerender();
    expect(send()).toBeEnabled();
    fireEvent.click(send());
    expect(hookOf().handleSubmit).toHaveBeenCalledTimes(1);

    setHook({ files: [{ id: 'f' } as ChatFile] });
    rerender();
    expect(send()).toBeEnabled();

    setHook();
    act(() => useChatStore.setState({ pendingExplicitSkillActivation: PENDING_SKILL }));
    expect(send()).toBeEnabled();
  });

  it('offers Stop for a turn the server runs on its own, and disables it while nothing is attached', () => {
    useChatStore.setState({ chatId: 'chat-1', sessionStatuses: { 'chat-1': 'generating' } });
    const { rerender } = renderInput();

    const stop = screen.getByRole('button', { name: 'input.stop' });
    expect(stop).toBeEnabled();
    fireEvent.click(stop);
    expect(hookOf().stopMessage).toHaveBeenCalledTimes(1);

    h.turnStoppable.current = false;
    rerender();
    expect(screen.getByRole('button', { name: 'input.stop' })).toBeDisabled();
  });

  it('shows no Stop button when no turn runs', () => {
    renderInput();

    expect(screen.queryByRole('button', { name: 'input.stop' })).toBeNull();
  });

  it('offers redirect, steer and queue next to Stop once a running turn gets text', () => {
    setHook({ inputMessage: 'next' });
    renderInput({ loading: true });

    fireEvent.click(screen.getByRole('button', { name: 'redirect.send' }));
    fireEvent.click(screen.getByRole('button', { name: 'steer.send' }));
    fireEvent.click(screen.getByRole('button', { name: 'queue.sendLater' }));
    fireEvent.click(screen.getByRole('button', { name: 'input.stop' }));

    expect(hookOf().handleRedirectSubmit).toHaveBeenCalledTimes(1);
    expect(hookOf().handleSteerSubmit).toHaveBeenCalledTimes(1);
    expect(hookOf().handleQueueSubmit).toHaveBeenCalledTimes(1);
    expect(hookOf().handleQueueSubmit).toHaveBeenCalledWith();
    expect(hookOf().stopMessage).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('button', { name: 'send' })).toBeNull();
  });

  it('offers only Stop while a running turn has nothing to send, and a pending skill counts as something', () => {
    const { rerender } = renderInput({ loading: true });
    expect(screen.queryByRole('button', { name: 'redirect.send' })).toBeNull();
    expect(screen.getByRole('button', { name: 'input.stop' })).toBeInTheDocument();

    act(() => useChatStore.setState({ pendingExplicitSkillActivation: PENDING_SKILL }));
    rerender({ loading: true });
    expect(screen.getByRole('button', { name: 'redirect.send' })).toBeInTheDocument();
  });

  it('hides the attach button in fast mode and shows the voice buttons only when the voice gate is on', () => {
    const { rerender } = renderInput();
    expect(h.propsByStub.has('AttachButton')).toBe(true);
    expect(h.propsByStub.has('SpeechInputButton')).toBe(false);

    setHook({ actionMode: 'fast' });
    enableVoice();
    h.propsByStub.clear();
    rerender({ loading: true });

    expect(h.propsByStub.has('AttachButton')).toBe(false);
    expect(stubProps('SpeechInputButton').disabled).toBe(true);
    expect(stubProps('VoiceSessionButton').disabled).toBe(true);
  });

  it('appends a voice transcript to what is typed and refocuses the input', () => {
    enableVoice();
    const { textarea } = renderInput();

    callStubProp('SpeechInputButton', 'onTranscript', 'spoken');
    expect(hookOf().setInputMessage).toHaveBeenLastCalledWith('spoken');

    textarea.value = 'typed';
    callStubProp('SpeechInputButton', 'onTranscript', 'spoken');
    expect(hookOf().setInputMessage).toHaveBeenLastCalledWith('typed spoken');
    expect(document.activeElement).toBe(textarea);
  });

  it('gives both voice buttons the same conversation key terms', () => {
    enableVoice();
    renderInput();

    expect(Array.isArray(stubProps('SpeechInputButton').keyterms)).toBe(true);
    expect(stubProps('VoiceSessionButton').keyterms).toBe(stubProps('SpeechInputButton').keyterms);
  });
});
