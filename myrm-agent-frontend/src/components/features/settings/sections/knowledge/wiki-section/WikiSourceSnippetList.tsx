'use client';

/**
 * [INPUT] @/services/wikiService (POS: 证据片段类型与资产缩略图地址), @/services/wiki/sectionLabels::resolveWikiSectionLabel (POS: 区块标题本地化), MessageSources 文案
 * [OUTPUT] WikiSourceSnippetList: 问答的证据片段列表: 每条显示标题、层级徽标、区块、路径、摘录、claim 证据位置与快照状态, 资产命中带缩略图; 点击把该片段交给抽屉
 * [POS] 问答结果里的证据来源; 没有片段时不渲染。
 */

import { useTranslations } from 'next-intl';
import { buildWikiAssetUrl, type WikiSourceLevel, type WikiSourceSnippet } from '@/services/wikiService';
import { resolveWikiSectionLabel } from '@/services/wiki/sectionLabels';
import type { WikiSnippetDrawerState } from './types';

function normalizeWikiLevel(level: string | undefined): WikiSourceLevel | undefined {
  if (level === 'L0' || level === 'L1' || level === 'L2') {
    return level;
  }
  return undefined;
}

interface WikiSourceSnippetListProps {
  sourceSnippets: WikiSourceSnippet[];
  agentScopeId: string | null;
  onOpenSnippet: (state: WikiSnippetDrawerState) => void;
}

export function WikiSourceSnippetList({ sourceSnippets, agentScopeId, onOpenSnippet }: WikiSourceSnippetListProps) {
  const t = useTranslations('settings.wiki');
  const tSources = useTranslations('MessageSources');

  if (sourceSnippets.length === 0) {
    return null;
  }

  return (
    <div className="mt-4 space-y-2">
      <div className="text-sm font-medium">{tSources('sources_title')}</div>
      <div className="space-y-2">
        {sourceSnippets.map((snippet, idx) => {
          const level = normalizeWikiLevel(snippet.level);
          const levelLabel = level
            ? level === 'L0'
              ? tSources('kb_level_l0')
              : level === 'L1'
                ? tSources('kb_level_l1')
                : tSources('kb_level_l2')
            : null;
          const cardTitle = snippet.name || snippet.path;
          const sectionLabel = resolveWikiSectionLabel(snippet.section || undefined, tSources);
          const thumbnailUrl =
            snippet.hit_kind === 'asset' && snippet.asset_filename
              ? buildWikiAssetUrl(snippet.asset_filename, agentScopeId)
              : null;
          return (
            <button
              key={`${snippet.path}-${idx}`}
              type="button"
              className="w-full text-left rounded-lg border border-border/60 bg-card px-3 py-2 hover:bg-muted transition-colors"
              onClick={() =>
                onOpenSnippet({
                  open: true,
                  title: cardTitle,
                  section: sectionLabel,
                  snippet: snippet.snippet,
                  level,
                  snapshotStatus: snippet.snapshot_status,
                  claimStatus: snippet.claim_status,
                  claimConfidence: snippet.claim_confidence,
                  claimText: snippet.claim_text,
                  resourceUri: snippet.resource_uri,
                  supersededFromUri: snippet.superseded_from_uri,
                  thumbnailUrl,
                })
              }
            >
              <div className="flex items-start gap-3">
                {thumbnailUrl ? (
                  // oxlint-disable-next-line next/no-img-element -- thumbnails are served by the backend asset endpoint, which next/image cannot optimize
                  <img
                    src={thumbnailUrl}
                    alt=""
                    className="h-14 w-14 shrink-0 rounded-md border border-border/60 object-cover bg-muted"
                  />
                ) : null}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium truncate">{cardTitle}</span>
                    {levelLabel && (
                      <span className="text-[10px] leading-4 px-1.5 py-0.5 rounded-full bg-amber-500/15 text-amber-700 dark:text-amber-300 border border-amber-500/30">
                        {levelLabel}
                      </span>
                    )}
                  </div>
                  {sectionLabel && <div className="mt-1 text-xs text-muted-foreground">{sectionLabel}</div>}
                  {snippet.path && (
                    <div className="mt-1 text-[11px] text-muted-foreground truncate font-mono">{snippet.path}</div>
                  )}
                  {snippet.snippet && (
                    <p className="mt-2 text-xs text-muted-foreground line-clamp-3">{snippet.snippet}</p>
                  )}
                  {snippet.claim_id && (
                    <p className="mt-1 text-[11px] text-primary/80 font-mono truncate">
                      {snippet.evidence_path}
                      {snippet.line_range ? ` · L${snippet.line_range}` : ''}
                    </p>
                  )}
                  {snippet.snapshot_status === 'verified' && (
                    <p className="mt-1 text-[11px] text-emerald-700 dark:text-emerald-300">
                      {t('evidenceSnapshotVerified')}
                    </p>
                  )}
                  {snippet.snapshot_status === 'stale' && (
                    <p className="mt-1 text-[11px] text-amber-700 dark:text-amber-300">{t('evidenceSnapshotStale')}</p>
                  )}
                  {snippet.snapshot_status === 'missing' && snippet.evidence_path && (
                    <p className="mt-1 text-[11px] text-muted-foreground">{t('evidenceSnapshotMissing')}</p>
                  )}
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
