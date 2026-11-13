'use client';

import { useTranslations } from 'next-intl';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { Switch } from '@/components/primitives/switch';
import SettingsSection from '../../SettingsSection';
import { VoiceFieldRow } from './VoiceFieldRow';
import type { UpdateVoiceForm, VoiceFormState } from './voiceFormState';

const STT_PROVIDERS = [
  { value: 'local', label: 'Local Whisper (Free)' },
  { value: 'openai', label: 'OpenAI Whisper' },
  { value: 'groq', label: 'Groq Whisper' },
  { value: 'deepgram', label: 'Deepgram' },
  { value: 'xai', label: 'xAI Grok STT' },
];

const LOCAL_MODELS = [
  { value: 'tiny', label: 'Tiny (~75 MB)' },
  { value: 'base', label: 'Base (~150 MB)' },
  { value: 'small', label: 'Small (~500 MB)' },
  { value: 'medium', label: 'Medium (~1.5 GB)' },
  { value: 'large-v3', label: 'Large-v3 (~3 GB)' },
];

const LOCAL_DEVICES = [
  { value: 'auto', label: 'Auto' },
  { value: 'cpu', label: 'CPU' },
  { value: 'cuda', label: 'CUDA (GPU)' },
];

interface VoiceSttSettingsProps {
  form: VoiceFormState;
  update: UpdateVoiceForm;
  isLocalStt: boolean;
  needsSttApiKey: boolean;
  /** `null` while the server has not said whether the local engine is installed. */
  localSttAvailable: boolean | null;
}

/** Speech-to-text: the provider and the fields that provider needs. */
export function VoiceSttSettings({
  form,
  update,
  isLocalStt,
  needsSttApiKey,
  localSttAvailable,
}: VoiceSttSettingsProps) {
  const t = useTranslations('voice');

  return (
    <SettingsSection title={t('sttTitle')} description={t('sttDesc')}>
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <Label htmlFor="voice-stt-enabled" className="text-sm font-medium">
            {t('sttEnabled')}
          </Label>
          <Switch id="voice-stt-enabled" checked={form.sttEnabled} onCheckedChange={(v) => update({ sttEnabled: v })} />
        </div>

        {form.sttEnabled && (
          <>
            <VoiceFieldRow label={t('sttProvider')} htmlFor="voice-stt-provider">
              <Select value={form.sttProvider} onValueChange={(v) => update({ sttProvider: v })}>
                <SelectTrigger id="voice-stt-provider">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {STT_PROVIDERS.map((p) => (
                    <SelectItem key={p.value} value={p.value}>
                      {p.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </VoiceFieldRow>

            {isLocalStt && localSttAvailable !== false && (
              <p className="text-xs text-emerald-600 dark:text-emerald-400">{t('sttLocalHint')}</p>
            )}

            {isLocalStt && (
              <>
                <VoiceFieldRow label={t('sttLocalModel')} htmlFor="voice-stt-local-model">
                  <Select value={form.sttLocalModel} onValueChange={(v) => update({ sttLocalModel: v })}>
                    <SelectTrigger id="voice-stt-local-model">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {LOCAL_MODELS.map((m) => (
                        <SelectItem key={m.value} value={m.value}>
                          {m.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </VoiceFieldRow>

                <VoiceFieldRow label={t('sttLocalDevice')} htmlFor="voice-stt-local-device">
                  <Select value={form.sttLocalDevice} onValueChange={(v) => update({ sttLocalDevice: v })}>
                    <SelectTrigger id="voice-stt-local-device">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {LOCAL_DEVICES.map((d) => (
                        <SelectItem key={d.value} value={d.value}>
                          {d.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </VoiceFieldRow>
              </>
            )}

            {needsSttApiKey && (
              <VoiceFieldRow label={t('sttApiKey')} htmlFor="voice-stt-api-key">
                <Input
                  id="voice-stt-api-key"
                  type="password"
                  placeholder={t('sttApiKeyPlaceholder')}
                  value={form.sttApiKey}
                  onChange={(e) => update({ sttApiKey: e.target.value })}
                />
              </VoiceFieldRow>
            )}

            {(form.sttProvider === 'openai' || form.sttProvider === 'xai') && (
              <VoiceFieldRow label={t('sttBaseUrl')} htmlFor="voice-stt-base-url">
                <Input
                  id="voice-stt-base-url"
                  placeholder={t('sttBaseUrlPlaceholder')}
                  value={form.sttBaseUrl}
                  onChange={(e) => update({ sttBaseUrl: e.target.value })}
                />
              </VoiceFieldRow>
            )}

            {!isLocalStt && (
              <VoiceFieldRow label={t('sttModel')} htmlFor="voice-stt-model">
                <Input
                  id="voice-stt-model"
                  placeholder="whisper-1"
                  value={form.sttModel}
                  onChange={(e) => update({ sttModel: e.target.value })}
                />
              </VoiceFieldRow>
            )}

            <VoiceFieldRow label={t('sttLanguage')} htmlFor="voice-stt-language">
              <Input
                id="voice-stt-language"
                placeholder={t('sttLanguagePlaceholder')}
                value={form.sttLanguage}
                onChange={(e) => update({ sttLanguage: e.target.value })}
              />
            </VoiceFieldRow>
          </>
        )}
      </div>
    </SettingsSection>
  );
}
