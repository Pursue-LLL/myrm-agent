'use client';

import { useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { Sparkles, Check, X, Clock } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { 
  listSkillDrafts, 
  approveSkillDraft, 
  rejectSkillDraft,
  type SkillDraft 
} from '@/services/skill';
import { toast } from '@/hooks/useToast';

interface AgentInstinctInboxTabProps {
  agentId: string | null;
  readonly?: boolean;
}

export function AgentInstinctInboxTab({ agentId, readonly }: AgentInstinctInboxTabProps) {
  const t = useTranslations();
  const [drafts, setDrafts] = useState<SkillDraft[]>([]);
  const [loading, setLoading] = useState(true);
  const [processingId, setProcessingId] = useState<string | null>(null);

  const fetchDrafts = useCallback(async () => {
    try {
      setLoading(true);
      const res = await listSkillDrafts('PENDING_REVIEW', 100);
      // Filter drafts relevant to this agent (or default if this is the default agent)
      const relevantDrafts = res.drafts.filter(d => 
        !agentId || d.agent_id === agentId || d.agent_id === 'default'
      );
      setDrafts(relevantDrafts);
    } catch (e) {
      console.error('Failed to fetch drafts:', e);
    } finally {
      setLoading(false);
    }
  }, [agentId]);

  useEffect(() => {
    fetchDrafts();
  }, [fetchDrafts]);

  const handleApprove = async (draft: SkillDraft) => {
    if (processingId) return;
    try {
      setProcessingId(draft.id);
      await approveSkillDraft(draft.id, draft.name || undefined);
      toast({ title: t('agent.instinctInbox.approveSuccess', { fallback: 'Insight approved and saved as skill.' }) });
      await fetchDrafts();
    } catch (e) {
      console.error(e);
      toast({ title: 'Approval failed', variant: 'destructive' });
    } finally {
      setProcessingId(null);
    }
  };

  const handleReject = async (draft: SkillDraft) => {
    if (processingId) return;
    try {
      setProcessingId(draft.id);
      await rejectSkillDraft(draft.id);
      toast({ title: t('agent.instinctInbox.rejectSuccess', { fallback: 'Insight dismissed.' }) });
      await fetchDrafts();
    } catch (e) {
      console.error(e);
      toast({ title: 'Rejection failed', variant: 'destructive' });
    } finally {
      setProcessingId(null);
    }
  };

  if (loading) {
    return <div className="p-8 text-center text-muted-foreground animate-pulse">Loading insights...</div>;
  }

  if (drafts.length === 0) {
    return (
      <div
        data-testid="instinct-inbox-empty"
        className="flex flex-col items-center justify-center py-16 px-4 text-center bg-card/30 rounded-xl border border-border/50 border-dashed"
      >
        <Sparkles className="w-12 h-12 text-muted-foreground/30 mb-4" />
        <h3 className="text-lg font-medium text-foreground">{t('agent.instinctInbox.emptyTitle')}</h3>
        <p className="text-sm text-muted-foreground max-w-sm mt-2">{t('agent.instinctInbox.emptyDesc')}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="instinct-inbox-panel">
      <div className="mb-4">
        <h3 className="text-sm font-medium text-foreground flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-purple-500" />
          {t('agent.instinctInbox.title', { fallback: 'Pending Insights' })}
        </h3>
        <p className="text-xs text-muted-foreground mt-1">
          {t('agent.instinctInbox.desc', { fallback: 'Review and approve habits extracted from recent conversations to permanently improve this agent.' })}
        </p>
      </div>

      <div className="space-y-4">
        {drafts.map(draft => (
          <div
            key={draft.id}
            data-testid="instinct-draft-card"
            data-draft-name={draft.name ?? ''}
            className="bg-card border border-border rounded-xl p-4 overflow-hidden relative group transition-all hover:border-purple-500/30 hover:shadow-md hover:shadow-purple-500/5"
          >
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="px-2 py-0.5 rounded-full bg-purple-500/10 text-purple-600 dark:text-purple-400 text-[10px] font-medium tracking-wider uppercase">
                    New Skill Proposal
                  </span>
                  <span className="flex items-center gap-1 text-[10px] text-muted-foreground">
                    <Clock className="w-3 h-3" />
                    {new Date(draft.created_at).toLocaleString()}
                  </span>
                </div>
                <h4 className="text-sm font-semibold text-foreground truncate">{draft.name || draft.draft_type}</h4>
                <p className="text-xs text-muted-foreground mt-1.5 line-clamp-3 leading-relaxed">
                  {draft.description}
                </p>
              </div>
              
              {!readonly && (
                <div className="flex flex-col gap-2 shrink-0">
                  <Button
                    size="sm"
                    data-testid="instinct-approve-btn"
                    onClick={() => handleApprove(draft)}
                    disabled={processingId === draft.id}
                    className="h-8 gap-1.5 bg-purple-600 hover:bg-purple-700 text-white"
                  >
                    <Check className="w-3.5 h-3.5" />
                    Approve
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    data-testid="instinct-dismiss-btn"
                    onClick={() => handleReject(draft)}
                    disabled={processingId === draft.id}
                    className="h-8 gap-1.5 text-muted-foreground hover:text-destructive"
                  >
                    <X className="w-3.5 h-3.5" />
                    Dismiss
                  </Button>
                </div>
              )}
            </div>
            
            {draft.content && (
              <div className="mt-4 pt-3 border-t border-border/50">
                <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider mb-2">Proposed Code/Rules:</p>
                <div className="bg-muted/50 rounded-lg p-3 overflow-x-auto">
                  <pre className="text-[11px] font-mono text-foreground/80 whitespace-pre-wrap break-all">
                    {draft.content.length > 300 ? draft.content.substring(0, 300) + '...' : draft.content}
                  </pre>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
