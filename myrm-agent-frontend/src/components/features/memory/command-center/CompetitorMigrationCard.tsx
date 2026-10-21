/**
 * [INPUT]
 * - @/services/memory/competitorMigration: detectCompetitors, ingestCompetitor
 * - ./CompetitorAssetDetectionView: CompetitorAssetDetectionView
 * - next-intl::useTranslations('memory.commandCenter.competitorMigration')
 *
 * [OUTPUT]
 * - CompetitorMigrationCard: Detect Hermes / Claude Code / Codex data on this machine and import it into Myrm.
 *
 * [POS]
 * Management card in Memory CommandCenter for bringing other assistants' memories, skills and rules over.
 * Whole-app backup and restore lives in Settings (features/instance-archive), not here.
 * Strict typing applied: No `any` types allowed.
 */

'use client';

import React, { useCallback, useState } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { ArrowRight, CircleNotch, MagnifyingGlass, WarningCircle } from '@phosphor-icons/react';

import { Button } from '@/components/primitives/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { CompetitorAssetDetectionView } from './CompetitorAssetDetectionView';
import {
  detectCompetitors,
  ingestCompetitor,
  type CompetitorDetectResponseDTO,
  type CompetitorIngestResponseDTO,
} from '@/services/memory/competitorMigration';

export function CompetitorMigrationCard() {
  const t = useTranslations('memory.commandCenter.competitorMigration');
  const [detecting, setDetecting] = useState(false);
  const [detection, setDetection] = useState<CompetitorDetectResponseDTO | null>(null);
  const [ingestingKey, setIngestingKey] = useState<string | null>(null);
  const [ingestResult, setIngestResult] = useState<CompetitorIngestResponseDTO | null>(null);
  const [errorKey, setErrorKey] = useState<'scan' | 'import' | null>(null);

  const handleDetect = useCallback(async () => {
    setDetecting(true);
    setErrorKey(null);
    try {
      setDetection(await detectCompetitors());
    } catch {
      setErrorKey('scan');
    } finally {
      setDetecting(false);
    }
  }, []);

  const handleIngest = useCallback(async (competitor: string, sourcePath: string) => {
    setIngestingKey(competitor);
    setErrorKey(null);
    try {
      setIngestResult(await ingestCompetitor({ competitor, source_path: sourcePath }));
    } catch {
      setErrorKey('import');
    } finally {
      setIngestingKey(null);
    }
  }, []);

  return (
    <Card className="border-border/70 bg-background/60 shadow-sm backdrop-blur-xl dark:bg-card/40">
      <CardHeader className="space-y-1 pb-4">
        <CardTitle className="text-base font-semibold">{t('title')}</CardTitle>
        <CardDescription className="text-xs leading-relaxed text-muted-foreground">{t('description')}</CardDescription>
      </CardHeader>

      <CardContent className="space-y-4 pt-0">
        {errorKey && (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/10 p-2.5 text-xs text-destructive"
          >
            <WarningCircle className="mt-0.5 h-4 w-4 shrink-0" weight="fill" />
            <span>{t(`errors.${errorKey}`)}</span>
          </div>
        )}

        <Button size="sm" variant="outline" onClick={handleDetect} disabled={detecting} className="h-8 gap-1.5 text-xs">
          {detecting ? (
            <CircleNotch className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <MagnifyingGlass className="h-3.5 w-3.5" />
          )}
          {detecting ? t('scanning') : t('scan')}
        </Button>

        <CompetitorAssetDetectionView
          detection={detection}
          onIngest={handleIngest}
          ingestingKey={ingestingKey}
          ingestResult={ingestResult}
        />

        <Link
          href="/settings/workbench"
          className="inline-flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          {t('backupHint')}
          <span className="inline-flex items-center gap-1 font-medium text-primary">
            {t('backupLink')}
            <ArrowRight className="h-3 w-3" />
          </span>
        </Link>
      </CardContent>
    </Card>
  );
}
