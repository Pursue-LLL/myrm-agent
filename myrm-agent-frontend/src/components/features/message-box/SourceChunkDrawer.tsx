/**
 * SourceChunkDrawer — KB 引用原文片段 Drawer
 *
 * [INPUT]
 * lib/wiki/claimStatusDisplay.ts (POS: Wiki claim 状态展示纯函数)
 * services/wikiEvidenceMetrics.ts (POS: 证据展开/停留埋点)
 *
 * [POS]
 * 当用户点击 KB citation 时，以右侧 Sheet 展示原文 snippet、分层标签（L0/L1/L2）、
 * snapshot 三态与 claim_status badge（仅 contested/unsupported），以及 structured claim / evidence excerpt 分区。
 */
'use client';

import React, { useEffect, useMemo, useRef } from 'react';
import { BookOpen, X } from 'lucide-react';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/primitives/sheet';
import { useLocale, useTranslations } from 'next-intl';
import { WikiSourceLevel } from '@/store/chat/types';
import { recordSnippetClose, recordSnippetOpen, type WikiEvidenceSurface } from '@/services/wiki/evidenceMetrics';
import {
  claimStatusClass,
  claimStatusLabel,
  formatClaimConfidence,
  shouldShowClaimConfidence,
  shouldShowClaimStatusBadge,
  type WikiClaimStatus,
  type WikiClaimStatusLabels,
} from '@/lib/wiki/claimStatusDisplay';
import { cn } from '@/lib/utils/classnameUtils';

interface SourceChunkDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  section?: string;
  snippet: string;
  level?: WikiSourceLevel;
  snapshotStatus?: 'verified' | 'stale' | 'missing';
  claimStatus?: WikiClaimStatus;
  claimConfidence?: number;
  claimText?: string;
  resourceUri?: string;
  supersededFromUri?: string;
  thumbnailUrl?: string | null;
  surface?: WikiEvidenceSurface;
  contextKey?: string;
}

function renderSnippetParagraphs(text: string, maxSegments: number = 3): React.ReactNode[] {
  if (!text) {return [];}

  const sentences = text.split(/(?<=[。.!?！？\n])\s*/);
  const segments = sentences.slice(0, maxSegments);
  return segments.map((seg, i) => (
    <p key={i} className="text-sm text-foreground/90 leading-relaxed mb-2 last:mb-0">
      {seg}
    </p>
  ));
}

const SourceChunkDrawer: React.FC<SourceChunkDrawerProps> = React.memo(
  ({ open, onOpenChange, title, section, snippet, level, snapshotStatus, claimStatus, claimConfidence, claimText, resourceUri, supersededFromUri, thumbnailUrl, surface = 'chat', contextKey }) => {
    const t = useTranslations('MessageSources');
    const tWiki = useTranslations('settings.wiki');
    const tWikiConcepts = useTranslations('settings.wiki.concepts');
    const locale = useLocale();
    const claimStatusLabels: WikiClaimStatusLabels = {
      supported: tWikiConcepts('claimStatusSupported'),
      contested: tWikiConcepts('claimStatusContested'),
      unsupported: tWikiConcepts('claimStatusUnsupported'),
      unknown: tWikiConcepts('claimStatusUnknown'),
    };
    const renderedSnippet = useMemo(() => renderSnippetParagraphs(snippet), [snippet]);
    const openStartedAtRef = useRef<number | null>(null);
    const wasOpenRef = useRef(false);

    useEffect(() => {
      if (open && !wasOpenRef.current) {
        openStartedAtRef.current = Date.now();
        recordSnippetOpen(surface, level, contextKey, snapshotStatus);
      } else if (!open && wasOpenRef.current) {
        const startedAt = openStartedAtRef.current;
        const dwellMs = startedAt !== null ? Date.now() - startedAt : 0;
        recordSnippetClose(surface, dwellMs, contextKey);
        openStartedAtRef.current = null;
      }
      wasOpenRef.current = open;
    }, [contextKey, level, open, surface]);

    useEffect(() => {
      return () => {
        if (!wasOpenRef.current) {
          return;
        }
        const startedAt = openStartedAtRef.current;
        const dwellMs = startedAt !== null ? Date.now() - startedAt : 0;
        recordSnippetClose(surface, dwellMs, contextKey);
        wasOpenRef.current = false;
        openStartedAtRef.current = null;
      };
    }, [contextKey, surface]);

    const levelLabel = useMemo(() => {
      if (level === 'L0') {return t('kb_level_l0');}
      if (level === 'L1') {return t('kb_level_l1');}
      if (level === 'L2') {return t('kb_level_l2');}
      return '';
    }, [level, t]);

    const showStructuredClaim = useMemo(() => {
      const normalizedClaim = claimText?.trim();
      if (!normalizedClaim) {
        return false;
      }
      return normalizedClaim !== snippet.trim();
    }, [claimText, snippet]);

    const excerptLabel = showStructuredClaim ? tWiki('evidenceExcerpt') : t('source_excerpt');

    return (
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent side="right" hideCloseButton className="w-full sm:max-w-md flex flex-col p-0">
          <SheetHeader className="px-5 pt-5 pb-3 border-b border-border/50 flex-shrink-0">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5 min-w-0">
                <div className="bg-amber-500/20 flex items-center justify-center w-8 h-8 rounded-full flex-shrink-0">
                  <BookOpen size={16} className="text-amber-600 dark:text-amber-400" />
                </div>
                <div className="min-w-0">
                  <SheetTitle className="text-base truncate">{title}</SheetTitle>
                  <div className="flex flex-wrap items-center gap-2 mt-0.5 min-w-0">
                    {section && <p className="text-xs text-muted-foreground truncate">§ {section}</p>}
                    {levelLabel && (
                      <span className="shrink-0 text-[10px] leading-4 px-1.5 py-0.5 rounded-full bg-amber-500/15 text-amber-700 dark:text-amber-300 border border-amber-500/30">
                        {levelLabel}
                      </span>
                    )}
                    {shouldShowClaimStatusBadge(claimStatus) && (
                      <span
                        className={cn(
                          'shrink-0 text-[10px] leading-4 px-1.5 py-0.5 rounded-full border',
                          claimStatusClass(claimStatus),
                        )}
                      >
                        {claimStatusLabel(claimStatus, claimStatusLabels)}
                      </span>
                    )}
                    {shouldShowClaimConfidence(claimConfidence) && (
                      <span className="shrink-0 text-[10px] leading-4 px-1.5 py-0.5 rounded-full border bg-sky-500/10 text-sky-800 dark:text-sky-200 border-sky-500/20">
                        {tWiki('evidenceClaimConfidence', {
                          value: formatClaimConfidence(claimConfidence!, locale),
                        })}
                      </span>
                    )}
                  </div>
                </div>
              </div>
              <button
                onClick={() => onOpenChange(false)}
                className="rounded-full p-1.5 hover:bg-muted transition-colors flex-shrink-0"
              >
                <X size={16} className="text-muted-foreground" />
              </button>
            </div>
          </SheetHeader>

          <div className="flex-1 overflow-y-auto px-5 py-4">
            {showStructuredClaim && claimText ? (
              <div className="mb-4">
                <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">
                  {tWiki('evidenceStructuredClaim')}
                </div>
                <p className="text-sm text-foreground/90 leading-relaxed">{claimText}</p>
              </div>
            ) : null}
            <div className="flex items-center gap-1.5 mb-3">
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                {excerptLabel}
              </span>
            </div>

            <div className="bg-muted/40 rounded-lg p-4 border border-border/30">
              {thumbnailUrl ? (
                <img
                  src={thumbnailUrl}
                  alt=""
                  className="mb-3 h-28 w-full max-w-xs rounded-md border border-border/60 object-cover bg-muted"
                />
              ) : null}
              {renderedSnippet.length > 0 ? (
                renderedSnippet
              ) : (
                <p className="text-sm text-muted-foreground italic">{t('no_snippet')}</p>
              )}
            </div>

            {snapshotStatus === 'verified' && (
              <p className="text-[11px] text-emerald-700 dark:text-emerald-300 mt-3">
                {tWiki('evidenceSnapshotVerified')}
              </p>
            )}
            {snapshotStatus === 'stale' && (
              <p className="text-[11px] text-amber-700 dark:text-amber-300 mt-3">
                {tWiki('evidenceSnapshotStale')}
              </p>
            )}
            {resourceUri ? (
              <p className="text-[11px] text-muted-foreground mt-2 font-mono break-all">{tWiki('evidenceResourceUri', { uri: resourceUri })}</p>
            ) : null}
            {supersededFromUri ? (
              <p className="text-[11px] text-amber-700/90 dark:text-amber-300/90 mt-1 font-mono break-all">
                {tWiki('evidenceSupersededFrom', { uri: supersededFromUri })}
              </p>
            ) : null}
            {snapshotStatus === 'missing' && (
              <p className="text-[11px] text-muted-foreground mt-3">{tWiki('evidenceSnapshotMissing')}</p>
            )}

            <p className="text-xs text-muted-foreground mt-4 flex items-center gap-1">
              <BookOpen size={12} />
              {t('knowledge_base')}: LLM-Wiki
            </p>
          </div>
        </SheetContent>
      </Sheet>
    );
  },
);

SourceChunkDrawer.displayName = 'SourceChunkDrawer';

export default SourceChunkDrawer;
