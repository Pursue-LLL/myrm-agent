'use client';

/**
 * [INPUT]
 * @/services/migrationDiscovery (POS: external assistant auto-discovery client)
 * ./memory-migration-wizard/wizardShared::TranslationFn (POS: translator contract shared by the wizard)
 *
 * [OUTPUT]
 * useMigrationScan: the sources found on this machine or in an uploaded archive, with a rescan and an upload that report their own failures
 *
 * [POS]
 * First step of the memory migration wizard. A local deployment scans the file system; a cloud deployment takes a
 * ZIP of the export instead. Either way the answer replaces what the wizard shows and its source manifest is registered.
 */

import { useCallback, useState } from 'react';
import { toast } from 'sonner';

import {
  discoverMigrationSources,
  invalidateDiscoveryCache,
  registerMigrationSourceManifest,
  uploadMigrationZip,
  type DiscoveryResponse,
} from '@/services/migrationDiscovery';

import type { TranslationFn } from './memory-migration-wizard/wizardShared';

const registerManifestOf = (result: DiscoveryResponse) =>
  registerMigrationSourceManifest(result.source_manifest, { authoritative: result.source_manifest_authoritative });

export function useMigrationScan(t: TranslationFn) {
  const [discovery, setDiscovery] = useState<DiscoveryResponse | null>(null);
  const [scanning, setScanning] = useState(false);
  const [uploading, setUploading] = useState(false);

  const handleScan = useCallback(
    async (force = false) => {
      setScanning(true);
      try {
        if (force) {
          invalidateDiscoveryCache();
        }
        const result = await discoverMigrationSources(force);
        registerManifestOf(result);
        setDiscovery(result);
      } catch {
        toast.error(t('scanFailed'));
      } finally {
        setScanning(false);
      }
    },
    [t],
  );

  const handleUpload = useCallback(
    async (file: File) => {
      setUploading(true);
      try {
        const result = await uploadMigrationZip(file);
        registerManifestOf(result);
        setDiscovery(result);
        if (result.sources.length === 0) {
          toast.info(t('cloudUploadEmpty'));
        }
      } catch {
        toast.error(t('cloudUploadFailed'));
      } finally {
        setUploading(false);
      }
    },
    [t],
  );

  return { discovery, scanning, uploading, handleScan, handleUpload };
}
