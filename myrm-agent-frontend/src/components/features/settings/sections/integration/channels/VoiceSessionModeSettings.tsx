'use client';

import { useSyncExternalStore } from 'react';
import { useTranslations } from 'next-intl';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { VOICE_SETTING_KEYS, voiceDeviceSettings } from '@/hooks/voice/voiceDeviceSettings';
import SettingsSection from '../../SettingsSection';
import { VoiceFieldRow } from './VoiceFieldRow';
import { DEFAULT_VOICE_FORM, type UpdateVoiceForm, type VoiceFormState } from './voiceFormState';

const DEFAULT_VOICE_MODE = 'audio_only';

const REALTIME_VOICES = ['alloy', 'ash', 'ballad', 'cedar', 'coral', 'echo', 'marin', 'sage', 'shimmer', 'verse'];

const GEMINI_LIVE_MODELS = [
  { value: 'gemini-2.5-flash-preview-native-audio-dialog', label: 'Gemini 2.5 Flash (Native Audio)' },
  { value: 'gemini-2.0-flash-live-001', label: 'Gemini 2.0 Flash Live' },
];

interface VoiceSessionModeSettingsProps {
  form: VoiceFormState;
  update: UpdateVoiceForm;
}

/** How voice conversations are processed; the mode is a device setting, the voice and model it needs are saved config. */
export function VoiceSessionModeSettings({ form, update }: VoiceSessionModeSettingsProps) {
  const t = useTranslations('voice');
  // The mode lives in the device settings the chat's voice button reads, so both always agree.
  const voiceMode = useSyncExternalStore(
    voiceDeviceSettings.subscribe,
    () => voiceDeviceSettings.read(VOICE_SETTING_KEYS.mode) || DEFAULT_VOICE_MODE,
    () => DEFAULT_VOICE_MODE,
  );

  return (
    <SettingsSection title={t('voiceSessionModeTitle')} description={t('voiceSessionModeDesc')}>
      <div className="space-y-4">
        <VoiceFieldRow label={t('voiceMode')} htmlFor="voice-session-mode">
          <Select value={voiceMode} onValueChange={(v) => voiceDeviceSettings.write(VOICE_SETTING_KEYS.mode, v)}>
            <SelectTrigger id="voice-session-mode">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="audio_only">{t('voiceModeAudioOnly')}</SelectItem>
              <SelectItem value="agent_bridge">{t('voiceModeAgentBridge')}</SelectItem>
              <SelectItem value="openai_realtime">{t('voiceModeRealtime')}</SelectItem>
              <SelectItem value="gemini_live">{t('voiceModeGeminiLive')}</SelectItem>
            </SelectContent>
          </Select>
        </VoiceFieldRow>

        {voiceMode === 'openai_realtime' && (
          <VoiceFieldRow label={t('realtimeVoice')} htmlFor="voice-realtime-voice">
            <Select value={form.ttsVoice || 'alloy'} onValueChange={(v) => update({ ttsVoice: v })}>
              <SelectTrigger id="voice-realtime-voice">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {REALTIME_VOICES.map((v) => (
                  <SelectItem key={v} value={v}>
                    {v.charAt(0).toUpperCase() + v.slice(1)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </VoiceFieldRow>
        )}

        {voiceMode === 'gemini_live' && (
          <VoiceFieldRow label={t('geminiLiveModel')} htmlFor="voice-gemini-live-model">
            <Select
              value={form.geminiLiveModel || DEFAULT_VOICE_FORM.geminiLiveModel}
              onValueChange={(v) => update({ geminiLiveModel: v })}
            >
              <SelectTrigger id="voice-gemini-live-model">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {GEMINI_LIVE_MODELS.map((model) => (
                  <SelectItem key={model.value} value={model.value}>
                    {model.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </VoiceFieldRow>
        )}
      </div>
    </SettingsSection>
  );
}
