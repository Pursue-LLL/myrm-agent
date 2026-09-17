/**
 * [INPUT]
 * - @/hooks/voice/useVoiceSession::VoiceSessionState (POS: Full-duplex voice session orchestrator)
 *
 * [OUTPUT]
 * - VoiceBubble: compact persistent voice status pill with expand control.
 *
 * [POS]
 * Minimized voice session surface. Renders nothing when hidden; never takes
 * keyboard focus and never blocks pointer events outside its own pill.
 */

'use client';

import { memo } from 'react';
import { ChevronUp } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { useTranslations } from 'next-intl';
import type { VoiceSessionState } from '@/hooks/voice/useVoiceSession';

interface VoiceBubbleProps {
  visible: boolean;
  sessionState: VoiceSessionState;
  statusText: string;
  speaking: boolean;
  onExpand: () => void;
}

const VoiceBubble = memo(({ visible, sessionState, statusText, speaking, onExpand }: VoiceBubbleProps) => {
  const t = useTranslations('voiceSession');

  if (!visible) {
    return null;
  }

  return (
    <div className="fixed bottom-4 right-4 sm:bottom-6 sm:right-6 z-40 flex items-center gap-2 rounded-full border border-border/50 bg-background/90 backdrop-blur-md pl-3 pr-2 py-2 shadow-lg">
      <span
        className={cn('h-2 w-2 rounded-full shrink-0', speaking ? 'bg-primary animate-pulse' : 'bg-green-500')}
        aria-hidden="true"
      />
      <span className="max-w-[180px] sm:max-w-[240px] truncate text-xs text-foreground/80">
        {statusText || sessionState}
      </span>
      <button
        type="button"
        onClick={onExpand}
        className="p-1.5 rounded-full hover:bg-muted/60 transition-colors text-muted-foreground hover:text-foreground"
        aria-label={t('bubbleExpand')}
      >
        <ChevronUp size={14} />
      </button>
    </div>
  );
});

VoiceBubble.displayName = 'VoiceBubble';

export default VoiceBubble;
