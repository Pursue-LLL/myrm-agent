'use client';

import { useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { toast } from 'sonner';
import { Sparkles, ShieldAlert, CheckCircle2, Info } from 'lucide-react';
import {
  writebackService,
  type ReviewSlipBatch,
  type ReviewSlipTask,
  type WritebackDecisionItem,
} from '@/services/wikiService';
import { useWikiAgentScope } from '../WikiAgentScopeContext';

interface WikiReviewSlipModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The finished task and the lessons extracted from it; keep the object stable, a new one re-requests the slip. */
  task: ReviewSlipTask;
  onApplied?: () => void;
}

export function WikiReviewSlipModal({ open, onOpenChange, task, onApplied }: WikiReviewSlipModalProps) {
  const t = useTranslations('settings.wiki.reviewSlip');
  const { agentScopeId } = useWikiAgentScope();
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [batch, setBatch] = useState<ReviewSlipBatch | null>(null);
  const [userDecisions, setUserDecisions] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!open) {
      return;
    }

    const loadCandidates = async () => {
      setLoading(true);
      try {
        const res = await writebackService.generateReviewSlips(
          {
            task_id: task.taskId,
            task_title: task.taskTitle,
            candidate_insights: task.candidateInsights,
          },
          agentScopeId,
        );

        setBatch(res);
        const initialSelections: Record<string, string> = {};
        for (const q of res.questions) {
          const rec = q.options.find((o) => o.recommended) || q.options[0];
          if (rec) {
            initialSelections[q.question_id] = rec.id;
          }
        }
        setUserDecisions(initialSelections);
      } catch (err) {
        console.error('Failed to generate review slips:', err);
        toast.error(t('fetchFailed'));
      } finally {
        setLoading(false);
      }
    };

    void loadCandidates();
  }, [open, task, agentScopeId, t]);

  const handleApply = async () => {
    if (!batch || batch.questions.length === 0) {
      onOpenChange(false);
      return;
    }

    setSubmitting(true);
    try {
      const decisionItems: WritebackDecisionItem[] = batch.questions.map((q) => {
        const selectedId = userDecisions[q.question_id];
        const opt = q.options.find((o) => o.id === selectedId) || q.options[0];
        return {
          question_id: q.question_id,
          selected_option_id: opt.id,
          target_layer: opt.target_layer,
          candidate_title: q.topic,
          candidate_content: q.candidate_content,
        };
      });

      const res = await writebackService.applyWritebackDecisions(
        {
          task_id: batch.task_id,
          decisions: decisionItems,
        },
        agentScopeId,
      );

      toast.success(t('applied', { committed: res.committed_count, discarded: res.discarded_count }));
      onOpenChange(false);
      onApplied?.();
    } catch (err) {
      console.error('Failed to apply review slip writeback:', err);
      toast.error(t('applyFailed'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] flex flex-col p-0 overflow-hidden">
        <DialogHeader className="p-6 pb-3 border-b border-border/40">
          <div className="flex items-center gap-2 text-primary font-medium text-xs">
            <Sparkles className="w-4 h-4" />
            <span>{t('engineLabel')}</span>
          </div>
          <DialogTitle className="text-xl font-bold mt-1">{t('title')}</DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground mt-0.5">{t('description')}</DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {batch && batch.excluded_matches_count > 0 && (
            <div className="p-3.5 rounded-xl border border-emerald-500/30 bg-emerald-500/5 flex items-start gap-3 text-xs">
              <ShieldAlert className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold text-emerald-700 dark:text-emerald-300">
                  {t('exclusionTitle', { count: batch.excluded_matches_count })}
                </span>
                <p className="text-muted-foreground mt-0.5 leading-relaxed">{t('exclusionBody')}</p>
              </div>
            </div>
          )}

          {loading ? (
            <div className="py-12 text-center text-xs text-muted-foreground">{t('extracting')}</div>
          ) : !batch || batch.questions.length === 0 ? (
            <div className="py-12 text-center text-xs text-muted-foreground">{t('noQuestions')}</div>
          ) : (
            batch.questions.map((q, idx) => {
              const currentChoice = userDecisions[q.question_id];
              return (
                <div
                  key={q.question_id}
                  className="p-4 rounded-xl border border-border/60 bg-card/60 shadow-sm space-y-3"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <span className="w-5 h-5 rounded-full bg-primary/10 text-primary flex items-center justify-center text-xs font-mono font-bold">
                        {idx + 1}
                      </span>
                      <h4 className="text-sm font-semibold text-foreground">{q.topic}</h4>
                    </div>
                    <Badge variant="outline" className="text-[10px] font-normal text-muted-foreground">
                      {t('pendingLayer')}
                    </Badge>
                  </div>

                  <div className="p-2.5 rounded-lg bg-secondary/30 text-xs font-mono text-muted-foreground/90 border border-border/30 whitespace-pre-wrap">
                    {q.candidate_content}
                  </div>

                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground/80">
                    <Info className="w-3.5 h-3.5 text-primary shrink-0" />
                    <span>{q.rationale}</span>
                  </div>

                  <div className="pt-2 border-t border-border/30">
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                      {q.options.map((opt) => {
                        const isSelected = currentChoice === opt.id;
                        return (
                          <button
                            key={opt.id}
                            type="button"
                            onClick={() =>
                              setUserDecisions((prev) => ({
                                ...prev,
                                [q.question_id]: opt.id,
                              }))
                            }
                            className={`flex items-center justify-between p-2.5 rounded-lg border text-xs text-left cursor-pointer transition-all ${
                              isSelected
                                ? 'border-primary bg-primary/10 text-foreground font-medium ring-1 ring-primary/40 shadow-sm'
                                : 'border-border/40 hover:bg-secondary/40 text-muted-foreground'
                            }`}
                          >
                            <div className="flex items-center gap-2">
                              <div
                                className={`w-3.5 h-3.5 rounded-full border flex items-center justify-center transition-colors ${
                                  isSelected ? 'border-primary bg-primary' : 'border-border/80'
                                }`}
                              >
                                {isSelected && <div className="w-1.5 h-1.5 rounded-full bg-primary-foreground" />}
                              </div>
                              <span>{opt.label}</span>
                            </div>
                            {opt.recommended && (
                              <Badge
                                variant="secondary"
                                className="text-[9px] px-1 py-0 bg-primary/15 text-primary border-primary/20"
                              >
                                {t('recommended')}
                              </Badge>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>

        <DialogFooter className="p-4 border-t border-border/40 bg-secondary/10 flex items-center justify-between sm:justify-between">
          <span className="text-xs text-muted-foreground">{t('footerNote')}</span>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)} disabled={submitting}>
              {t('later')}
            </Button>
            <Button
              variant="default"
              size="sm"
              onClick={handleApply}
              disabled={submitting || loading || !batch || batch.questions.length === 0}
              className="gap-1.5 shadow-sm"
            >
              <CheckCircle2 className="w-4 h-4" />
              {t('confirm')}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
