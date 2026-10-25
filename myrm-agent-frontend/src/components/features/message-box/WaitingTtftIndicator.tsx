'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';

/**
 * Pre-first-token waiting indicator.
 *
 * The turn is already routed at this point (the assistant bubble exists), but the model has not
 * emitted a token yet. A static skeleton makes those seconds look like a freeze, so this shows a
 * live elapsed counter next to the breathing dots. It unmounts as soon as content (or reasoning)
 * arrives.
 */
const WaitingTtftIndicator = () => {
  const t = useTranslations('chat');
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    const startedAt = Date.now();
    const timer = setInterval(() => {
      setSeconds(Math.max(0, Math.floor((Date.now() - startedAt) / 1000)));
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <span className="inline-flex items-center gap-2 py-2 text-xs text-muted-foreground" aria-label={t('thinking')}>
      <span className="inline-flex items-center gap-0.5" aria-hidden="true">
        <span className="h-1.5 w-1.5 rounded-full bg-primary/40 animate-[pulse_1s_ease-in-out_infinite]" />
        <span className="h-1.5 w-1.5 rounded-full bg-primary/60 animate-[pulse_1s_ease-in-out_0.2s_infinite]" />
        <span className="h-1.5 w-1.5 rounded-full bg-accent-warm/70 animate-[pulse_1s_ease-in-out_0.4s_infinite]" />
      </span>
      <span className="tabular-nums">{t('reasoningThinking', { seconds })}</span>
    </span>
  );
};

export default WaitingTtftIndicator;
