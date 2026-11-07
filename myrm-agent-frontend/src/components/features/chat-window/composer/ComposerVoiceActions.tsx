'use client';

/**
 * [INPUT]
 * - @/components/features/message-input-actions/{SpeechInputButton,VoiceSessionButton} (POS: 语音听写与语音会话入口)
 * - @/store/useChatStore::useChatStore (POS: 聊天状态总线，会话消息)
 * - ../speechKeyterms::extractKeyterms (POS: 供 STT 做识别偏置的领域热词)
 *
 * [OUTPUT]
 * - ComposerVoiceActions: 输入区右侧的听写按钮与语音会话按钮。
 *
 * [POS]
 * 两个按钮共用同一份热词：识别器偏向会话里已出现的术语。热词只在语音功能开启、本组件挂载时才计算，
 * 听写结果追加到输入框现有文字之后并把焦点还给输入框。是否开启语音由调用方决定。
 */
import { type RefObject, useCallback, useMemo } from 'react';

import SpeechInputButton from '@/components/features/message-input-actions/SpeechInputButton';
import VoiceSessionButton from '@/components/features/message-input-actions/VoiceSessionButton';
import useChatStore from '@/store/useChatStore';

import { extractKeyterms } from '../speechKeyterms';

interface ComposerVoiceActionsProps {
  inputRef: RefObject<HTMLTextAreaElement | null>;
  setInputMessage: (text: string) => void;
  disabled: boolean;
}

export function ComposerVoiceActions({ inputRef, setInputMessage, disabled }: ComposerVoiceActionsProps) {
  const messages = useChatStore((s) => s.messages);
  const keyterms = useMemo(() => extractKeyterms(messages), [messages]);

  const handleTranscript = useCallback(
    (text: string) => {
      const currentMessage = inputRef.current?.value || '';
      setInputMessage(currentMessage ? `${currentMessage} ${text}` : text);
      inputRef.current?.focus();
    },
    [setInputMessage, inputRef],
  );

  return (
    <>
      <SpeechInputButton onTranscript={handleTranscript} disabled={disabled} keyterms={keyterms} />
      <VoiceSessionButton disabled={disabled} keyterms={keyterms} />
    </>
  );
}
