'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { AlertCircle, ExternalLink, RefreshCw } from 'lucide-react';
import { useShallow } from 'zustand/react/shallow';
import useConfigStore from '@/store/useConfigStore';
import useProviderStore from '@/store/useProviderStore';
import { apiRequest } from '@/lib/api';
import type { BuiltinToolId } from '@/store/chat/types';
import type { VoiceConfigValue } from '@/services/config/types';
import {
  collectMediaCredentialWarnings,
  fetchMediaProviderStatus,
  type MediaCredentialWarning,
  type MediaProviderStatus,
} from '@/lib/utils/media';
import { cn } from '@/lib/utils/classnameUtils';

/** What each warning says: nothing usable is chosen yet, or the chosen provider has no key. */
const WARNING_COPY_KEYS: Record<MediaCredentialWarning['tool'], Record<MediaCredentialWarning['reason'], string>> = {
  image_generation: {
    notSelected: 'mediaCredential.imageNotSelected',
    noCredential: 'mediaCredential.imageMissing',
  },
  video_generation: {
    notSelected: 'mediaCredential.videoNotSelected',
    noCredential: 'mediaCredential.videoMissing',
  },
  tts: {
    notSelected: 'mediaCredential.ttsNotSelected',
    noCredential: 'mediaCredential.ttsMissing',
  },
};

interface MediaCredentialInlineProps {
  enabledBuiltinTools: BuiltinToolId[];
  tPanel: (key: string) => string;
}

export const MediaCredentialInline = ({ enabledBuiltinTools, tPanel }: MediaCredentialInlineProps) => {
  const { imageGeneration, videoGeneration } = useConfigStore(
    useShallow((s) => ({
      imageGeneration: s.imageGeneration,
      videoGeneration: s.videoGeneration,
    })),
  );
  const providers = useProviderStore((s) => s.providers);
  const [providerStatuses, setProviderStatuses] = useState<Record<string, MediaProviderStatus>>({});
  const [voice, setVoice] = useState<VoiceConfigValue | null>(null);
  const [loading, setLoading] = useState(false);

  const mediaToolsEnabled =
    enabledBuiltinTools.includes('image_generation') ||
    enabledBuiltinTools.includes('video_generation') ||
    enabledBuiltinTools.includes('tts');

  const refresh = useCallback(async () => {
    if (!mediaToolsEnabled) {
      return;
    }
    setLoading(true);
    try {
      const [statuses, voiceRecord] = await Promise.all([
        fetchMediaProviderStatus(),
        apiRequest<{ value: VoiceConfigValue }>('/config/voice', { silent: true }).catch(() => null),
      ]);
      setProviderStatuses(statuses);
      setVoice(voiceRecord?.value ?? null);
    } finally {
      setLoading(false);
    }
  }, [mediaToolsEnabled]);

  useEffect(() => {
    // oxlint-disable-next-line react/set-state-in-effect -- the effect starts the credential-status request; the loading flag only mirrors that external fetch
    void refresh();
  }, [refresh, enabledBuiltinTools, providers, imageGeneration, videoGeneration]);

  const warnings = useMemo(
    () =>
      collectMediaCredentialWarnings(
        enabledBuiltinTools,
        providers,
        imageGeneration,
        videoGeneration,
        voice,
        providerStatuses,
      ),
    [enabledBuiltinTools, providers, imageGeneration, videoGeneration, voice, providerStatuses],
  );

  if (!mediaToolsEnabled || warnings.length === 0) {
    return null;
  }

  return (
    <div
      className={cn(
        'p-3 rounded-xl border text-xs space-y-2',
        'bg-amber-500/5 border-amber-500/20 text-amber-700 dark:text-amber-400',
      )}
    >
      <div className="flex items-center gap-2 font-medium">
        <AlertCircle size={14} />
        <span>{tPanel('mediaCredential.title')}</span>
      </div>
      <ul className="ml-5 list-disc space-y-0.5">
        {warnings.map(({ tool, reason }) => (
          <li key={tool}>{tPanel(WARNING_COPY_KEYS[tool][reason])}</li>
        ))}
      </ul>
      <p className="text-[10px] opacity-75">{tPanel('mediaCredential.hint')}</p>
      <div className="flex items-center gap-2 pt-1">
        <Link
          href="/settings/models?sub=default"
          className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-amber-500/15 hover:bg-amber-500/25 font-medium transition-colors"
        >
          <ExternalLink size={12} />
          {tPanel('mediaCredential.openSettings')}
        </Link>
        <button
          type="button"
          className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-amber-500/15 hover:bg-amber-500/25 font-medium transition-colors"
          onClick={() => void refresh()}
          disabled={loading}
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          {tPanel('mediaCredential.recheck')}
        </button>
      </div>
    </div>
  );
};
