'use client';

import { memo, useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { Check, X, ChevronDown, FileText, Clock } from 'lucide-react';
import { IconGlow } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { Skeleton } from '@/components/primitives/skeleton';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/primitives/collapsible';
import { toast } from '@/hooks/useToast';
import useAuthStore from '@/store/useAuthStore';
import { useSkillDraftStore } from '@/store/skill/useSkillDraftStore';
import type { SkillDraft } from '@/services/skill';
import { cn } from '@/lib/utils/classnameUtils';

interface SkillDraftReviewPanelProps {
  className?: string;
}

const SkillDraftReviewPanel = memo(({ className }: SkillDraftReviewPanelProps) => {
  const t = useTranslations('settings.skills');
  const { user } = useAuthStore();
  const { drafts, unreviewedCount, isLoading, fetchDrafts, approveDraft, rejectDraft } = useSkillDraftStore();

  const [isOpen, setIsOpen] = useState(unreviewedCount > 0);
  const [processingId, setProcessingId] = useState<string | null>(null);

  useEffect(() => {
    if (unreviewedCount > 0) {
      fetchDrafts('PENDING_REVIEW');
    }
  }, [unreviewedCount, fetchDrafts]);

  useEffect(() => {
    if (unreviewedCount > 0) {
      setIsOpen(true);
    }
  }, [unreviewedCount]);

  const handleApprove = useCallback(
    async (draft: SkillDraft) => {
      if (!user?.id || processingId) return;
      setProcessingId(draft.id);
      try {
        const result = await approveDraft(draft.id, draft.name);
        if (result.materialized === false) {
          toast({
            title: t('draft.approveFailed'),
            description: result.error || draft.name,
            variant: 'destructive',
          });
        } else {
          let description = draft.name || draft.draft_type;
          if (result.materialized_type === 'skill') {
            description = t('draft.materializedSkill', { name: result.skill_name || draft.name });
          } else if (result.materialized_type === 'memory') {
            description = t('draft.materializedMemory');
          }
          toast({
            title: t('draft.approveSuccess'),
            description,
            variant: 'default',
          });
        }
      } catch {
        toast({ title: t('draft.approveFailed'), variant: 'destructive' });
      } finally {
        setProcessingId(null);
      }
    },
    [user?.id, processingId, approveDraft, t],
  );

  const handleReject = useCallback(
    async (draft: SkillDraft) => {
      if (!user?.id || processingId) return;
      setProcessingId(draft.id);
      try {
        await rejectDraft(draft.id);
        toast({
          title: t('draft.rejectSuccess'),
          variant: 'default',
        });
      } catch {
        toast({ title: t('draft.rejectFailed'), variant: 'destructive' });
      } finally {
        setProcessingId(null);
      }
    },
    [user?.id, processingId, rejectDraft, t],
  );

  if (unreviewedCount === 0) return null;

  const draftTypeLabel = (type: string): string => {
    if (type === 'skill_draft') return t('draft.typeSkill');
    if (type === 'semantic_memory') return t('draft.typeMemory');
    return type;
  };

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen} className={className}>
      <CollapsibleTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className="gap-2 w-full justify-start bg-orange-50 dark:bg-orange-950/30 border-orange-200 dark:border-orange-800"
        >
          <IconGlow className="h-4 w-4 text-orange-500" />
          {t('draft.reviewPanelTitle')}
          <Badge variant="destructive" className="ml-auto px-1.5 py-0 text-xs">
            {unreviewedCount}
          </Badge>
          <ChevronDown className={cn('h-4 w-4 transition-transform ml-1', isOpen && 'rotate-180')} />
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="mt-3 space-y-3">
          {isLoading && drafts.length === 0 ? (
            <div className="space-y-2">
              {[1, 2].map((i) => (
                <div key={i} className="p-3 border rounded-lg space-y-2">
                  <Skeleton className="h-4 w-3/4" />
                  <Skeleton className="h-3 w-1/2" />
                </div>
              ))}
            </div>
          ) : (
            drafts.map((draft) => (
              <div key={draft.id} className="p-3 border rounded-lg bg-muted/30 space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <FileText className="h-3.5 w-3.5 text-muted-foreground" />
                      <span className="font-medium text-sm truncate">
                        {draft.name || draft.content?.slice(0, 40) || draft.draft_type}
                      </span>
                      <Badge variant="outline" className="text-xs px-1.5 py-0">
                        {draftTypeLabel(draft.draft_type)}
                      </Badge>
                    </div>
                    {draft.description && (
                      <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{draft.description}</p>
                    )}
                    <div className="flex items-center gap-1 mt-1 text-[10px] text-muted-foreground/70">
                      <Clock className="h-3 w-3" />
                      {new Date(draft.created_at).toLocaleString()}
                    </div>
                  </div>
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 text-green-600 hover:text-green-700 hover:bg-green-50 dark:hover:bg-green-950/30"
                      onClick={() => handleApprove(draft)}
                      disabled={processingId === draft.id}
                    >
                      <Check className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-950/30"
                      onClick={() => handleReject(draft)}
                      disabled={processingId === draft.id}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
                {draft.trigger_condition && (
                  <div className="pt-2 border-t border-border/50">
                    <p className="text-xs font-medium text-muted-foreground">{t('draft.triggerCondition')}</p>
                    <p className="text-xs mt-0.5">{draft.trigger_condition}</p>
                  </div>
                )}
                {draft.skill_steps && (
                  <div className="pt-2 border-t border-border/50">
                    <p className="text-xs font-medium text-muted-foreground">{t('draft.skillSteps')}</p>
                    <pre className="text-xs mt-0.5 whitespace-pre-wrap bg-background/50 p-2 rounded max-h-40 overflow-y-auto">
                      {draft.skill_steps}
                    </pre>
                  </div>
                )}
                {draft.content && draft.draft_type === 'skill_patch' && (
                  <div className="pt-2 border-t border-border/50">
                    <p className="text-xs font-medium text-muted-foreground">
                      {t('draft.patchContent') || 'Patch Changes'}
                    </p>
                    <pre className="text-[10px] font-mono mt-0.5 whitespace-pre-wrap bg-background/50 p-2 rounded border border-border/50 max-h-60 overflow-y-auto">
                      {draft.content}
                    </pre>
                  </div>
                )}
              </div>
            ))
          )}
          {drafts.length === 0 && !isLoading && (
            <p className="text-sm text-muted-foreground text-center py-4">{t('draft.noDrafts')}</p>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
});

SkillDraftReviewPanel.displayName = 'SkillDraftReviewPanel';

export default SkillDraftReviewPanel;
