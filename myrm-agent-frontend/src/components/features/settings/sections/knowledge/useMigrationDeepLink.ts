'use client';

/**
 * [INPUT]
 * @/services/migrationDiscovery (POS: external assistant auto-discovery client)
 * ./memory-migration-wizard/wizardShared::TranslationFn,WizardStep (POS: translator contract and step names shared by the wizard)
 *
 * [OUTPUT]
 * useMigrationDeepLink: opens the preview of the source named by ?source= once the scan has found it
 *
 * [POS]
 * Lets a link (for example from the chat banner) land on the preview of one assistant instead of the source list.
 * A source it cannot open is reported once, and coming back to the scan step never re-opens it; only a preview that
 * failed to start is tried again.
 */

import { useSearchParams } from 'next/navigation';
import { useEffect, useRef } from 'react';
import { toast } from 'sonner';

import { canDeepLinkMigrationSource, type DiscoveryResponse, type ExternalSource } from '@/services/migrationDiscovery';

import type { TranslationFn, WizardStep } from './memory-migration-wizard/wizardShared';

interface MigrationDeepLinkOptions {
  discovery: DiscoveryResponse | null;
  scanning: boolean;
  previewing: boolean;
  step: WizardStep;
  /** Opens the preview of a source; resolves false when it could not be opened, which allows one more try. */
  onPreview: (source: ExternalSource) => Promise<boolean>;
  t: TranslationFn;
}

export function useMigrationDeepLink({
  discovery,
  scanning,
  previewing,
  step,
  onPreview,
  t,
}: MigrationDeepLinkOptions) {
  const deepLinkSourceId = useSearchParams().get('source')?.trim().toLowerCase() ?? '';
  const attemptedRef = useRef(false);

  useEffect(() => {
    if (!deepLinkSourceId || !discovery || scanning || previewing || step !== 'scan' || attemptedRef.current) {
      return;
    }

    if (!canDeepLinkMigrationSource(deepLinkSourceId)) {
      attemptedRef.current = true;
      toast.error(t('deepLinkSourceInvalid'));
      return;
    }

    const matched = discovery.sources.find((source) => source.competitor.toLowerCase() === deepLinkSourceId);
    if (!matched) {
      attemptedRef.current = true;
      toast.error(t('deepLinkSourceNotFound'));
      return;
    }

    attemptedRef.current = true;
    void onPreview(matched).then((ok) => {
      if (!ok) {
        attemptedRef.current = false;
      }
    });
  }, [deepLinkSourceId, discovery, scanning, previewing, step, onPreview, t]);
}
