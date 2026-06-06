'use client';

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Layers, ChevronRight, ChevronLeft, Loader2, X } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import type { PipelineTemplate, PipelineTemplateDetail, PipelineQuestionGroup } from '@/services/kanban';
import { listPipelines, getPipelineDetail, instantiatePipeline } from '@/services/kanban';

interface KanbanPipelineWizardProps {
  boardId: string;
  open: boolean;
  onClose: () => void;
  onCreated: (taskCount: number) => void;
}

type WizardStep = 'select' | 'configure' | 'creating';

export default function KanbanPipelineWizard({ boardId, open, onClose, onCreated }: KanbanPipelineWizardProps) {
  const t = useTranslations('kanban');
  const [step, setStep] = useState<WizardStep>('select');
  const [templates, setTemplates] = useState<PipelineTemplate[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState<PipelineTemplateDetail | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [selectedVariantId, setSelectedVariantId] = useState<string | undefined>();
  const [currentGroupIdx, setCurrentGroupIdx] = useState(0);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    if (!open) return;
    setStep('select');
    setSelectedTemplate(null);
    setAnswers({});
    setCurrentGroupIdx(0);
    setLoading(true);
    listPipelines()
      .then((res) => setTemplates(res.items))
      .catch(() => toast.error(t('pipelineLoadError')))
      .finally(() => setLoading(false));
  }, [open, t]);

  useEffect(() => {
    if (!open) return;
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !creating) onClose();
    };
    document.addEventListener('keydown', handleEsc);
    return () => document.removeEventListener('keydown', handleEsc);
  }, [open, creating, onClose]);

  const handleSelectTemplate = useCallback(
    async (template: PipelineTemplate) => {
      setLoading(true);
      try {
        const detail = await getPipelineDetail(template.skill_id);
        setSelectedTemplate(detail);
        setAnswers({});
        setSelectedVariantId(detail.task_graph_variants?.[0]?.id);
        setCurrentGroupIdx(0);
        setStep('configure');
      } catch {
        toast.error(t('pipelineLoadError'));
      } finally {
        setLoading(false);
      }
    },
    [t],
  );

  const handleCreate = useCallback(async () => {
    if (!selectedTemplate) return;
    setCreating(true);
    setStep('creating');
    try {
      const result = await instantiatePipeline(boardId, {
        skill_id: selectedTemplate.skill_id,
        answers,
        variant_id: selectedVariantId,
      });
      toast.success(t('pipelineCreated', { count: result.task_ids.length }));
      onCreated(result.task_ids.length);
      onClose();
    } catch {
      toast.error(t('pipelineError'));
      setStep('configure');
    } finally {
      setCreating(false);
    }
  }, [boardId, selectedTemplate, answers, onCreated, onClose, t]);

  const updateAnswer = (questionId: string, value: string) => {
    setAnswers((prev) => ({ ...prev, [questionId]: value }));
  };

  if (!open) return null;

  const groups = selectedTemplate?.discovery_questions ?? [];
  const currentGroup: PipelineQuestionGroup | undefined = groups[currentGroupIdx];
  const isLastGroup = currentGroupIdx >= groups.length - 1;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 dark:bg-black/60">
      <div className="w-[calc(100vw-32px)] sm:w-full max-w-[680px] max-h-[80vh] rounded-xl border border-border bg-background shadow-xl overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-primary" />
            <h2 className="text-base font-semibold">
              {step === 'select' ? t('pipelineSelectTitle') : t('pipelineWizardTitle')}
            </h2>
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-muted transition-colors" disabled={creating}>
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5">
          {step === 'select' && (
            <TemplateSelector templates={templates} loading={loading} onSelect={handleSelectTemplate} t={t} />
          )}

          {step === 'configure' && currentGroupIdx === 0 && selectedTemplate?.task_graph_variants && selectedTemplate.task_graph_variants.length > 0 && (
            <div className="mb-6 space-y-3">
              <h3 className="text-sm font-medium">{t('pipelineWizardSelectMode')}</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {selectedTemplate.task_graph_variants.map((variant) => (
                  <button
                    key={variant.id}
                    onClick={() => setSelectedVariantId(variant.id)}
                    className={cn(
                      "text-left p-3 rounded-lg border transition-all",
                      selectedVariantId === variant.id 
                        ? "border-primary bg-primary/5 ring-1 ring-primary" 
                        : "border-border hover:border-primary/50"
                    )}
                  >
                    <h4 className="text-sm font-medium">{variant.label}</h4>
                    <p className="text-xs text-muted-foreground mt-1">{variant.description}</p>
                    <div className="mt-2 text-[10px] text-muted-foreground">
                      {t('pipelineTaskCount', { count: variant.seeds.length })}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {step === 'configure' && currentGroup && (
            <QuestionGroupForm group={currentGroup} answers={answers} onAnswer={updateAnswer} />
          )}

          {step === 'creating' && (
            <div className="flex flex-col items-center justify-center py-12 gap-3">
              <Loader2 className="w-8 h-8 animate-spin text-primary" />
              <p className="text-sm text-muted-foreground">{t('pipelineWizardCreating')}</p>
            </div>
          )}
        </div>

        {/* Footer */}
        {step === 'configure' && (
          <div className="flex items-center justify-between px-5 py-3 border-t border-border">
            <button
              onClick={() => {
                if (currentGroupIdx > 0) setCurrentGroupIdx((i) => i - 1);
                else setStep('select');
              }}
              className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
              {currentGroupIdx > 0 ? t('pipelineWizardBack') : t('pipelineSelectTitle')}
            </button>

            <div className="flex items-center gap-1.5">
              {groups.map((_, idx) => (
                <span
                  key={idx}
                  className={cn(
                    'w-1.5 h-1.5 rounded-full transition-colors',
                    idx === currentGroupIdx ? 'bg-primary' : 'bg-muted-foreground/30',
                  )}
                />
              ))}
            </div>

            {isLastGroup ? (
              <button
                onClick={handleCreate}
                disabled={creating}
                className="flex items-center gap-1 text-sm px-3 py-1.5 rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
              >
                {t('pipelineWizardCreate')}
              </button>
            ) : (
              <button
                onClick={() => setCurrentGroupIdx((i) => i + 1)}
                className="flex items-center gap-1 text-sm text-primary hover:text-primary/80 transition-colors"
              >
                {t('pipelineWizardNext')}
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// --- Sub-components ---

function TemplateSelector({
  templates,
  loading,
  onSelect,
  t,
}: {
  templates: PipelineTemplate[];
  loading: boolean;
  onSelect: (t: PipelineTemplate) => void;
  t: ReturnType<typeof useTranslations<'kanban'>>;
}) {
  if (loading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-28 rounded-lg bg-muted/30 animate-pulse" />
        ))}
      </div>
    );
  }

  if (templates.length === 0) {
    return <p className="text-center text-sm text-muted-foreground py-8">{t('pipelineNoTemplates')}</p>;
  }

  return (
    <div className="space-y-2">
      <p className="text-xs text-muted-foreground mb-3">{t('pipelineSelectDesc')}</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {templates.map((template) => (
          <button
            key={template.skill_id}
            onClick={() => onSelect(template)}
            className="text-left p-4 rounded-lg border border-border hover:border-primary/50 hover:bg-primary/5 transition-all group"
          >
            <h3 className="text-sm font-medium group-hover:text-primary transition-colors truncate">{template.name}</h3>
            <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{template.description}</p>
            <div className="flex items-center gap-2 mt-2 text-[10px] text-muted-foreground">
              <span className="px-1.5 py-0.5 rounded bg-muted">
                {t('pipelineTaskCount', { count: template.task_count })}
              </span>
              {template.roles.length > 0 && (
                <span className="truncate">
                  {template.roles.slice(0, 3).join(', ')}
                  {template.roles.length > 3 && '...'}
                </span>
              )}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

function QuestionGroupForm({
  group,
  answers,
  onAnswer,
}: {
  group: PipelineQuestionGroup;
  answers: Record<string, string>;
  onAnswer: (id: string, value: string) => void;
}) {
  return (
    <div className="space-y-4">
      <h3 className="text-sm font-medium">{group.group_label}</h3>
      {group.questions.map((q) => (
        <div key={q.id} className="space-y-1.5">
          <label className="text-xs font-medium text-muted-foreground">{q.label}</label>
          {q.type === 'select' && (
            <select
              value={answers[q.id] ?? ''}
              onChange={(e) => onAnswer(q.id, e.target.value)}
              className="w-full px-3 py-2 text-sm rounded-md border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="">—</option>
              {q.options.map((opt) => (
                <option key={opt} value={opt}>
                  {opt}
                </option>
              ))}
            </select>
          )}
          {q.type === 'text' && (
            <input
              type="text"
              value={answers[q.id] ?? ''}
              onChange={(e) => onAnswer(q.id, e.target.value)}
              className="w-full px-3 py-2 text-sm rounded-md border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
              placeholder={q.label}
            />
          )}
          {q.type === 'textarea' && (
            <textarea
              value={answers[q.id] ?? ''}
              onChange={(e) => onAnswer(q.id, e.target.value)}
              className="w-full px-3 py-2 text-sm rounded-md border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary resize-y min-h-[80px]"
              placeholder={q.label}
            />
          )}
          {q.type === 'multi-select' && (
            <div className="flex flex-wrap gap-1.5">
              {q.options.map((opt) => {
                const selected = (answers[q.id] ?? '').split(',').filter(Boolean);
                const isSelected = selected.includes(opt);
                return (
                  <button
                    key={opt}
                    type="button"
                    onClick={() => {
                      const next = isSelected ? selected.filter((s) => s !== opt) : [...selected, opt];
                      onAnswer(q.id, next.join(','));
                    }}
                    className={cn(
                      'text-xs px-2 py-1 rounded-full border transition-colors',
                      isSelected
                        ? 'bg-primary/10 border-primary/40 text-primary'
                        : 'border-border text-muted-foreground hover:border-primary/30',
                    )}
                  >
                    {opt}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
