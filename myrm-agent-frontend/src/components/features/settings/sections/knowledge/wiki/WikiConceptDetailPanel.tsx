'use client';

import Link from 'next/link';
import { useLocale, useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { Card, CardContent, CardHeader } from '@/components/primitives/card';
import { Input } from '@/components/primitives/input';
import { IconBook, IconEdit, IconLoader, IconSave, IconX } from '@/components/features/icons/PremiumIcons';
import MarkdownContent from '@/components/features/message-box/MarkdownContent';
import { WikiMarkdownEditor } from './WikiMarkdownEditor';
import { cn } from '@/lib/utils/classnameUtils';
import type { Concept } from '@/services/wikiService';
import type { WikiEditTab } from './useWikiConceptsList';
import { claimStatusClass, claimStatusLabel, formatClaimConfidence, shouldShowClaimConfidence } from '@/lib/wiki/claimStatusDisplay';

interface WikiConceptDetailPanelProps {
  selectedConcept: Concept | null;
  isEditing: boolean;
  editTab: WikiEditTab;
  editContent: string;
  editCompiledTruth: string;
  editTimelineDisplay: string;
  editTimelineAppend: string;
  editTags: string;
  editAliases: string;
  isSaving: boolean;
  onEdit: () => void;
  onCancelEdit: () => void;
  onSave: () => void;
  onEditTabChange: (tab: WikiEditTab) => void;
  onEditContentChange: (value: string) => void;
  onEditCompiledTruthChange: (value: string) => void;
  onEditTimelineAppendChange: (value: string) => void;
  onEditTagsChange: (value: string) => void;
  onEditAliasesChange: (value: string) => void;
}

const EDIT_TABS: WikiEditTab[] = ['truth', 'timeline', 'metadata', 'advanced'];

function tabLabel(tab: WikiEditTab, labels: Record<WikiEditTab, string>): string {
  return labels[tab];
}

export function WikiConceptDetailPanel({
  selectedConcept,
  isEditing,
  editTab,
  editContent,
  editCompiledTruth,
  editTimelineDisplay,
  editTimelineAppend,
  editTags,
  editAliases,
  isSaving,
  onEdit,
  onCancelEdit,
  onSave,
  onEditTabChange,
  onEditContentChange,
  onEditCompiledTruthChange,
  onEditTimelineAppendChange,
  onEditTagsChange,
  onEditAliasesChange,
}: WikiConceptDetailPanelProps) {
  const t = useTranslations('settings.wiki.concepts');
  const locale = useLocale();
  const claims = selectedConcept?.claims ?? [];
  const claimStatusLabels = {
    supported: t('claimStatusSupported'),
    contested: t('claimStatusContested'),
    unsupported: t('claimStatusUnsupported'),
    unknown: t('claimStatusUnknown'),
  };
  const editTabLabels: Record<WikiEditTab, string> = {
    truth: t('editTabTruth'),
    timeline: t('editTabTimeline'),
    metadata: t('editTabMetadata'),
    advanced: t('editTabAdvanced'),
  };

  return (
    <Card className="col-span-1 md:col-span-2 h-full overflow-hidden flex flex-col min-h-0">
      {selectedConcept ? (
        <>
          <CardHeader className="border-b bg-muted/20 flex flex-row items-center justify-between py-4 gap-3">
            <div className="flex items-center gap-2 truncate pr-4">
              <span className="font-semibold text-lg truncate">{selectedConcept.name}</span>
              {selectedConcept.provenance && (
                <Badge variant="outline" className="text-blue-600 dark:text-blue-400 border-blue-500/30 shrink-0">
                  {t(`provenance.${selectedConcept.provenance}`, { defaultValue: selectedConcept.provenance })}
                </Badge>
              )}
              {selectedConcept.source_chat && (
                <Link
                  href={
                    selectedConcept.source_message
                      ? `/${selectedConcept.source_chat}?highlight=${encodeURIComponent(selectedConcept.source_message)}`
                      : `/${selectedConcept.source_chat}`
                  }
                  className="text-xs text-primary hover:underline shrink-0"
                >
                  {t('sourceChat')}
                </Link>
              )}
            </div>
            <div className="flex gap-2 shrink-0">
              {isEditing ? (
                <>
                  <Button variant="outline" size="sm" onClick={onCancelEdit} disabled={isSaving}>
                    <IconX className="w-4 h-4 mr-2" />
                    {t('cancel')}
                  </Button>
                  <Button size="sm" onClick={() => void onSave()} disabled={isSaving}>
                    {isSaving ? (
                      <IconLoader className="w-4 h-4 mr-2 animate-spin" />
                    ) : (
                      <IconSave className="w-4 h-4 mr-2" />
                    )}
                    {t('save')}
                  </Button>
                </>
              ) : (
                <Button variant="outline" size="sm" onClick={onEdit}>
                  <IconEdit className="w-4 h-4 mr-2" />
                  {t('edit')}
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent className="flex-1 overflow-y-auto p-4 min-h-0 space-y-6">
            {isEditing ? (
              <div className="space-y-4 h-full flex flex-col min-h-[420px]">
                <div className="flex flex-wrap gap-2 overflow-x-auto pb-1">
                  {EDIT_TABS.map((tab) => (
                    <Button
                      key={tab}
                      type="button"
                      size="sm"
                      variant={editTab === tab ? 'default' : 'outline'}
                      onClick={() => onEditTabChange(tab)}
                    >
                      {tabLabel(tab, editTabLabels)}
                    </Button>
                  ))}
                </div>

                {editTab === 'truth' && (
                  <WikiMarkdownEditor
                    value={editCompiledTruth}
                    onChange={onEditCompiledTruthChange}
                    placeholder={t('editTruthPlaceholder')}
                    messageIdSuffix="truth"
                    onSaveShortcut={() => { if (!isSaving) {onSave();} }}
                    className="flex-1"
                  />
                )}

                {editTab === 'timeline' && (
                  <div className="space-y-3">
                    <p className="text-xs text-muted-foreground">{t('editTimelineHint')}</p>
                    {editTimelineDisplay ? (
                      <div className="space-y-2">
                        <div className="text-xs font-medium text-muted-foreground">{t('editTimelineExisting')}</div>
                        <pre className="whitespace-pre-wrap rounded-md border bg-muted/20 p-3 text-xs font-mono text-muted-foreground max-h-40 overflow-y-auto">
                          {editTimelineDisplay}
                        </pre>
                      </div>
                    ) : (
                      <p className="text-xs text-muted-foreground">{t('editTimelineEmpty')}</p>
                    )}
                    <textarea
                      className="w-full min-h-[120px] p-4 font-mono text-sm bg-background border rounded-md focus:outline-none focus:ring-2 focus:ring-primary/50 resize-none"
                      value={editTimelineAppend}
                      onChange={(e) => onEditTimelineAppendChange(e.target.value)}
                      placeholder={t('editTimelinePlaceholder')}
                    />
                  </div>
                )}

                {editTab === 'metadata' && (
                  <div className="grid gap-4">
                    <div className="space-y-2">
                      <label className="text-sm font-medium">{t('editTagsLabel')}</label>
                      <Input
                        value={editTags}
                        onChange={(e) => onEditTagsChange(e.target.value)}
                        placeholder={t('editTagsPlaceholder')}
                      />
                    </div>
                    <div className="space-y-2">
                      <label className="text-sm font-medium">{t('editAliasesLabel')}</label>
                      <Input
                        value={editAliases}
                        onChange={(e) => onEditAliasesChange(e.target.value)}
                        placeholder={t('editAliasesPlaceholder')}
                      />
                    </div>
                  </div>
                )}

                {editTab === 'advanced' && (
                  <div className="space-y-3 flex-1 min-h-0 flex flex-col">
                    <p className="text-xs text-amber-700 dark:text-amber-300">{t('editAdvancedWarning')}</p>
                    <WikiMarkdownEditor
                      value={editContent}
                      onChange={onEditContentChange}
                      placeholder={t('editPlaceholder')}
                      messageIdSuffix="advanced"
                      onSaveShortcut={() => { if (!isSaving) {onSave();} }}
                      className="flex-1"
                    />
                  </div>
                )}
              </div>
            ) : (
              <>
                <div className="prose dark:prose-invert max-w-none">
                  <MarkdownContent
                    content={selectedConcept.content}
                    sources={[]}
                    messageId={`wiki-${selectedConcept.name}`}
                  />
                </div>
                <div className="space-y-3 border-t border-border/60 pt-4">
                  <div className="text-sm font-medium">{t('claimsTitle')}</div>
                  {claims.length === 0 ? (
                    <p className="text-sm text-muted-foreground">{t('claimsEmpty')}</p>
                  ) : (
                    <div className="space-y-3">
                      {claims.map((claim) => (
                        <div
                          key={claim.id}
                          className={cn(
                            'rounded-lg border p-3 space-y-2',
                            claim.status === 'unknown'
                              ? 'border-border/40 bg-muted/10 opacity-80'
                              : 'border-border/60 bg-muted/20',
                          )}
                        >
                          <div className="flex flex-wrap items-center gap-2">
                            <span
                              className={cn(
                                'text-sm font-medium',
                                claim.status === 'unknown' && 'text-muted-foreground',
                              )}
                            >
                              {claim.text}
                            </span>
                            <span
                              className={cn(
                                'text-[10px] leading-4 px-1.5 py-0.5 rounded-full border',
                                claimStatusClass(claim.status),
                              )}
                            >
                              {claimStatusLabel(claim.status, claimStatusLabels)}
                            </span>
                            {shouldShowClaimConfidence(claim.confidence) && (
                              <span className="text-[10px] leading-4 px-1.5 py-0.5 rounded-full border bg-sky-500/10 text-sky-800 dark:text-sky-200 border-sky-500/20">
                                {formatClaimConfidence(claim.confidence, locale)}
                              </span>
                            )}
                          </div>
                          {claim.evidence.length > 0 && (
                            <ul className="space-y-1 text-xs text-muted-foreground">
                              {claim.evidence.map((evidence, index) => (
                                <li key={`${claim.id}-${index}`} className="space-y-0.5">
                                  {evidence.path && (
                                    <div className="font-mono truncate">
                                      {t('evidencePath')}: {evidence.path}
                                      {evidence.lines ? ` · ${t('evidenceLines')}: ${evidence.lines}` : ''}
                                    </div>
                                  )}
                                  {evidence.snapshot_status === 'verified' && (
                                    <div className="text-[11px] text-emerald-700 dark:text-emerald-300">
                                      {t('evidenceSnapshotVerified')}
                                    </div>
                                  )}
                                  {evidence.snapshot_status === 'stale' && (
                                    <div className="text-[11px] text-amber-700 dark:text-amber-300">
                                      {t('evidenceSnapshotStale')}
                                    </div>
                                  )}
                                  {evidence.snapshot_status === 'missing' && evidence.path && (
                                    <div className="text-[11px] text-muted-foreground">
                                      {t('evidenceSnapshotMissing')}
                                    </div>
                                  )}
                                  {evidence.resource_uri ? (
                                    <div className="text-[11px] text-muted-foreground font-mono break-all">
                                      {t('evidenceResourceUri', { uri: evidence.resource_uri })}
                                    </div>
                                  ) : null}
                                  {evidence.superseded_from_uri ? (
                                    <div className="text-[11px] text-amber-700/90 dark:text-amber-300/90 font-mono break-all">
                                      {t('evidenceSupersededFrom', { uri: evidence.superseded_from_uri })}
                                    </div>
                                  ) : null}
                                </li>
                              ))}
                            </ul>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </>
            )}
          </CardContent>
        </>
      ) : (
        <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-4">
          <IconBook className="w-16 h-16 opacity-20" />
          <p>{t('selectToView')}</p>
        </div>
      )}
    </Card>
  );
}
