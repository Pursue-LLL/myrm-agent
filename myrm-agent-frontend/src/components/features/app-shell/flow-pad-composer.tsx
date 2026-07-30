/**
 * [INPUT]
 * - SpeechInputButton (POS: 语音转写输入动作)
 * - Button (POS: 发送按钮)
 *
 * [OUTPUT]
 * - FlowPadComposer: FlowPad 输入区。
 *
 * [POS]
 * FlowPad 文本输入子组件。封装 textarea + 语音输入 + 发送按钮，
 * 避免主组件继续膨胀。
 */
import type { KeyboardEvent, MutableRefObject } from 'react';
import { Send } from 'lucide-react';

import { Button } from '@/components/primitives/button';
import { cn } from '@/lib/utils/classnameUtils';
import SpeechInputButton from '@/components/features/message-input-actions/SpeechInputButton';

interface FlowPadComposerProps {
  mode: 'chat' | 'inline';
  hasCaptures: boolean;
  text: string;
  isSubmitting: boolean;
  inlineRouteSwitching: boolean;
  isVoiceEnabled: boolean;
  inputRef: MutableRefObject<HTMLTextAreaElement | null>;
  onTextChange: (value: string) => void;
  onKeyDown: (event: KeyboardEvent) => void;
  onSpeechTranscript: (transcript: string) => void;
  onSubmit: () => void;
  t: (key: string) => string;
}

export function FlowPadComposer({
  mode,
  hasCaptures,
  text,
  isSubmitting,
  inlineRouteSwitching,
  isVoiceEnabled,
  inputRef,
  onTextChange,
  onKeyDown,
  onSpeechTranscript,
  onSubmit,
  t,
}: FlowPadComposerProps) {
  return (
    <div className="p-4 relative">
      <textarea
        ref={inputRef}
        value={text}
        onChange={(event) => onTextChange(event.target.value)}
        onKeyDown={onKeyDown}
        placeholder={
          mode === 'inline'
            ? t('inlinePlaceholder')
            : hasCaptures
              ? t('placeholderWithCapture')
              : t('placeholder')
        }
        className={cn(
          'w-full resize-none border-0 focus:outline-none focus-visible:ring-0',
          'text-base bg-transparent placeholder:text-muted-foreground/40',
          'min-h-[80px] max-h-[200px]',
        )}
        rows={3}
      />
      <div className="flex items-center justify-end gap-2 mt-2">
        <span className="text-[10px] text-muted-foreground/40">
          Enter {t('toSend')} · Esc {t('toCancel')}
        </span>
        {isVoiceEnabled && (
          <SpeechInputButton
            onTranscript={onSpeechTranscript}
            disabled={isSubmitting}
          />
        )}
        <Button
          size="icon"
          className="h-8 w-8 rounded-full"
          onClick={onSubmit}
          disabled={isSubmitting || inlineRouteSwitching || (!text.trim() && !hasCaptures)}
        >
          {isSubmitting ? (
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
          ) : (
            <Send className="h-4 w-4" />
          )}
        </Button>
      </div>
    </div>
  );
}
