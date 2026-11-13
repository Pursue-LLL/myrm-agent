'use client';

import { useTranslations } from 'next-intl';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { Switch } from '@/components/primitives/switch';
import SettingsSection from '../../SettingsSection';
import TemperatureSlider from '../../../default-model/TemperatureSlider';
import { VoiceFieldRow } from './VoiceFieldRow';
import type { UpdateVoiceForm, VoiceFormState } from './voiceFormState';

const TTS_PROVIDERS = [
  { value: 'edge', label: 'Edge TTS (Free)' },
  { value: 'piper', label: 'Piper TTS (Local Offline)' },
  { value: 'voicebox', label: 'Voicebox (Loopback)' },
  { value: 'openai', label: 'OpenAI TTS' },
  { value: 'elevenlabs', label: 'ElevenLabs' },
  { value: 'fish_audio', label: 'Fish Audio' },
  { value: 'minimax', label: 'MiniMax' },
];

interface VoiceTtsSettingsProps {
  form: VoiceFormState;
  update: UpdateVoiceForm;
  needsTtsApiKey: boolean;
}

/**
 * Text-to-speech and, once it is on, the automatic summary of long replies before they are synthesized.
 * Both sections are direct children of the page's spaced column, so this returns a fragment rather than a wrapper.
 */
export function VoiceTtsSettings({ form, update, needsTtsApiKey }: VoiceTtsSettingsProps) {
  const t = useTranslations('voice');

  return (
    <>
      <SettingsSection title={t('ttsTitle')} description={t('ttsDesc')}>
        <div className="space-y-4">
          <VoiceFieldRow label={t('ttsMode')} htmlFor="voice-tts-mode">
            <Select value={form.ttsMode} onValueChange={(v) => update({ ttsMode: v })}>
              <SelectTrigger id="voice-tts-mode">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="off">{t('ttsModeOff')}</SelectItem>
                <SelectItem value="always">{t('ttsModeAlways')}</SelectItem>
                <SelectItem value="inbound">{t('ttsModeInbound')}</SelectItem>
              </SelectContent>
            </Select>
          </VoiceFieldRow>

          {form.ttsMode !== 'off' && (
            <>
              <VoiceFieldRow label={t('ttsProvider')} htmlFor="voice-tts-provider">
                <Select value={form.ttsProvider} onValueChange={(v) => update({ ttsProvider: v })}>
                  <SelectTrigger id="voice-tts-provider">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {TTS_PROVIDERS.map((p) => (
                      <SelectItem key={p.value} value={p.value}>
                        {p.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </VoiceFieldRow>

              {needsTtsApiKey && (
                <VoiceFieldRow label={t('ttsApiKey')} htmlFor="voice-tts-api-key">
                  <Input
                    id="voice-tts-api-key"
                    type="password"
                    placeholder={t('ttsApiKeyPlaceholder')}
                    value={form.ttsApiKey}
                    onChange={(e) => update({ ttsApiKey: e.target.value })}
                  />
                </VoiceFieldRow>
              )}

              {(form.ttsProvider === 'openai' || form.ttsProvider === 'voicebox') && (
                <VoiceFieldRow label={t('ttsBaseUrl')} htmlFor="voice-tts-base-url">
                  <Input
                    id="voice-tts-base-url"
                    placeholder={form.ttsProvider === 'voicebox' ? 'http://127.0.0.1:8000' : t('ttsBaseUrlPlaceholder')}
                    value={form.ttsBaseUrl}
                    onChange={(e) => update({ ttsBaseUrl: e.target.value })}
                  />
                </VoiceFieldRow>
              )}

              <VoiceFieldRow label={t('ttsVoice')} htmlFor="voice-tts-voice">
                <Input
                  id="voice-tts-voice"
                  placeholder={t('ttsVoicePlaceholder')}
                  value={form.ttsVoice}
                  onChange={(e) => update({ ttsVoice: e.target.value })}
                />
              </VoiceFieldRow>

              <TemperatureSlider
                value={form.ttsSpeed}
                onChange={(v) => update({ ttsSpeed: v })}
                min={0.5}
                max={2.0}
                step={0.1}
                label={t('ttsSpeed')}
                minLabel={t('ttsSpeedSlow')}
                maxLabel={t('ttsSpeedFast')}
                hint={t('ttsSpeedHint')}
              />

              <TemperatureSlider
                value={form.ttsPitch}
                onChange={(v) => update({ ttsPitch: v })}
                min={-10}
                max={10}
                step={1}
                label={t('ttsPitch')}
                minLabel={t('ttsPitchLow')}
                maxLabel={t('ttsPitchHigh')}
                hint={t('ttsPitchHint')}
              />

              <VoiceFieldRow label={t('ttsMaxLength')} htmlFor="voice-tts-max-length">
                <Input
                  id="voice-tts-max-length"
                  type="number"
                  min={100}
                  max={10000}
                  value={form.ttsMaxLength}
                  onChange={(e) => update({ ttsMaxLength: Number(e.target.value) || 4000 })}
                />
              </VoiceFieldRow>
            </>
          )}
        </div>
      </SettingsSection>

      {form.ttsMode !== 'off' && (
        <SettingsSection title={t('ttsSummaryTitle')} description={t('ttsSummaryDesc')}>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <Label htmlFor="voice-tts-summary-enabled" className="text-sm font-medium">
                {t('ttsSummaryEnabled')}
              </Label>
              <Switch
                id="voice-tts-summary-enabled"
                checked={form.ttsSummaryEnabled}
                onCheckedChange={(v) => update({ ttsSummaryEnabled: v })}
              />
            </div>

            {form.ttsSummaryEnabled && (
              <>
                <VoiceFieldRow label={t('ttsSummaryThreshold')} htmlFor="voice-tts-summary-threshold">
                  <Input
                    id="voice-tts-summary-threshold"
                    type="number"
                    min={100}
                    max={10000}
                    value={form.ttsSummaryThreshold}
                    onChange={(e) => update({ ttsSummaryThreshold: Number(e.target.value) || 1500 })}
                  />
                </VoiceFieldRow>

                <VoiceFieldRow label={t('ttsSummaryModel')} htmlFor="voice-tts-summary-model">
                  <Input
                    id="voice-tts-summary-model"
                    placeholder={t('ttsSummaryModelPlaceholder')}
                    value={form.ttsSummaryModel}
                    onChange={(e) => update({ ttsSummaryModel: e.target.value })}
                  />
                </VoiceFieldRow>
              </>
            )}
          </div>
        </SettingsSection>
      )}
    </>
  );
}
