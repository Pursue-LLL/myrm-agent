'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { MessageSquarePlus, Send, GitPullRequestArrow, Trash2, Loader2 } from 'lucide-react';
import useChatStore from '@/store/useChatStore';
import { useArtifactAnnotationStore } from '@/store/useArtifactAnnotationStore';
import {
  addComment,
  listBoards,
  listTasks,
  rejectTask,
  type KanbanTask,
} from '@/services/kanban';
import {
  buildAnchor,
  composeReviewMessage,
  relocateAnchor,
  verifyRevisionLocality,
} from '@/lib/artifacts/artifactAnnotations';
import { toast } from '@/hooks/shared/useToast';
import { cn } from '@/lib/utils';

interface ArtifactAnnotationPanelProps {
  artifactId: string;
  artifactName: string;
  content: string;
  versionId: string;
  chatId?: string | null;
  versionCount: number;
  /** Parallel to versions prop order; used to map annotation version ids. */
  versionIds?: string[];
  viewingVersionIndex?: number;
  onSwitchVersion?: (index: number) => void;
}

function selectionToRange(container: HTMLElement | null, content: string): { start: number; end: number } | null {
  const selection = window.getSelection();
  if (!container || !selection || selection.isCollapsed || selection.rangeCount === 0) {
    return null;
  }
  const range = selection.getRangeAt(0);
  if (!container.contains(range.commonAncestorContainer)) {
    return null;
  }
  const text = selection.toString();
  if (!text.trim()) {
    return null;
  }
  const index = content.indexOf(text.trim().split('\n')[0]);
  if (index < 0) {
    return { start: -1, end: -1 };
  }
  const startLine = content.slice(0, index).split('\n').length;
  const spanLines = text.trim().split('\n').length;
  return { start: startLine, end: startLine + spanLines - 1 };
}

async function resolveOwningTask(chatId: string, artifactId: string): Promise<KanbanTask | null> {
  const boards = await listBoards();
  for (const board of boards.items || []) {
    let offset = 0;
    for (;;) {
      const page = await listTasks(board.board_id, { source_chat_id: chatId, limit: 50, offset });
      const hit = (page.items || []).find((t) =>
        (t.attachments || []).some((a) => a.file_id === artifactId),
      );
      if (hit) {
        return hit;
      }
      if ((page.items || []).length < 50) {
        break;
      }
      offset += 50;
    }
  }
  return null;
}

export function ArtifactAnnotationPanel({
  artifactId,
  artifactName,
  content,
  versionId,
  chatId,
  versionCount,
  versionIds,
  viewingVersionIndex,
  onSwitchVersion,
}: ArtifactAnnotationPanelProps) {
  const t = useTranslations('artifacts');
  const annotations = useArtifactAnnotationStore((s) => s.byArtifact[artifactId] || []);
  const addAnnotation = useArtifactAnnotationStore((s) => s.addAnnotation);
  const removeAnnotation = useArtifactAnnotationStore((s) => s.removeAnnotation);
  const markSubmitted = useArtifactAnnotationStore((s) => s.markSubmitted);
  const markResolved = useArtifactAnnotationStore((s) => s.markResolved);
  const hydrateFromStorage = useArtifactAnnotationStore((s) => s.hydrateFromStorage);
  const [intent, setIntent] = useState('');
  const [busy, setBusy] = useState(false);
  const [revisionNote, setRevisionNote] = useState<string | null>(null);
  const prevContentRef = useRef<string | null>(null);
  const prevArtifactRef = useRef<string | null>(null);

  useEffect(() => {
    hydrateFromStorage();
  }, [hydrateFromStorage]);

  useEffect(() => {
    if (prevArtifactRef.current !== artifactId) {
      prevArtifactRef.current = artifactId;
      prevContentRef.current = content;
      setRevisionNote(null);
      return;
    }
    const prev = prevContentRef.current;
    prevContentRef.current = content;
    if (prev === null || prev === content) {
      return;
    }
    const open = useArtifactAnnotationStore
      .getState()
      .byArtifact[artifactId]?.filter((a) => a.status !== 'resolved');
    if (!open || open.length === 0) {
      setRevisionNote(null);
      return;
    }
    const verdict = verifyRevisionLocality(
      prev,
      content,
      open.map((a) => a.anchor),
    );
    if (verdict.local) {
      setRevisionNote(t('annotation.revisionLocal', { fallback: 'Revision stayed inside the marked areas.' }));
    } else {
      setRevisionNote(
        t('annotation.revisionOutside', {
          fallback: 'Revision also touched unmarked lines: {lines}',
          lines: verdict.outsideLines.slice(0, 8).join(', '),
        }),
      );
    }
  }, [content, artifactId, t]);

  const openAnnotations = useMemo(() => annotations.filter((a) => a.status === 'open'), [annotations]);

  const latestVersionId = versionIds && versionIds.length > 0 ? versionIds[versionIds.length - 1] : undefined;
  const currentRealVersionId =
    versionIds && versionIds.length > 0
      ? (versionIds[viewingVersionIndex ?? -1] ?? latestVersionId)
      : undefined;

  const versionChips = useMemo(() => {
    if (!versionIds || versionIds.length < 2) {
      return [];
    }
    const latest = versionIds[versionIds.length - 1];
    const matches = (aVersionId: string, vid: string) =>
      aVersionId === vid || (vid === latest && (aVersionId === 'latest' || aVersionId === versionId));
    return versionIds.map((vid, index) => ({
      index,
      label: `v${index + 1}`,
      count: annotations.filter((a) => matches(a.versionId, vid)).length,
      active: viewingVersionIndex === index,
    }));
  }, [versionIds, annotations, viewingVersionIndex, versionId]);

  const handleCapture = () => {
    const container = document.getElementById('artifact-content-container');
    const range = selectionToRange(container, content);
    if (!range || !intent.trim()) {
      toast.error(t('annotation.needSelection', { fallback: 'Select text in the preview, then describe the change.' }));
      return;
    }
    const anchor = buildAnchor(content, range.start, range.end);
    addAnnotation({
      id: `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
      artifactId,
      versionId: currentRealVersionId || versionId,
      anchor,
      intent: intent.trim(),
      status: 'open',
      createdAt: new Date().toISOString(),
    });
    setIntent('');
    setRevisionNote(null);
    window.getSelection()?.removeAllRanges();
  };

  const buildPayload = () => ({
    artifactName,
    annotations: openAnnotations.map((a) => ({ anchor: a.anchor, intent: a.intent })),
  });

  const handleSendToChat = async () => {
    if (openAnnotations.length === 0) {
      return;
    }
    setBusy(true);
    try {
      await useChatStore.getState().sendMessage(composeReviewMessage(buildPayload()));
      markSubmitted(
        artifactId,
        openAnnotations.map((a) => a.id),
      );
    } catch {
      toast.error(t('annotation.sendFailed', { fallback: 'Failed to send review feedback.' }));
    } finally {
      setBusy(false);
    }
  };

  const handleSendToTask = async () => {
    if (openAnnotations.length === 0 || !chatId) {
      return;
    }
    setBusy(true);
    try {
      const task = await resolveOwningTask(chatId, artifactId);
      if (!task) {
        toast.error(t('annotation.noLinkedTask', { fallback: 'No linked review task found for this file.' }));
        return;
      }
      const body = composeReviewMessage(buildPayload());
      await addComment(task.task_id, body, 'user');
      if (task.status === 'in_review') {
        await rejectTask(task.task_id, body.slice(0, 500));
      }
      markSubmitted(
        artifactId,
        openAnnotations.map((a) => a.id),
      );
      toast.success(t('annotation.sentToTask', { fallback: 'Feedback sent back for revision.' }));
    } catch {
      toast.error(t('annotation.sendFailed', { fallback: 'Failed to send review feedback.' }));
    } finally {
      setBusy(false);
    }
  };

  const statusLabel = (status: string) => {
    if (status === 'submitted') {
      return t('annotation.statusSubmitted', { fallback: 'submitted' });
    }
    if (status === 'resolved') {
      return t('annotation.statusResolved', { fallback: 'resolved' });
    }
    return t('annotation.statusOpen', { fallback: 'open' });
  };

  return (
    <section className="rounded-xl border bg-card p-4 space-y-3" aria-label="Artifact annotations">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">
          {t('annotation.title', { fallback: 'Review comments' })} ({annotations.length})
        </h3>
        <span className="text-xs text-muted-foreground">
          {t('annotation.versions', { fallback: '{count} versions', count: versionCount })}
        </span>
      </div>
      {revisionNote && (
        <output className="block text-xs text-amber-600 dark:text-amber-400">{revisionNote}</output>
      )}
      {versionChips.length > 0 && (
        <nav className="flex flex-wrap items-center gap-1.5" aria-label="versions">
          {versionChips.map((chip) => (
            <button
              key={chip.index}
              type="button"
              disabled={!onSwitchVersion}
              onClick={() => onSwitchVersion?.(chip.index)}
              className={cn(
                'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs',
                chip.active
                  ? 'border-primary/50 bg-primary/10 text-primary'
                  : 'border-border/60 text-muted-foreground hover:text-foreground',
              )}
            >
              {chip.label}
              {chip.count > 0 && (
                <span className="inline-flex items-center justify-center min-w-4 h-4 rounded-full bg-primary/15 px-1 text-[10px] font-semibold">
                  {chip.count}
                </span>
              )}
            </button>
          ))}
        </nav>
      )}

      <div className="flex flex-col sm:flex-row gap-2">
        <Input
          value={intent}
          onChange={(e) => setIntent(e.target.value)}
          placeholder={t('annotation.intentPlaceholder', { fallback: 'Describe the change, then select text' })}
          maxLength={500}
          className="flex-1"
        />
        <Button variant="outline" size="sm" className="h-9" onClick={handleCapture}>
          <MessageSquarePlus className="mr-2 h-4 w-4" />
          {t('annotation.add', { fallback: 'Add comment' })}
        </Button>
      </div>

      {annotations.length > 0 && (
        <ul className="space-y-2 max-h-56 overflow-y-auto pr-1">
          {annotations.map((a) => {
            const relocated = relocateAnchor(content, a.anchor);
            return (
              <li key={a.id} className="rounded-lg border border-border/60 p-2.5 text-sm">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm font-medium break-words flex-1">{a.intent}</p>
                  <div className="flex items-center gap-1 shrink-0">
                    {a.status === 'submitted' && (
                      <button
                        type="button"
                        onClick={() => markResolved(artifactId, [a.id])}
                        className="text-xs text-emerald-600 dark:text-emerald-400 hover:underline"
                      >
                        {t('annotation.resolve', { fallback: 'Mark resolved' })}
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => removeAnnotation(artifactId, a.id)}
                      className="text-muted-foreground hover:text-destructive"
                      aria-label={t('annotation.remove', { fallback: 'Remove comment' })}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
                <p className="text-xs text-muted-foreground mt-1 break-words">
                  {a.anchor.startLine < 0
                    ? t('annotation.wholeDoc', { fallback: 'Whole document' })
                    : t('annotation.lines', {
                        fallback: 'Lines {from}-{to}',
                        from: relocated?.startLine ?? a.anchor.startLine,
                        to: relocated?.endLine ?? a.anchor.endLine,
                      })}
                  {' · '}
                  {statusLabel(a.status)}
                  {!relocated && (
                    <span className="text-amber-600 dark:text-amber-400">
                      {' · '}
                      {t('annotation.driftedShort', { fallback: 'moved' })}
                    </span>
                  )}
                </p>
                <p className="text-xs text-muted-foreground mt-1 line-clamp-2 break-words">{a.anchor.excerpt}</p>
              </li>
            );
          })}
        </ul>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" className="h-8" disabled={busy || openAnnotations.length === 0} onClick={handleSendToChat}>
          {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          <Send className="mr-2 h-4 w-4" />
          {t('annotation.sendToChat', { fallback: 'Send for revision' })}
        </Button>
        <Button
          size="sm"
          variant="outline"
          className="h-8"
          disabled={busy || openAnnotations.length === 0 || !chatId}
          onClick={handleSendToTask}
        >
          <GitPullRequestArrow className="mr-2 h-4 w-4" />
          {t('annotation.sendToTask', { fallback: 'Return to task' })}
        </Button>
      </div>

      <div className="space-y-1">
        <Label className="text-xs text-muted-foreground">
          {t('annotation.howItWorks', {
            fallback: 'Comments ride along until you send them; the agent revises only the marked parts.',
          })}
        </Label>
      </div>
    </section>
  );
}
