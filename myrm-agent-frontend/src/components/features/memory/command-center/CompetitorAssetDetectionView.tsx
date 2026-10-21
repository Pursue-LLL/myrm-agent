/**
 * [INPUT]
 * - @/services/memory/competitorMigration: CompetitorDetectResponseDTO, CompetitorIngestResponseDTO
 * - @/components/primitives/badge: Badge
 * - @/components/primitives/button: Button
 * - next-intl::useTranslations('memory.commandCenter.competitorMigration')
 *
 * [OUTPUT]
 * - CompetitorAssetDetectionView: Renders the assistants found on this machine with one-click import and the import result.
 *
 * [POS]
 * Sub-component for CompetitorMigrationCard under command-center.
 * Strict typing applied: No `any` types allowed.
 */

'use client';

import React from 'react';
import { useTranslations } from 'next-intl';
import { CheckCircle, CircleNotch, DownloadSimple } from '@phosphor-icons/react';

import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import type { CompetitorDetectResponseDTO, CompetitorIngestResponseDTO } from '@/services/memory/competitorMigration';

interface CompetitorAssetDetectionViewProps {
  detection: CompetitorDetectResponseDTO | null;
  onIngest: (competitor: string, sourcePath: string) => Promise<void>;
  ingestingKey: string | null;
  ingestResult: CompetitorIngestResponseDTO | null;
}

type SourceKey = 'hermes' | 'claude_code' | 'codex';

const SOURCES: ReadonlyArray<{
  key: SourceKey;
  name: string;
  pathOf: (d: CompetitorDetectResponseDTO) => string | null | undefined;
}> = [
  { key: 'hermes', name: 'Hermes Agent', pathOf: (d) => d.hermes_dir },
  { key: 'claude_code', name: 'Claude Code', pathOf: (d) => d.claude_code_rule_path },
  { key: 'codex', name: 'Codex / OpenClaw', pathOf: (d) => d.codex_rule_path },
];

export function CompetitorAssetDetectionView({
  detection,
  onIngest,
  ingestingKey,
  ingestResult,
}: CompetitorAssetDetectionViewProps) {
  const t = useTranslations('memory.commandCenter.competitorMigration');

  if (!detection) {
    return (
      <div className="rounded-lg border border-dashed border-border/60 p-4 text-center text-xs text-muted-foreground">
        {t('empty')}
      </div>
    );
  }

  const busy = ingestingKey !== null;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-foreground">
          {t('foundCount', { count: detection.detected_competitors.length })}
        </span>
      </div>

      <div className="grid grid-cols-1 gap-2.5 md:grid-cols-3">
        {SOURCES.map(({ key, name, pathOf }) => {
          const path = pathOf(detection);
          const detected = Boolean(path);
          return (
            <div
              key={key}
              className={`space-y-2 rounded-lg border p-3 text-xs transition-colors ${
                detected ? 'border-primary/40 bg-primary/5' : 'border-border/40 bg-muted/20 opacity-70'
              }`}
            >
              <div className="flex items-center justify-between gap-1.5">
                <span className="font-semibold text-foreground">{name}</span>
                <Badge
                  variant="outline"
                  className={
                    detected
                      ? 'border-emerald-500/40 text-[10px] text-emerald-600 dark:text-emerald-400'
                      : 'border-border text-[10px] text-muted-foreground'
                  }
                >
                  {detected ? t('found') : t('notFound')}
                </Badge>
              </div>
              <p className="text-[11px] leading-relaxed text-muted-foreground">{t(`sources.${key}`)}</p>
              {path && (
                <p className="truncate font-mono text-[10px] text-muted-foreground" title={path}>
                  {path}
                </p>
              )}
              {path && (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={busy}
                  onClick={() => void onIngest(key, path)}
                  className="mt-1 h-7 w-full gap-1 text-[11px]"
                >
                  {ingestingKey === key ? (
                    <CircleNotch className="h-3 w-3 animate-spin" />
                  ) : (
                    <DownloadSimple className="h-3 w-3" />
                  )}
                  {ingestingKey === key ? t('importing') : t('import')}
                </Button>
              )}
            </div>
          );
        })}
      </div>

      {ingestResult && (
        <div className="space-y-2 rounded-lg border border-emerald-500/40 bg-emerald-500/10 p-3 text-xs">
          <output className="flex items-center gap-1.5 font-medium text-emerald-600 dark:text-emerald-400">
            <CheckCircle className="h-4 w-4" weight="fill" />
            <span>{t('resultTitle')}</span>
          </output>
          <div className="flex flex-wrap gap-2">
            <Badge variant="outline" className="border-border bg-background/50">
              {t('memories', { count: ingestResult.imported_memories_count })}
            </Badge>
            <Badge variant="outline" className="border-border bg-background/50">
              {t('skills', { count: ingestResult.imported_skills_count })}
            </Badge>
            <Badge variant="outline" className="border-border bg-background/50">
              {t('rules', { count: ingestResult.imported_rules_count })}
            </Badge>
          </div>
        </div>
      )}
    </div>
  );
}
