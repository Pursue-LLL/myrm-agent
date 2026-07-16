'use client';

import type { RefObject } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import type { KanbanTask } from '@/services/kanban';
import KanbanMarkdown from './KanbanMarkdown';
import { Paperclip, X, FileText } from 'lucide-react';

// --- Attachments Section ---

interface AttachmentsSectionProps {
  task: KanbanTask;
  dragOver: boolean;
  setDragOver: (v: boolean) => void;
  uploadingAttachment: boolean;
  attachInputRef: RefObject<HTMLInputElement | null>;
  handleDrop: (e: React.DragEvent) => void;
  handleAttachUpload: (files: File[]) => void;
  handleRemoveAttachment: (fileId: string) => void;
  t: (key: string) => string;
}

export function AttachmentsSection({
  task,
  dragOver,
  setDragOver,
  uploadingAttachment,
  attachInputRef,
  handleDrop,
  handleAttachUpload,
  handleRemoveAttachment,
  t,
}: AttachmentsSectionProps) {
  return (
    <section
      className={cn(
        'rounded-lg border px-3 py-2 transition-colors',
        dragOver ? 'border-primary bg-primary/5' : 'border-border',
      )}
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragOver(false);
      }}
      onDrop={handleDrop}
    >
      <div className="flex items-center justify-between mb-1.5">
        <h4 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1">
          <Paperclip className="w-3 h-3" />
          {t('attachments')}
          {(task.attachments ?? []).length > 0 && (
            <span className="text-[10px] text-primary font-normal">({(task.attachments ?? []).length})</span>
          )}
        </h4>
        <button
          onClick={() => attachInputRef.current?.click()}
          disabled={uploadingAttachment}
          className="text-[10px] px-1.5 py-0.5 rounded hover:bg-primary/10 text-primary/70 hover:text-primary transition-colors disabled:opacity-50"
        >
          {uploadingAttachment ? t('uploading') : `+ ${t('addAttachment')}`}
        </button>
        <input
          ref={attachInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={(e) => {
            const files = Array.from(e.target.files || []);
            e.target.value = '';
            handleAttachUpload(files);
          }}
        />
      </div>
      {(task.attachments ?? []).length > 0 ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
          {(task.attachments ?? []).map((att) => {
            const isImage = att.content_type.startsWith('image/');
            return (
              <div key={att.file_id} className="group/att relative rounded border bg-muted/30 overflow-hidden">
                {isImage ? (
                  <a href={att.url} target="_blank" rel="noopener noreferrer" className="block">
                    <img
                      src={att.url}
                      alt={att.filename}
                      className="w-full h-16 object-cover hover:opacity-80 transition-opacity"
                      loading="lazy"
                    />
                  </a>
                ) : (
                  <a
                    href={att.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1.5 px-2 py-2 hover:bg-muted/50 transition-colors"
                  >
                    <FileText className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                    <span className="text-[10px] text-foreground/80 truncate">{att.filename}</span>
                  </a>
                )}
                <button
                  onClick={() => handleRemoveAttachment(att.file_id)}
                  className="absolute top-0.5 right-0.5 w-4 h-4 rounded-full bg-destructive/80 text-destructive-foreground flex items-center justify-center opacity-0 group-hover/att:opacity-100 transition-opacity"
                  title={t('removeAttachment')}
                >
                  <X className="w-2.5 h-2.5" />
                </button>
              </div>
            );
          })}
        </div>
      ) : (
        <p className="text-[10px] text-muted-foreground/60 text-center py-2">
          {dragOver ? t('dropFilesHere') : t('noAttachments')}
        </p>
      )}
    </section>
  );
}

// --- Task Result Section ---

interface TaskResultSectionProps {
  task: KanbanTask;
  isTerminal: boolean;
  editingResult: boolean;
  setEditingResult: (v: boolean) => void;
  resultText: string;
  setResultText: (v: string) => void;
  savingResult: boolean;
  handleSaveResult: () => void;
  t: (key: string) => string;
}

export function TaskResultSection({
  task,
  isTerminal,
  editingResult,
  setEditingResult,
  resultText,
  setResultText,
  savingResult,
  handleSaveResult,
  t,
}: TaskResultSectionProps) {
  if (!task.result && !isTerminal) return null;

  return (
    <div className="rounded-lg border bg-muted/20 px-3 py-2">
      <div className="flex items-center justify-between mb-1">
        <h4 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{t('taskResult')}</h4>
        {isTerminal && !editingResult && (
          <button
            onClick={() => {
              setResultText(task.result || '');
              setEditingResult(true);
            }}
            className="text-[10px] px-1.5 py-0.5 rounded hover:bg-primary/10 text-primary/70 hover:text-primary transition-colors"
          >
            {t('edit')}
          </button>
        )}
      </div>
      {editingResult ? (
        <div className="space-y-1.5">
          <textarea
            value={resultText}
            onChange={(e) => setResultText(e.target.value)}
            rows={4}
            className="w-full rounded border bg-background px-2 py-1.5 text-sm resize-y focus:outline-none focus:ring-1 focus:ring-primary"
            maxLength={10000}
          />
          <div className="flex gap-1.5 justify-end">
            <button
              onClick={() => setEditingResult(false)}
              className="text-[11px] px-2 py-0.5 rounded border hover:bg-muted transition-colors"
            >
              {t('cancel')}
            </button>
            <button
              onClick={handleSaveResult}
              disabled={savingResult}
              className="text-[11px] px-2 py-0.5 rounded bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              {savingResult ? t('saving') : t('save')}
            </button>
          </div>
        </div>
      ) : task.result ? (
        <KanbanMarkdown className="text-foreground/80" maxLines={6}>
          {task.result}
        </KanbanMarkdown>
      ) : (
        <p className="text-xs text-muted-foreground italic">{t('noResult')}</p>
      )}
    </div>
  );
}

export { DependenciesSection, CommentInputSection, LatestProgressSection } from './KanbanTaskDrawerBodyMetaSections';
