'use client';

/**
 * [INPUT]
 * - @/services/wikiService::Concept (POS: 知识库核心词条实体模型)
 * - @/components/features/message-box/MarkdownContent::MarkdownContent (POS: Markdown 渲染与锚点生成核心组件)
 * - ./WikiMarkdownEditor::WikiMarkdownEditor (POS: Wiki 词条分屏实时编辑组件)
 * - ./VideoKnowledgePlayer::VideoKnowledgePlayer (POS: 视频知识播放与时间戳对齐组件)
 * - ./WikiConceptClaimsSection::WikiConceptClaimsSection (POS: 词条声明与事实凭证下钻组件)
 * - ./WikiConceptLinksPanel::WikiConceptLinksPanel (POS: 词条双向链接与脉络导航组件)
 *
 * [OUTPUT]
 * - WikiConceptDetailPanel: 词条详情预览、反向引用小节锚点聚焦定位、多标签窄写与分屏编辑一体化面板
 *
 * [POS]
 * 知识库词条主阅读与编辑工作区。承载概念预览、来源对话跳转、反向链接小节直达与多模态知识交互。
 */

import { useMemo, useEffect, useRef, useState, useCallback } from 'react';
import Link from 'next/link';
import { useLocale, useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { Card, CardContent, CardHeader } from '@/components/primitives/card';
import { Input } from '@/components/primitives/input';
import { IconBook, IconEdit, IconLoader, IconSave, IconX } from '@/components/features/icons/PremiumIcons';
import MarkdownContent from '@/components/features/message-box/MarkdownContent';
import { WikiMarkdownEditor } from './WikiMarkdownEditor';
import { VideoKnowledgePlayer, extractVideoNoteMeta } from './VideoKnowledgePlayer';
import { WikiConceptClaimsSection } from './WikiConceptClaimsSection';
import { WikiConceptLinksPanel } from './WikiConceptLinksPanel';
import { Network } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import type { Concept } from '@/services/wikiService';
import type { WikiEditTab } from './useWikiConceptsList';

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
  onUpdateClaimStatus?: (claimId: string, status: 'supported' | 'contested') => void;
  onHealClaims?: () => void;
  agentId?: string | null;
  onSelectConcept?: (name: string) => void;
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
  onUpdateClaimStatus,
  onHealClaims,
  agentId,
  onSelectConcept,
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

  const videoNoteMeta = useMemo(() => {
    return selectedConcept ? extractVideoNoteMeta(selectedConcept.content) : null;
  }, [selectedConcept]);

  const [targetHeading, setTargetHeading] = useState<string | null>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const highlightTimerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    return () => {
      if (highlightTimerRef.current) {
        clearTimeout(highlightTimerRef.current);
      }
    };
  }, []);

  const scrollToHeading = useCallback((headingText: string): boolean => {
    const container = contentRef.current;
    if (!container) {
      return false;
    }
    const headings = Array.from(container.querySelectorAll('h1, h2, h3, h4, h5, h6'));
    const normalizedTarget = headingText.trim().toLowerCase();
    const matched = headings.find((h) => {
      const text = (h.textContent || '').trim().toLowerCase();
      return text === normalizedTarget || text.includes(normalizedTarget) || normalizedTarget.includes(text);
    });
    if (matched) {
      matched.scrollIntoView({ behavior: 'smooth', block: 'center' });
      if (highlightTimerRef.current) {
        clearTimeout(highlightTimerRef.current);
      }
      matched.classList.add('bg-primary/10', 'ring-1', 'ring-primary/40', 'rounded-md', 'transition-all', 'duration-500');
      highlightTimerRef.current = setTimeout(() => {
        matched.classList.remove('bg-primary/10', 'ring-1', 'ring-primary/40', 'rounded-md');
        highlightTimerRef.current = null;
      }, 2000);
      return true;
    }
    return false;
  }, []);

  useEffect(() => {
    if (!targetHeading || isEditing) {
      return;
    }

    let cancelled = false;
    const delays = [80, 250, 600];
    const timers: NodeJS.Timeout[] = [];

    delays.forEach((delay) => {
      const timer = setTimeout(() => {
        if (cancelled) {
          return;
        }
        const found = scrollToHeading(targetHeading);
        if (found) {
          timers.forEach((t) => clearTimeout(t));
          setTargetHeading(null);
        }
      }, delay);
      timers.push(timer);
    });

    return () => {
      cancelled = true;
      timers.forEach((t) => clearTimeout(t));
    };
  }, [selectedConcept?.name, selectedConcept?.content, targetHeading, isEditing, scrollToHeading]);

  const handleSelectConceptFromLinks = useCallback(
    (name: string, heading?: string | null) => {
      setTargetHeading(heading || null);
      if (selectedConcept && selectedConcept.name === name) {
        if (heading) {
          const found = scrollToHeading(heading);
          if (found) {
            setTargetHeading(null);
          }
        }
        return;
      }
      if (onSelectConcept) {
        onSelectConcept(name);
      }
    },
    [selectedConcept, onSelectConcept, scrollToHeading],
  );

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
                  <Button
                    data-testid="wiki-concept-save-btn"
                    size="sm"
                    onClick={() => void onSave()}
                    disabled={isSaving}
                  >
                    {isSaving ? (
                      <IconLoader className="w-4 h-4 mr-2 animate-spin" />
                    ) : (
                      <IconSave className="w-4 h-4 mr-2" />
                    )}
                    {t('save')}
                  </Button>
                </>
              ) : (
                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      const el = document.getElementById('wiki-concept-links');
                      el?.scrollIntoView({ behavior: 'smooth' });
                    }}
                    className="text-xs text-muted-foreground hover:text-foreground hidden sm:flex items-center gap-1.5"
                    title="跳转到双向链接与脉络"
                  >
                    <Network className="w-3.5 h-3.5 text-primary" />
                    <span>脉络</span>
                  </Button>
                  <Button data-testid="wiki-concept-edit-btn" variant="outline" size="sm" onClick={onEdit}>
                    <IconEdit className="w-4 h-4 mr-2" />
                    {t('edit')}
                  </Button>
                </div>
              )}
            </div>
          </CardHeader>
          <CardContent ref={contentRef} className="flex-1 overflow-y-auto p-4 min-h-0 space-y-6">
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
                    onSaveShortcut={() => {
                      if (!isSaving) {
                        onSave();
                      }
                    }}
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
                      onSaveShortcut={() => {
                        if (!isSaving) {
                          onSave();
                        }
                      }}
                      className="flex-1"
                    />
                  </div>
                )}
              </div>
            ) : (
              <>
                {videoNoteMeta && (
                  <VideoKnowledgePlayer
                    sourceUrl={videoNoteMeta.sourceUrl}
                    title={videoNoteMeta.title || selectedConcept.name}
                    chapters={videoNoteMeta.chapters}
                    className="mb-4"
                  />
                )}
                <div className="prose dark:prose-invert max-w-none">
                  <MarkdownContent
                    content={selectedConcept.content}
                    sources={[]}
                    messageId={`wiki-${selectedConcept.name}`}
                  />
                </div>
                <WikiConceptClaimsSection
                  claims={claims}
                  locale={locale}
                  claimStatusLabels={claimStatusLabels}
                  onHealClaims={onHealClaims}
                  onUpdateClaimStatus={onUpdateClaimStatus}
                  t={t}
                />

                <WikiConceptLinksPanel
                  conceptName={selectedConcept.name}
                  agentId={agentId}
                  onSelectConcept={handleSelectConceptFromLinks}
                />
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
