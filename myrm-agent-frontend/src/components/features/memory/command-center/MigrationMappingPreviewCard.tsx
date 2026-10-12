/**
 * Migration Mapping and Extracted Fact Preview Card.
 * Displays normalized cognitive memory facts classified into cognitive layers with SHA-256 fingerprints.
 */

import React from 'react';
import {
  Brain,
  CheckCheck,
  Compass,
  FileCode,
  Fingerprint,
  History,
  Tag,
  User,
} from 'lucide-react';
import type { ExtractedMemoryUnitDTO } from '@/services/memory/memoryMigration';

interface MigrationMappingPreviewCardProps {
  units: ExtractedMemoryUnitDTO[];
  isPreviewing: boolean;
}

export const MigrationMappingPreviewCard: React.FC<MigrationMappingPreviewCardProps> = ({
  units,
  isPreviewing,
}) => {
  const getLayerBadge = (layer: string) => {
    switch (layer.toLowerCase()) {
      case 'profile':
        return (
          <span className="inline-flex items-center gap-1 rounded-md bg-purple-500/10 px-2 py-0.5 text-xs font-semibold text-purple-600 dark:text-purple-400">
            <User className="h-3 w-3" aria-hidden="true" />
            用户画像 (Profile)
          </span>
        );
      case 'procedural':
        return (
          <span className="inline-flex items-center gap-1 rounded-md bg-amber-500/10 px-2 py-0.5 text-xs font-semibold text-amber-600 dark:text-amber-400">
            <Compass className="h-3 w-3" aria-hidden="true" />
            规约规则 (Procedural)
          </span>
        );
      case 'episodic':
        return (
          <span className="inline-flex items-center gap-1 rounded-md bg-sky-500/10 px-2 py-0.5 text-xs font-semibold text-sky-600 dark:text-sky-400">
            <History className="h-3 w-3" aria-hidden="true" />
            情景对话 (Episodic)
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 rounded-md bg-emerald-500/10 px-2 py-0.5 text-xs font-semibold text-emerald-600 dark:text-emerald-400">
            <Brain className="h-3 w-3" aria-hidden="true" />
            语义事实 (Semantic)
          </span>
        );
    }
  };

  return (
    <section
      aria-label="认知分层映射与预览"
      className="flex flex-col rounded-xl border border-border bg-card p-5 text-card-foreground shadow-sm"
    >
      <div className="flex items-center justify-between pb-3 border-b border-border/60">
        <div className="flex items-center gap-2">
          <FileCode className="h-4 w-4 text-primary" aria-hidden="true" />
          <h3 className="text-sm font-semibold text-foreground">
            认知分层归一化映射与事实预览
          </h3>
        </div>
        <span className="text-xs text-muted-foreground">
          {isPreviewing ? '正在解析映射...' : `已解析 ${units.length} 个认知事实单元`}
        </span>
      </div>

      <div className="mt-4 space-y-3 max-h-72 overflow-y-auto pr-1">
        {units.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-center text-xs text-muted-foreground">
            <CheckCheck className="h-6 w-6 text-muted-foreground/60 mb-1" aria-hidden="true" />
            <p>暂无预览数据。在上方选择资产或填入内容后点击“预览映射”。</p>
          </div>
        ) : (
          units.map((unit) => (
            <article
              key={`${unit.source_id}-${unit.content_hash}`}
              className="flex flex-col gap-2 rounded-lg border border-border/60 bg-muted/20 p-3.5 hover:bg-muted/30 transition-colors"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  {getLayerBadge(unit.layer)}
                  <span className="text-xs font-mono text-muted-foreground">
                    {unit.source_id}
                  </span>
                </div>
                <div className="flex items-center gap-1 text-xs font-mono text-muted-foreground">
                  <Fingerprint className="h-3 w-3" aria-hidden="true" />
                  <span>SHA: {unit.content_hash.slice(0, 8)}</span>
                </div>
              </div>

              <p className="text-xs text-foreground font-medium leading-relaxed">
                {unit.normalized_text}
              </p>

              {unit.tags && unit.tags.length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5 pt-1">
                  <Tag className="h-3 w-3 text-muted-foreground" aria-hidden="true" />
                  {unit.tags.map((tag) => (
                    <span
                      key={tag}
                      className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </article>
          ))
        )}
      </div>
    </section>
  );
};
