'use client';

import { Volume2, Pause, Square, Loader2 } from 'lucide-react';
import { useTTS, type TTSMode } from '@/hooks/useTTS';
import { useTranslations } from 'next-intl';
import useConfigStore from '@/store/useConfigStore';

const ReadAloud = ({ content }: { content: string }) => {
  const webTtsProvider = useConfigStore((s) => s.webTtsProvider);
  const mode: TTSMode = webTtsProvider === 'browser' ? 'browser' : 'api';
  const provider = mode === 'api' ? webTtsProvider : undefined;

  const { state, toggle, stop, supported } = useTTS({ mode, provider });
  const t = useTranslations('chat');

  if (!supported) return null;

  const isActive = state !== 'idle';

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
