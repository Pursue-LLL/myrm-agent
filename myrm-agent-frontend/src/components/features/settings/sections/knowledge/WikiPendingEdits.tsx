'use client';

import Link from 'next/link';
import { useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Button } from '@/components/primitives/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { Badge } from '@/components/primitives/badge';
import { IconCheckCircle, IconCheck, IconX, IconClock, IconEdit } from '@/components/features/icons/PremiumIcons';
import { wikiService, PendingEdit } from '@/services/wikiService';
import { ApiError } from '@/lib/api';
import { WikiScopeChip } from './WikiScopeChip';
import { WikiMarkdownEditor } from './wiki/WikiMarkdownEditor';
import {
  extractSourceChatIdFromFrontmatter,
  extractSourceMessageIdFromFrontmatter,
  stripYamlFrontmatter,
} from './wiki/wikiTreeUtils';

interface WikiPendingEditsProps {
  agentScopeId?: string | null;
  scopeLabel: string;
  onVaultMutated?: () => void;
  initialFilter?: PendingEditFilter;
}

type PendingEditFilter = 'all' | 'concepts' | 'synthesis';

function isSynthesisEdit(edit: PendingEdit): boolean {
  return edit.concept_name.startsWith('Comparisons/');
}

export function WikiPendingEdits({
  agentScopeId,
  scopeLabel,
  onVaultMutated,
  initialFilter = 'all',
}: WikiPendingEditsProps) {
  const t = useTranslations('settings.wiki');
  const [edits, setEdits] = useState<PendingEdit[]>([]);
  const [stats, setStats] = useState<Record<string, number>>({});
  const [filter, setFilter] = useState<PendingEditFilter>(initialFilter);
  const [isLoading, setIsLoading] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editContent, setEditContent] = useState<string>('');

  const loadPending = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await wikiService.getPendingEdits(agentScopeId);
      setEdits(res.pending_edits);
      setStats(res.stats);
    } catch (error) {
      console.error('Failed to load pending edits:', error);
      toast.error(t('errors.loadPendingFailed'));
    } finally {
      setIsLoading(false);
    }
  }, [agentScopeId, t]);

  useEffect(() => {
    setFilter(initialFilter);
  }, [initialFilter]);

  useEffect(() => {
    setEdits([]);
    setStats({});
    setEditingId(null);
    setEditContent('');
    void loadPending();
  }, [loadPending]);

  const handleApprove = async (id: number, modifiedContent?: string) => {
    try {
      await wikiService.approveEdit(id, modifiedContent, agentScopeId);
      toast.success(t('success.approveComplete'));
      setEditingId(null);
      setEditContent('');
      void loadPending();
      onVaultMutated?.();
    } catch (error) {
      console.error('Failed to approve:', error);
      if (error instanceof ApiError) {
        if (error.businessCode === 'stale_pending') {
          toast.error(t('errors.approveStaleSources'));
          return;
        }
        if (error.code === 422 && error.businessCode === 'invalid_frontmatter') {
          toast.error(t('errors.approveTypeRequired'));
          return;
        }
      }
      toast.error(t('errors.approveFailed'));
    }
  };

  const handleReject = async (id: number) => {
    try {
      await wikiService.rejectEdit(id, agentScopeId);
      toast.success(t('success.rejectComplete'));
      void loadPending();
    } catch (error) {
      console.error('Failed to reject:', error);
      toast.error(t('errors.rejectFailed'));
    }
  };

  const startEditing = (edit: PendingEdit) => {
    setEditingId(edit.id);
    setEditContent(edit.proposed_content);
  };

  const cancelEditing = () => {
    setEditingId(null);
    setEditContent('');
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString();
  };

  const synthesisPendingCount = stats.synthesis_pending ?? 0;
  const filteredEdits = edits.filter((edit) => {
    if (filter === 'synthesis') {
      return isSynthesisEdit(edit);
    }
    if (filter === 'concepts') {
      return !isSynthesisEdit(edit);
    }
    return true;
  });

  const filterOptions: Array<{ id: PendingEditFilter; label: string }> = [
    { id: 'all', label: t('pendingEdits.filterAll') },
    { id: 'concepts', label: t('pendingEdits.filterConcepts') },
    { id: 'synthesis', label: t('pendingEdits.filterSynthesis') },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <IconCheckCircle className="w-5 h-5" />
            {t('pendingEdits.title')}
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <WikiScopeChip scopeLabel={scopeLabel} />
            {stats.pending > 0 && (
              <Badge variant="secondary" className="bg-amber-500/10 text-amber-600 hover:bg-amber-500/20">
                {stats.pending} {t('pendingEdits.status.pending')}
              </Badge>
            )}
            {synthesisPendingCount > 0 && (
              <Badge variant="secondary" className="bg-violet-500/10 text-violet-600 hover:bg-violet-500/20">
                {synthesisPendingCount} {t('pendingEdits.status.synthesisPending')}
              </Badge>
            )}
          </div>
        </CardTitle>
        <CardDescription>{t('pendingEdits.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {edits.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {filterOptions.map((option) => (
              <Button
                key={option.id}
                size="sm"
                variant={filter === option.id ? 'default' : 'outline'}
                onClick={() => setFilter(option.id)}
              >
                {option.label}
              </Button>
            ))}
          </div>
        )}
        {edits.length === 0 && !isLoading ? (
          <div className="p-8 border border-dashed rounded-lg flex flex-col items-center justify-center text-muted-foreground bg-muted/20">
            <IconCheck className="w-8 h-8 mb-2 text-green-500/50" />
            <div>{t('pendingEdits.noPending')}</div>
          </div>
        ) : filteredEdits.length === 0 && !isLoading ? (
          <div className="p-8 border border-dashed rounded-lg flex flex-col items-center justify-center text-muted-foreground bg-muted/20">
            <IconCheck className="w-8 h-8 mb-2 text-green-500/50" />
            <div>{t('pendingEdits.noFiltered')}</div>
          </div>
        ) : (
          <div className="space-y-4">
            {filteredEdits.map((edit) => {
              const sourceChatId =
                edit.provenance === 'chat-compound'
                  ? extractSourceChatIdFromFrontmatter(edit.proposed_content)
                  : null;
              const sourceMessageId =
                edit.provenance === 'chat-compound'
                  ? extractSourceMessageIdFromFrontmatter(edit.proposed_content)
                  : null;
              return (
              <div key={edit.id} className="border rounded-lg overflow-hidden bg-card">
                <div className="flex items-center justify-between p-4 bg-muted/30 border-b gap-3 flex-wrap">
                  <div className="flex items-center gap-3 flex-wrap">
                    <span className="font-semibold text-lg">{edit.concept_name}</span>
                    {isSynthesisEdit(edit) && (
                      <Badge variant="outline" className="text-violet-600 border-violet-500/30">
                        {t('pendingEdits.synthesisBadge')}
                      </Badge>
                    )}
                    {edit.provenance && !isSynthesisEdit(edit) && (
                      <Badge variant="outline" className="text-blue-600 dark:text-blue-400 border-blue-500/30">
                        {t(`pendingEdits.provenance.${edit.provenance}`, { defaultValue: edit.provenance })}
                      </Badge>
                    )}
                    {sourceChatId && (
                      <Link
                        href={
                          sourceMessageId
                            ? `/${sourceChatId}?highlight=${encodeURIComponent(sourceMessageId)}`
                            : `/${sourceChatId}`
                        }
                        className="text-xs text-primary hover:underline"
                      >
                        {t('pendingEdits.openSourceChat')}
                      </Link>
                    )}
                    <Badge
                      variant="outline"
                      className="flex items-center gap-1.5 text-xs text-muted-foreground font-normal"
                    >
                      <IconClock className="w-3 h-3" />
                      {formatDate(edit.created_at)}
                    </Badge>
                  </div>
                  <div className="flex gap-2 flex-wrap">
                    {editingId === edit.id ? (
                      <>
                        <Button size="sm" variant="outline" onClick={cancelEditing}>
                          <IconX className="w-4 h-4 mr-1.5" />
                          {t('pendingEdits.cancelEdit')}
                        </Button>
                        <Button
                          size="sm"
                          className="bg-green-600 hover:bg-green-700 text-white"
                          onClick={() => handleApprove(edit.id, editContent)}
                        >
                          <IconCheck className="w-4 h-4 mr-1.5" />
                          {t('pendingEdits.saveApprove')}
                        </Button>
                      </>
                    ) : (
                      <>
                        <Button
                          size="sm"
                          variant="outline"
                          className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                          onClick={() => handleReject(edit.id)}
                        >
                          <IconX className="w-4 h-4 mr-1.5" />
                          {t('pendingEdits.reject')}
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => startEditing(edit)}>
                          <IconEdit className="w-4 h-4 mr-1.5" />
                          {t('pendingEdits.edit')}
                        </Button>
                        <Button
                          size="sm"
                          className="bg-green-600 hover:bg-green-700 text-white"
                          onClick={() => handleApprove(edit.id)}
                        >
                          <IconCheck className="w-4 h-4 mr-1.5" />
                          {t('pendingEdits.approve')}
                        </Button>
                      </>
                    )}
                  </div>
                </div>
                <div className="p-4 flex flex-col min-h-[420px]">
                  {editingId === edit.id ? (
                    <WikiMarkdownEditor
                      value={editContent}
                      onChange={setEditContent}
                      previewTransform={stripYamlFrontmatter}
                      messageIdSuffix={`pending-${edit.id}`}
                      className="flex-1"
                    />
                  ) : (
                    <div className="text-sm font-mono whitespace-pre-wrap max-h-96 overflow-y-auto">{edit.proposed_content}</div>
                  )}
                </div>
              </div>
            );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
