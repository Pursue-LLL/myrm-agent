/**
 * [INPUT]
 * - @/hooks/useVoiceSession::useVoiceSession (POS: Full-duplex voice session orchestrator)
 * - @/components/ui/voice/VoiceSessionOverlay (POS: Full-screen voice session UI)
 * - @/store/useChatStore::useChatStore (POS: Chat state bus)
 *
 * [OUTPUT]
 * - VoiceSessionButton: Trigger button for full-duplex voice session with overlay.
 *
 * [POS]
 * Voice session trigger. Renders a mic-session button that opens VoiceSessionOverlay,
 * bridging useVoiceSession with the chat store for message sending and TTS playback.
 * Supports both audio_only (frontend Agent roundtrip) and agent_bridge (server-side Agent) modes.
 */

'use client';

import { memo, useCallback, useEffect, useRef, useState } from 'react';
import { HeadsetIcon } from 'hugeicons-react';
import { cn } from '@/lib/utils/classnameUtils';
import { useTranslations } from 'next-intl';
import { useVoiceSession, type VoiceSessionMode } from '@/hooks/useVoiceSession';
import VoiceSessionOverlay from '@/components/ui/voice/VoiceSessionOverlay';
import Tooltip from '@/components/ui/settings/Tooltip';
import useChatStore from '@/store/useChatStore';

const VOICE_SESSION_KEY = 'voiceSessionEnabled';
const VOICE_FULL_DUPLEX_KEY = 'voiceFullDuplexEnabled';
const VOICE_AGENT_BRIDGE_KEY = 'voiceAgentBridgeEnabled';
const VOICE_MODE_KEY = 'voiceSessionMode';

function resolveVoiceMode(): VoiceSessionMode {
  const stored = localStorage.getItem(VOICE_MODE_KEY);
  if (stored === 'openai_realtime' || stored === 'agent_bridge' || stored === 'audio_only') {
    return stored;
  }
  return localStorage.getItem(VOICE_AGENT_BRIDGE_KEY) === 'true' ? 'agent_bridge' : 'audio_only';
}

interface VoiceSessionButtonProps {
  disabled?: boolean;
  keyterms?: string[];
}

const VoiceSessionButton = memo(({ disabled = false, keyterms }: VoiceSessionButtonProps) => {
  const t = useTranslations('voiceSession');
  const sendMessage = useChatStore((s) => s.sendMessage);
  const chatId = useChatStore((s) => s.chatId);
  const agentId = useChatStore((s) => s.agentConfig?.agentId);

  const [voiceEnabled, setVoiceEnabled] = useState(false);
  const [fullDuplex, setFullDuplex] = useState(true);
  const [voiceMode, setVoiceMode] = useState<VoiceSessionMode>('audio_only');

  useEffect(() => {
    setVoiceEnabled(localStorage.getItem(VOICE_SESSION_KEY) === 'true');
    setFullDuplex(localStorage.getItem(VOICE_FULL_DUPLEX_KEY) !== 'false');
    setVoiceMode(resolveVoiceMode());

    const handler = () => {
      setVoiceEnabled(localStorage.getItem(VOICE_SESSION_KEY) === 'true');
      setFullDuplex(localStorage.getItem(VOICE_FULL_DUPLEX_KEY) !== 'false');
      setVoiceMode(resolveVoiceMode());
    };
    window.addEventListener('storage', handler);
    return () => window.removeEventListener('storage', handler);
  }, []);

  const handleSendMessage = useCallback(
    (text: string) => {
      if (text.trim()) {
        void sendMessage(text);
      }
    },
    [sendMessage],
  );

  const voice = useVoiceSession({
    enabled: voiceEnabled,
    autoSend: true,
    onSendMessage: handleSendMessage,
    keyterms,
    fullDuplex,
    mode: voiceMode,
    agentId: agentId ?? undefined,
    chatId: chatId ?? undefined,
  });

  const lastAssistantRef = useRef<string | null>(null);
  const messages = useChatStore((s) => s.messages);
  const loading = useChatStore((s) => s.loading);

  // In audio_only mode: watch messages store for assistant replies → TTS
  useEffect(() => {
    if (voiceMode === 'agent_bridge') return;
    if (!voice.isActive || loading) return;

    const lastMsg = messages[messages.length - 1];
    if (!lastMsg || lastMsg.role !== 'assistant') return;

    const content = lastMsg.content;
    if (content && content !== lastAssistantRef.current && content.length > 10) {
      lastAssistantRef.current = content;
      voice.speakResponse(content);
    }
  }, [messages, loading, voice, voiceMode]);

  const handleToggle = useCallback(() => {
    if (voice.isActive) {
      voice.stopSession();
    } else {
      voice.startSession();
    }
  }, [voice]);

  if (!voiceEnabled) return null;

  return (
    <>
      <Tooltip content={voice.isActive ? t('stopSession') : t('startSession')}>
        <button
          type="button"
          onClick={handleToggle}
          disabled={disabled}
          className={cn(
            'relative flex items-center justify-center w-8 h-8 rounded-full transition duration-200',
            voice.isActive
              ? 'bg-primary/15 dark:bg-primary/20 text-primary hover:bg-primary/25 dark:hover:bg-primary/30'
              : 'bg-[#fdfdf8] dark:bg-muted/60 hover:bg-[#e8e8e0] dark:hover:bg-muted/80 text-black/70 dark:text-white/70 hover:text-black dark:hover:text-white',
            disabled && 'opacity-50 cursor-not-allowed',
          )}
          aria-label={voice.isActive ? t('stopSession') : t('startSession')}
        >
          <HeadsetIcon size={16} />
          {voice.isActive && (
            <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-green-500 animate-pulse" />
          )}
        </button>
      </Tooltip>

      <VoiceSessionOverlay
        isOpen={voice.isActive}
        sessionState={voice.sessionState}
        audioLevel={voice.audioLevel}
        interimText={voice.interimText}
        onClose={voice.stopSession}
        onInterrupt={voice.interruptTTS}
        agentResponseText={voice.agentResponseText}
        agentToolName={voice.agentToolName}
        isAgentBridge={voiceMode === 'agent_bridge'}
        voiceMode={voiceMode}
      />
    </>
  );
});

VoiceSessionButton.displayName = 'VoiceSessionButton';

export default VoiceSessionButton;
