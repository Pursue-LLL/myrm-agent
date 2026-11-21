'use client';

/**
 * [INPUT]
 * @/hooks/voice/useTTS::useTTS (POS: Text-to-speech output with browser and API backends)
 * @/store/useConfigStore (POS: User settings mirror; supplies the TTS provider)
 * @/store/useFeatureGateStore (POS: Feature gates; hides API read-aloud while voice interaction is off)
 * @/store/useSpeakingRowStore::useSpeakingRowStore (POS: The message row being read aloud, which the virtual list keeps mounted)
 *
 * [OUTPUT]
 * ReadAloud: Read-aloud controls (speak, pause, resume, stop) of one assistant message.
 *
 * [POS]
 * Read-aloud control of the message action bar. While it speaks it names its row in useSpeakingRowStore so the
 * virtual list keeps the row mounted, and it ends the speech once the row shows other text.
 */

import { useEffect } from 'react';
import { Volume2, Pause, Square, Loader2 } from 'lucide-react';
import { useTTS, type TTSMode } from '@/hooks/voice/useTTS';
import { useTranslations } from 'next-intl';
import useConfigStore from '@/store/useConfigStore';
import { useFeatureGateStore } from '@/store/useFeatureGateStore';
import { useSpeakingRowStore } from '@/store/useSpeakingRowStore';

const ReadAloud = ({ content, messageIndex }: { content: string; messageIndex: number }) => {
  const webTtsProvider = useConfigStore((s) => s.webTtsProvider);
  const isVoiceInteractionEnabled = useFeatureGateStore((s) => s.isEnabled('voice_interaction'));
  const mode: TTSMode = webTtsProvider === 'browser' ? 'browser' : 'api';
  const provider = mode === 'api' ? webTtsProvider : undefined;

  const { state, toggle, stop, supported } = useTTS({ mode, provider });
  const t = useTranslations('chat');
  const isActive = state !== 'idle';

  // The virtual list unmounts rows that scroll out of view and unmounting ends the speech, so a speaking row asks the
  // list to keep it mounted. Rows are reused by index: once the list shifts (older messages load in) this instance can
  // show another message, and speech that belongs to text no longer here has to end rather than sit under a wrong row.
  useEffect(() => {
    if (!isActive) {
      return;
    }
    useSpeakingRowStore.getState().claim(messageIndex);
    return () => {
      useSpeakingRowStore.getState().release(messageIndex);
      stop();
    };
  }, [isActive, content, messageIndex, stop]);

  if (!supported) {
    return null;
  }
  if (mode === 'api' && !isVoiceInteractionEnabled) {
    return null;
  }

  return (
    <span className="inline-flex items-center">
      <button
        onClick={() => toggle(content)}
        disabled={state === 'loading'}
        className="p-2 text-black/70 dark:text-white/70 rounded-xl hover:bg-secondary dark:hover:bg-secondary transition duration-200 hover:text-black dark:hover:text-white disabled:opacity-50"
        aria-label={state === 'playing' ? t('tts.pause') : state === 'paused' ? t('tts.resume') : t('tts.readAloud')}
        title={state === 'playing' ? t('tts.pause') : state === 'paused' ? t('tts.resume') : t('tts.readAloud')}
      >
        {state === 'loading' ? (
          <Loader2 size={18} className="animate-spin" />
        ) : state === 'playing' ? (
          <Pause size={18} />
        ) : (
          <Volume2 size={18} />
        )}
      </button>
      {isActive && state !== 'loading' && (
        <button
          onClick={stop}
          className="p-2 text-black/70 dark:text-white/70 rounded-xl hover:bg-secondary dark:hover:bg-secondary transition duration-200 hover:text-black dark:hover:text-white"
          aria-label={t('tts.stop')}
          title={t('tts.stop')}
        >
          <Square size={16} />
        </button>
      )}
    </span>
  );
};

export default ReadAloud;
