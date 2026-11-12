'use client';

import { memo, useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Skeleton } from '@/components/primitives/skeleton';
import { ConfigLoadError } from '@/components/features/app-shell/config-load-error';
import { IconMic } from '@/components/features/icons/PremiumIcons';
import { toast } from 'sonner';
import { apiRequest } from '@/lib/api';
import { VoiceSessionModeSettings } from './VoiceSessionModeSettings';
import { VoiceSttSettings } from './VoiceSttSettings';
import { VoiceTtsSettings } from './VoiceTtsSettings';
import { DEFAULT_VOICE_FORM, loadVoiceConfig, saveVoiceConfig, type VoiceFormState } from './voiceFormState';

/** `failed`: the saved settings could not be read, so the form stays out of reach instead of showing defaults. */
type LoadStatus = 'loading' | 'ready' | 'failed';

const VoiceSection = memo(() => {
  const t = useTranslations('voice');
  const [form, setForm] = useState<VoiceFormState>(DEFAULT_VOICE_FORM);
  const [status, setStatus] = useState<LoadStatus>('loading');
  const [edgeTtsAvailable, setEdgeTtsAvailable] = useState<boolean | null>(null);
  const [localSttAvailable, setLocalSttAvailable] = useState<boolean | null>(null);
  const [localTtsAvailable, setLocalTtsAvailable] = useState<boolean | null>(null);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchConfig = useCallback(() => {
    loadVoiceConfig().then(
      (config) => {
        setForm(config);
        setStatus('ready');
      },
      () => setStatus('failed'),
    );
  }, []);

  const retryLoad = useCallback(() => {
    setStatus('loading');
    fetchConfig();
  }, [fetchConfig]);

  useEffect(() => {
    fetchConfig();
    apiRequest<{ edge_tts_available?: boolean; local_stt_available?: boolean; local_tts_available?: boolean }>(
      '/health/info',
    )
      .then((info) => {
        setEdgeTtsAvailable(info.edge_tts_available === true);
        setLocalSttAvailable(info.local_stt_available === true);
        setLocalTtsAvailable(info.local_tts_available === true);
      })
      .catch(() => {
        setEdgeTtsAvailable(null);
        setLocalSttAvailable(null);
        setLocalTtsAvailable(null);
      });
    return () => {
      if (saveTimerRef.current) {
        clearTimeout(saveTimerRef.current);
      }
    };
  }, [fetchConfig]);

  const debouncedSave = useCallback(
    (next: VoiceFormState) => {
      if (saveTimerRef.current) {
        clearTimeout(saveTimerRef.current);
      }
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

  if (status === 'loading') {
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

  if (status === 'failed') {
    return <ConfigLoadError onRetry={retryLoad} />;
  }

  const isLocalStt = form.sttProvider === 'local';
  const needsSttApiKey = !isLocalStt;
  const isPiper = form.ttsProvider === 'piper';
  const isVoicebox = form.ttsProvider === 'voicebox';
  const needsTtsApiKey = form.ttsProvider !== 'edge' && !isPiper && !isVoicebox;
  const showEdgeTtsWarning = form.ttsProvider === 'edge' && edgeTtsAvailable === false;
  const showPiperWarning = isPiper && localTtsAvailable === false;
  const showLocalSttWarning = isLocalStt && localSttAvailable === false;

  return (
    <div className="space-y-6" data-testid="voice-settings-panel">
      <div className="flex items-center gap-2">
        <IconMic className="h-5 w-5 text-muted-foreground" />
        <h2 className="text-base font-semibold">{t('sectionTitle')}</h2>
      </div>
      <p className="text-sm text-muted-foreground">{t('sectionDesc')}</p>

      {showLocalSttWarning && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-800 dark:text-amber-300">
          <p className="font-medium">{t('localSttUnavailableTitle')}</p>
          <p className="mt-1 text-xs opacity-90">{t('localSttUnavailableDesc')}</p>
        </div>
      )}

      {showEdgeTtsWarning && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-800 dark:text-amber-300">
          <p className="font-medium">{t('edgeTtsUnavailableTitle')}</p>
          <p className="mt-1 text-xs opacity-90">{t('edgeTtsUnavailableDesc')}</p>
        </div>
      )}

      {showPiperWarning && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-800 dark:text-amber-300">
          <p className="font-medium">{t('piperUnavailableTitle')}</p>
          <p className="mt-1 text-xs opacity-90">{t('piperUnavailableDesc')}</p>
        </div>
      )}

      <VoiceSttSettings
        form={form}
        update={update}
        isLocalStt={isLocalStt}
        needsSttApiKey={needsSttApiKey}
        localSttAvailable={localSttAvailable}
      />
      <VoiceTtsSettings form={form} update={update} needsTtsApiKey={needsTtsApiKey} />
      <VoiceSessionModeSettings form={form} update={update} />
    </div>
  );
});

VoiceSection.displayName = 'VoiceSection';

export default VoiceSection;
