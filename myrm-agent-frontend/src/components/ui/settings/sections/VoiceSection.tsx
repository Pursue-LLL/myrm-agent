'use client';

import { memo, useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Skeleton } from '@/components/ui/skeleton';
import { IconMic } from '@/components/ui/icons/PremiumIcons';
import { toast } from 'sonner';
import { apiRequest } from '@/lib/api';
import { Switch } from '@/components/ui/switch';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import SettingsSection from './SettingsSection';

interface VoiceFormState {
  sttEnabled: boolean;
  sttProvider: string;
  sttApiKey: string;
  sttModel: string;
  sttLanguage: string;
  sttLocalModel: string;
  sttLocalDevice: string;
  sttLocalComputeType: string;
  ttsMode: string;
  ttsProvider: string;
  ttsApiKey: string;
  ttsBaseUrl: string;
  ttsVoice: string;
  ttsMaxLength: number;
  ttsSummaryEnabled: boolean;
  ttsSummaryThreshold: number;
  ttsSummaryModel: string;
}

const DEFAULT_STATE: VoiceFormState = {
  sttEnabled: false,
  sttProvider: 'openai',
  sttApiKey: '',
  sttModel: 'whisper-1',
  sttLanguage: '',
  sttLocalModel: 'base',
  sttLocalDevice: 'auto',
  sttLocalComputeType: 'auto',
  ttsMode: 'off',
  ttsProvider: 'edge',
  ttsApiKey: '',
  ttsBaseUrl: '',
  ttsVoice: '',
  ttsMaxLength: 4000,
  ttsSummaryEnabled: true,
  ttsSummaryThreshold: 1500,
  ttsSummaryModel: '',
};

const STT_PROVIDERS = [
  { value: 'local', label: 'Local Whisper (Free)' },
  { value: 'openai', label: 'OpenAI Whisper' },
  { value: 'groq', label: 'Groq Whisper' },
  { value: 'deepgram', label: 'Deepgram' },
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

const TTS_PROVIDERS = [
  { value: 'edge', label: 'Edge TTS (Free)' },
  { value: 'openai', label: 'OpenAI TTS' },
  { value: 'elevenlabs', label: 'ElevenLabs' },
  { value: 'fish_audio', label: 'Fish Audio' },
  { value: 'minimax', label: 'MiniMax' },
];

const REALTIME_VOICES = ['alloy', 'ash', 'ballad', 'cedar', 'coral', 'echo', 'marin', 'sage', 'shimmer', 'verse'];

async function loadVoiceConfig(): Promise<VoiceFormState> {
  try {
    const record = await apiRequest<{ value: VoiceFormState }>('/config/voice');
    return { ...DEFAULT_STATE, ...record.value };
  } catch {
    return DEFAULT_STATE;
  }
}

async function saveVoiceConfig(state: VoiceFormState): Promise<void> {
  await apiRequest('/config/voice', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ value: state, device_id: 'web' }),
  });
}

function FieldRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
      <Label className="text-sm font-medium text-foreground shrink-0">{label}</Label>
      <div className="w-full sm:w-64">{children}</div>
    </div>
  );
}

const VoiceSection = memo(() => {
  const t = useTranslations('voice');
  const [form, setForm] = useState<VoiceFormState>(DEFAULT_STATE);
  const [loading, setLoading] = useState(true);
  const [voiceMode, setVoiceMode] = useState('audio_only');
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    loadVoiceConfig()
      .then(setForm)
      .finally(() => setLoading(false));
    setVoiceMode(localStorage.getItem('voiceSessionMode') || 'audio_only');
    return () => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    };
  }, []);

  const debouncedSave = useCallback(
    (next: VoiceFormState) => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      saveTimerRef.current = setTimeout(async () => {
        try {
          await saveVoiceConfig(next);
          toast.success(t('saved'));
        } catch {
          toast.error(t('saveError'));
        }
      }, 600);
    },
    [t],
  );

  const update = useCallback(
    (patch: Partial<VoiceFormState>) => {
      setForm((prev) => {
        const next = { ...prev, ...patch };
        debouncedSave(next);
        return next;
      });
    },
    [debouncedSave],
  );

  if (loading) {
    return (
      <div className="space-y-5">
        <div className="space-y-1.5">
          <Skeleton className="h-5 w-28" />
          <Skeleton className="h-4 w-52" />
        </div>
        <Skeleton className="h-10 w-full rounded-lg" />
        <Skeleton className="h-10 w-full rounded-lg" />
        <Skeleton className="h-20 w-full rounded-lg" />
      </div>
    );
  }

  const isLocalStt = form.sttProvider === 'local';
  const needsSttApiKey = !isLocalStt;
  const needsTtsApiKey = form.ttsProvider !== 'edge';

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <IconMic className="h-5 w-5 text-muted-foreground" />
        <h2 className="text-base font-semibold">{t('sectionTitle')}</h2>
      </div>
      <p className="text-sm text-muted-foreground">{t('sectionDesc')}</p>

      {/* STT */}
      <SettingsSection title={t('sttTitle')} description={t('sttDesc')}>
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <Label className="text-sm font-medium">{t('sttEnabled')}</Label>
            <Switch checked={form.sttEnabled} onCheckedChange={(v) => update({ sttEnabled: v })} />
          </div>

          {form.sttEnabled && (
            <>
              <FieldRow label={t('sttProvider')}>
                <Select value={form.sttProvider} onValueChange={(v) => update({ sttProvider: v })}>
                  <SelectTrigger>
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
              </FieldRow>

              {isLocalStt && <p className="text-xs text-emerald-600 dark:text-emerald-400">{t('sttLocalHint')}</p>}

              {isLocalStt && (
                <>
                  <FieldRow label={t('sttLocalModel')}>
                    <Select value={form.sttLocalModel} onValueChange={(v) => update({ sttLocalModel: v })}>
                      <SelectTrigger>
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
                  </FieldRow>

                  <FieldRow label={t('sttLocalDevice')}>
                    <Select value={form.sttLocalDevice} onValueChange={(v) => update({ sttLocalDevice: v })}>
                      <SelectTrigger>
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
                  </FieldRow>
                </>
              )}

              {needsSttApiKey && (
                <FieldRow label={t('sttApiKey')}>
                  <Input
                    type="password"
                    placeholder={t('sttApiKeyPlaceholder')}
                    value={form.sttApiKey}
                    onChange={(e) => update({ sttApiKey: e.target.value })}
                  />
                </FieldRow>
              )}

              {!isLocalStt && (
                <FieldRow label={t('sttModel')}>
                  <Input
                    placeholder="whisper-1"
                    value={form.sttModel}
                    onChange={(e) => update({ sttModel: e.target.value })}
                  />
                </FieldRow>
              )}

              <FieldRow label={t('sttLanguage')}>
                <Input
                  placeholder={t('sttLanguagePlaceholder')}
                  value={form.sttLanguage}
                  onChange={(e) => update({ sttLanguage: e.target.value })}
                />
              </FieldRow>
            </>
          )}
        </div>
      </SettingsSection>

      {/* TTS */}
      <SettingsSection title={t('ttsTitle')} description={t('ttsDesc')}>
        <div className="space-y-4">
          <FieldRow label={t('ttsMode')}>
            <Select value={form.ttsMode} onValueChange={(v) => update({ ttsMode: v })}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="off">{t('ttsModeOff')}</SelectItem>
                <SelectItem value="always">{t('ttsModeAlways')}</SelectItem>
                <SelectItem value="inbound">{t('ttsModeInbound')}</SelectItem>
              </SelectContent>
            </Select>
          </FieldRow>

          {form.ttsMode !== 'off' && (
            <>
              <FieldRow label={t('ttsProvider')}>
                <Select value={form.ttsProvider} onValueChange={(v) => update({ ttsProvider: v })}>
                  <SelectTrigger>
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
              </FieldRow>

              {needsTtsApiKey && (
                <FieldRow label={t('ttsApiKey')}>
                  <Input
                    type="password"
                    placeholder={t('ttsApiKeyPlaceholder')}
                    value={form.ttsApiKey}
                    onChange={(e) => update({ ttsApiKey: e.target.value })}
                  />
                </FieldRow>
              )}

              {form.ttsProvider === 'openai' && (
                <FieldRow label={t('ttsBaseUrl')}>
                  <Input
                    placeholder={t('ttsBaseUrlPlaceholder')}
                    value={form.ttsBaseUrl}
                    onChange={(e) => update({ ttsBaseUrl: e.target.value })}
                  />
                </FieldRow>
              )}

              <FieldRow label={t('ttsVoice')}>
                <Input
                  placeholder={t('ttsVoicePlaceholder')}
                  value={form.ttsVoice}
                  onChange={(e) => update({ ttsVoice: e.target.value })}
                />
              </FieldRow>

              <FieldRow label={t('ttsMaxLength')}>
                <Input
                  type="number"
                  min={100}
                  max={10000}
                  value={form.ttsMaxLength}
                  onChange={(e) => update({ ttsMaxLength: Number(e.target.value) || 4000 })}
                />
              </FieldRow>
            </>
          )}
        </div>
      </SettingsSection>

      {/* Summary */}
      {form.ttsMode !== 'off' && (
        <SettingsSection title={t('ttsSummaryTitle')} description={t('ttsSummaryDesc')}>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <Label className="text-sm font-medium">{t('ttsSummaryEnabled')}</Label>
              <Switch checked={form.ttsSummaryEnabled} onCheckedChange={(v) => update({ ttsSummaryEnabled: v })} />
            </div>

            {form.ttsSummaryEnabled && (
              <>
                <FieldRow label={t('ttsSummaryThreshold')}>
                  <Input
                    type="number"
                    min={100}
                    max={10000}
                    value={form.ttsSummaryThreshold}
                    onChange={(e) => update({ ttsSummaryThreshold: Number(e.target.value) || 1500 })}
                  />
                </FieldRow>

                <FieldRow label={t('ttsSummaryModel')}>
                  <Input
                    placeholder={t('ttsSummaryModelPlaceholder')}
                    value={form.ttsSummaryModel}
                    onChange={(e) => update({ ttsSummaryModel: e.target.value })}
                  />
                </FieldRow>
              </>
            )}
          </div>
        </SettingsSection>
      )}

      {/* Voice Session Mode */}
      <SettingsSection
        title={t('voiceSessionModeTitle') ?? 'Voice Session Mode'}
        description={t('voiceSessionModeDesc') ?? 'Choose how voice conversations are processed'}
      >
        <div className="space-y-4">
          <FieldRow label={t('voiceMode') ?? 'Mode'}>
            <Select
              value={voiceMode}
              onValueChange={(v) => {
                setVoiceMode(v);
                localStorage.setItem('voiceSessionMode', v);
                window.dispatchEvent(new StorageEvent('storage'));
              }}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="audio_only">{t('voiceModeAudioOnly') ?? 'Standard (STT → Agent → TTS)'}</SelectItem>
                <SelectItem value="agent_bridge">
                  {t('voiceModeAgentBridge') ?? 'Agent Bridge (Server-side)'}
                </SelectItem>
                <SelectItem value="openai_realtime">
                  {t('voiceModeRealtime') ?? 'Realtime (OpenAI WebRTC, ~200ms)'}
                </SelectItem>
              </SelectContent>
            </Select>
          </FieldRow>

          {voiceMode === 'openai_realtime' && (
            <FieldRow label={t('realtimeVoice') ?? 'Realtime Voice'}>
              <Select value={form.ttsVoice || 'alloy'} onValueChange={(v) => update({ ttsVoice: v })}>
                <SelectTrigger>
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
            </FieldRow>
          )}
        </div>
      </SettingsSection>
    </div>
  );
});

VoiceSection.displayName = 'VoiceSection';

export default VoiceSection;
