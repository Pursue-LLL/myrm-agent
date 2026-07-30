'use client';

/**
 * [INPUT] @/store/useMilestoneStore, @/store/useProjectStore, ./assessmentImportError::resolveAssessmentImportErrorMessage
 * [OUTPUT] ProjectMilestonePanel: 项目里程碑管理面板
 * [POS] 在侧边栏显示当前项目的里程碑列表，支持创建、完成、删除与评估工件导入（最近候选一键导入 + 手输兜底）。
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Check, Plus, Target, Trash2, ChevronDown, ChevronRight, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { useToast } from '@/hooks/shared/useToast';
import { useMilestoneStore } from '@/store/useMilestoneStore';
import { useProjectStore } from '@/store/useProjectStore';
import { resolveAssessmentImportErrorMessage } from './assessmentImportError';
import {
  listAssessmentImportArtifactCandidates,
  type AssessmentImportArtifactCandidate,
  type Milestone,
} from '@/services/milestones';
import { useTranslations } from 'next-intl';

export default function ProjectMilestonePanel() {
  const t = useTranslations();
  const { error: toastError, success: toastSuccess } = useToast();
  const { activeFilter, projects } = useProjectStore();
  const { milestones, loading, fetchMilestones, addMilestone, completeMilestone, removeMilestone, importAssessment } =
    useMilestoneStore();
  const [expanded, setExpanded] = useState(false);
  const [showInput, setShowInput] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const [importArtifactId, setImportArtifactId] = useState('');
  const [importing, setImporting] = useState(false);
  const [lastImportSummary, setLastImportSummary] = useState<{ milestones: number; tasks: number } | null>(null);
  const [artifactCandidates, setArtifactCandidates] = useState<AssessmentImportArtifactCandidate[]>([]);
  const [artifactCandidatesLoaded, setArtifactCandidatesLoaded] = useState(false);
  const [artifactCandidatesLoading, setArtifactCandidatesLoading] = useState(false);
  const [artifactCandidatesLoadFailed, setArtifactCandidatesLoadFailed] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const candidateRequestIdRef = useRef(0);

  const activeProject = typeof activeFilter === 'string' ? projects.find((p) => p.id === activeFilter) : null;

  useEffect(() => {
    if (activeProject) {
      fetchMilestones(activeProject.id);
    }
  }, [activeProject, fetchMilestones]);

  useEffect(() => {
    if (showInput) inputRef.current?.focus();
  }, [showInput]);

  useEffect(() => {
    candidateRequestIdRef.current += 1;
    setArtifactCandidates([]);
    setArtifactCandidatesLoaded(false);
    setArtifactCandidatesLoading(false);
    setArtifactCandidatesLoadFailed(false);
  }, [activeProject?.id]);

  const handleAddSubmit = useCallback(async () => {
    const title = inputValue.trim();
    if (!title || !activeProject) {
      setShowInput(false);
      setInputValue('');
      return;
    }
    try {
      await addMilestone(activeProject.id, title);
      setInputValue('');
      setShowInput(false);
    } catch {
      toastError(t('common.operationFailed'));
    }
  }, [inputValue, activeProject, addMilestone, toastError, t]);

  const handleComplete = useCallback(
    async (ms: Milestone) => {
      if (!activeProject) return;
      try {
        await completeMilestone(activeProject.id, ms.id);
      } catch {
        toastError(t('common.operationFailed'));
      }
    },
    [activeProject, completeMilestone, toastError, t],
  );

  const handleDelete = useCallback(
    async (ms: Milestone) => {
      if (!activeProject) return;
      try {
        await removeMilestone(activeProject.id, ms.id);
      } catch {
        toastError(t('common.operationFailed'));
      }
    },
    [activeProject, removeMilestone, toastError, t],
  );

  const loadArtifactCandidates = useCallback(async (projectId: string) => {
    if (artifactCandidatesLoading) {
      return;
    }
    const requestId = candidateRequestIdRef.current + 1;
    candidateRequestIdRef.current = requestId;
    setArtifactCandidatesLoading(true);
    setArtifactCandidatesLoadFailed(false);
    try {
      const candidates = await listAssessmentImportArtifactCandidates(12);
      if (candidateRequestIdRef.current !== requestId) {
        return;
      }
      if (activeProject?.id !== projectId) {
        return;
      }
      setArtifactCandidates(candidates);
    } catch {
      if (candidateRequestIdRef.current !== requestId) {
        return;
      }
      setArtifactCandidatesLoadFailed(true);
    } finally {
      if (candidateRequestIdRef.current === requestId) {
        setArtifactCandidatesLoaded(true);
        setArtifactCandidatesLoading(false);
      }
    }
  }, [activeProject?.id, artifactCandidatesLoading]);

  useEffect(() => {
    if (!expanded || !activeProject || artifactCandidatesLoaded || artifactCandidatesLoading) {
      return;
    }
    void loadArtifactCandidates(activeProject.id);
  }, [
    expanded,
    activeProject,
    artifactCandidatesLoaded,
    artifactCandidatesLoading,
    loadArtifactCandidates,
  ]);

  const executeImportAssessment = useCallback(async (rawArtifactId: string) => {
    if (!activeProject) return;
    const artifactId = rawArtifactId.trim();
    if (!artifactId) {
      toastError(t('milestone.importArtifactRequired'));
      return;
    }
    setImportArtifactId(artifactId);
    setImporting(true);
    try {
      const receipt = await importAssessment(activeProject.id, { artifact_id: artifactId });
      setImportArtifactId('');
      setLastImportSummary({ milestones: receipt.total_milestones, tasks: receipt.total_tasks });
      toastSuccess(
        t('milestone.importSuccess', {
          milestones: receipt.total_milestones,
          tasks: receipt.total_tasks,
        }),
      );
    } catch (error) {
      toastError(resolveAssessmentImportErrorMessage(error, t));
    } finally {
      setImporting(false);
    }
  }, [activeProject, importAssessment, toastError, toastSuccess, t]);

  const handleImportAssessment = useCallback(async () => {
    await executeImportAssessment(importArtifactId);
  }, [executeImportAssessment, importArtifactId]);

  const filteredArtifactCandidates = useMemo(() => {
    const query = importArtifactId.trim().toLowerCase();
    if (!query) {
      return artifactCandidates;
    }
    return artifactCandidates.filter((candidate) => {
      return candidate.id.toLowerCase().includes(query) || candidate.name.toLowerCase().includes(query);
    });
  }, [artifactCandidates, importArtifactId]);

  if (!activeProject) return null;

  const activeMilestones = milestones.filter((m) => m.status === 'active');
  const completedMilestones = milestones.filter((m) => m.status === 'completed');

  return (
    <div className="px-2 pb-1">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1 text-[10px] text-muted-foreground/70 hover:text-foreground transition-colors w-full"
      >
        {expanded ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
        <Target size={10} />
        <span className="font-medium">
          {t('milestone.title')} ({activeMilestones.length})
        </span>
      </button>

      {expanded && (
        <div className="mt-1 ml-3 space-y-0.5">
          {loading && <div className="text-[9px] text-muted-foreground/50">{t('common.loading')}</div>}

          {activeMilestones.map((ms) => (
            <MilestoneRow key={ms.id} milestone={ms} onComplete={handleComplete} onDelete={handleDelete} />
          ))}

          {completedMilestones.length > 0 && (
            <div className="pt-0.5 border-t border-border/20">
              {completedMilestones.slice(-3).map((ms) => (
                <div key={ms.id} className="flex items-center gap-1 text-[9px] text-muted-foreground/40 line-through">
                  <Check size={8} />
                  <span className="truncate">{ms.title}</span>
                </div>
              ))}
            </div>
          )}

          {showInput ? (
            <input
              ref={inputRef}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onBlur={handleAddSubmit}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleAddSubmit();
                if (e.key === 'Escape') {
                  setShowInput(false);
                  setInputValue('');
                }
              }}
              placeholder={t('milestone.addPlaceholder')}
              className="w-full h-4 px-1.5 text-[9px] rounded border border-primary/30 bg-transparent outline-none placeholder:text-muted-foreground/40"
            />
          ) : (
            <button
              onClick={() => setShowInput(true)}
              className="flex items-center gap-0.5 text-[9px] text-muted-foreground/50 hover:text-muted-foreground transition-colors"
            >
              <Plus size={8} />
              <span>{t('milestone.add')}</span>
            </button>
          )}

          <div className="pt-1 border-t border-border/20 space-y-1">
            <input
              value={importArtifactId}
              onChange={(event) => setImportArtifactId(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault();
                  void handleImportAssessment();
                }
              }}
              placeholder={t('milestone.importPlaceholder')}
              className="w-full h-5 px-1.5 text-[9px] rounded border border-border/40 bg-transparent outline-none placeholder:text-muted-foreground/40"
            />
            <button
              onClick={() => {
                void handleImportAssessment();
              }}
              disabled={importing}
              className="flex items-center gap-1 text-[9px] text-muted-foreground/70 hover:text-foreground disabled:opacity-50 transition-colors"
            >
              {importing ? <Loader2 size={8} className="animate-spin" /> : <Plus size={8} />}
              <span>{importing ? t('milestone.importing') : t('milestone.importAction')}</span>
            </button>
            <div className="space-y-0.5">
              <div className="text-[9px] text-muted-foreground/55">{t('milestone.importRecentLabel')}</div>
              {artifactCandidatesLoading ? (
                <div className="text-[9px] text-muted-foreground/45">{t('common.loading')}</div>
              ) : artifactCandidatesLoadFailed ? (
                <div className="flex items-center gap-1 text-[9px] text-muted-foreground/45">
                  <span>{t('milestone.importRecentLoadFailed')}</span>
                  <button
                    onClick={() => {
                      setArtifactCandidatesLoaded(false);
                      if (!activeProject) {
                        return;
                      }
                      void loadArtifactCandidates(activeProject.id);
                    }}
                    className="text-primary/80 hover:text-primary transition-colors"
                  >
                    {t('common.retry')}
                  </button>
                </div>
              ) : filteredArtifactCandidates.length > 0 ? (
                <div className="max-h-20 space-y-0.5 overflow-y-auto pr-0.5">
                  {filteredArtifactCandidates.map((candidate) => (
                    <button
                      key={candidate.id}
                      onClick={() => {
                        void executeImportAssessment(candidate.id);
                      }}
                      disabled={importing}
                      className="w-full rounded border border-border/30 px-1.5 py-1 text-left text-[9px] text-muted-foreground/75 hover:border-primary/40 hover:text-foreground disabled:opacity-50 transition-colors"
                    >
                      <div className="truncate">{candidate.name}</div>
                      <div className="truncate text-[8px] text-muted-foreground/45">{candidate.id}</div>
                    </button>
                  ))}
                </div>
              ) : (
                <div className="text-[9px] text-muted-foreground/45">{t('milestone.importRecentEmpty')}</div>
              )}
            </div>
            {lastImportSummary && (
              <div className="text-[9px] text-muted-foreground/60">
                {t('milestone.importReceipt', {
                  milestones: lastImportSummary.milestones,
                  tasks: lastImportSummary.tasks,
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function MilestoneRow({
  milestone,
  onComplete,
  onDelete,
}: {
  milestone: Milestone;
  onComplete: (ms: Milestone) => void;
  onDelete: (ms: Milestone) => void;
}) {
  const [open, setOpen] = useState(false);
  const hasDetails = milestone.description || milestone.acceptanceCriteria;

  return (
    <div>
      <div className="group flex items-center gap-1 text-[10px] text-foreground/80">
        <button
          onClick={() => onComplete(milestone)}
          className={cn(
            'w-3 h-3 rounded-sm border border-muted-foreground/30 flex items-center justify-center shrink-0',
            'hover:border-primary/60 hover:bg-primary/10 transition-colors',
          )}
        >
          {milestone.status === 'completed' && <Check size={8} className="text-primary" />}
        </button>
        <span
          className={cn('truncate flex-1', hasDetails && 'cursor-pointer hover:text-primary/80')}
          onClick={() => hasDetails && setOpen(!open)}
        >
          {milestone.title}
        </span>
        <button
          onClick={() => onDelete(milestone)}
          className="opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground/40 hover:text-destructive"
        >
          <Trash2 size={8} />
        </button>
      </div>
      {open && hasDetails && (
        <div className="ml-4 mt-0.5 text-[9px] text-muted-foreground/60 space-y-0.5">
          {milestone.description && <p className="line-clamp-2">{milestone.description}</p>}
          {milestone.acceptanceCriteria && (
            <p className="line-clamp-1 italic">{milestone.acceptanceCriteria}</p>
          )}
        </div>
      )}
    </div>
  );
}
