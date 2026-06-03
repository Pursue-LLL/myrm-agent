'use client';

/**
 * KanbanInlineAddForm — Two variants of the create-task form embedded in a
 * column footer: a lightweight TRIAGE one (title-only) and a full READY one
 * (title + body + deps + criteria + agent + attachments).
 *
 * [INPUT]
 * - @/services/agent::AgentListItem (POS: Agent list for the assignment dropdown.)
 *
 * [OUTPUT]
 * - Default export <KanbanInlineAddForm /> — controlled inline form.
 *
 * [POS]
 * Shared inline add form for the TRIAGE and READY columns. Single source of
 * truth for create-task UX so both columns stay in visual lockstep.
 */

import { useCallback, useEffect, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Paperclip, X } from 'lucide-react';
import type { KanbanTask } from '@/services/kanban';
import type { AgentListItem } from '@/services/agent';
import { TIMEOUT_PRESETS } from './kanban-styles';

export interface KanbanAttachment {
  file_id: string;
  filename: string;
  content_type: string;
}

type Variant = 'triage' | 'ready';

interface KanbanInlineAddFormProps {
  variant: Variant;
  title: string;
  description: string;
  selectedDeps: string[];
  showDepPicker: boolean;
  showCriteria: boolean;
  criteria: string;
  agentId: string;
  skills: string;
  maxRuntimeSeconds: number | null;
  branch: string;
  agents: AgentListItem[];
  allTasks: KanbanTask[];
  attachments: KanbanAttachment[];
  onAttachmentsChange: (attachments: KanbanAttachment[]) => void;
  onTitleChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  onSelectedDepsToggle: (taskId: string) => void;
  onShowDepPickerToggle: () => void;
  onShowCriteriaToggle: () => void;
  onCriteriaChange: (value: string) => void;
  onAgentIdChange: (value: string) => void;
  onSkillsChange: (value: string) => void;
  onMaxRuntimeChange: (value: number | null) => void;
  onBranchChange: (value: string) => void;
  onSubmit: () => void;
  onCancel: () => void;
}

export default function KanbanInlineAddForm({
  variant,
  title,
  description,
  selectedDeps,
  showDepPicker,
  showCriteria,
  criteria,
  agentId,
  skills,
  maxRuntimeSeconds,
  branch,
  agents,
  allTasks,
  attachments,
  onAttachmentsChange,
  onTitleChange,
  onDescriptionChange,
  onSelectedDepsToggle,
  onShowDepPickerToggle,
  onShowCriteriaToggle,
  onCriteriaChange,
  onAgentIdChange,
  onSkillsChange,
  onMaxRuntimeChange,
  onBranchChange,
  onSubmit,
  onCancel,
}: KanbanInlineAddFormProps) {
  const t = useTranslations('kanban');

  const handleSubmit = useCallback(() => {
    if (!title.trim()) return;
    onSubmit();
  }, [title, onSubmit]);

  const uploadFiles = useCallback(
    async (files: File[]) => {
      if (files.length === 0) return;
      const remaining = 10 - attachments.length;
      if (remaining <= 0) {
        toast.warning(t('attachmentLimitExceeded'));
        return;
      }
      const toUpload = files.slice(0, remaining);
      if (toUpload.length < files.length) {
        toast.warning(t('attachmentLimitExceeded'));
      }

      const { getApiUrl } = await import('@/lib/api');
      const results = await Promise.allSettled(
        toUpload.map(async (file) => {
          const formData = new FormData();
          formData.append('file', file);
          const resp = await fetch(getApiUrl('/files/upload'), { method: 'POST', body: formData });
          if (!resp.ok) throw new Error(`Upload failed: ${resp.status}`);
          const data = await resp.json();
          return {
            file_id: data.file_id,
            filename: data.filename,
            content_type: data.content_type,
          } as KanbanAttachment;
        }),
      );
      const newAttachments = results
        .filter((r): r is PromiseFulfilledResult<KanbanAttachment> => r.status === 'fulfilled')
        .map((r) => r.value);
      const failedCount = results.filter((r) => r.status === 'rejected').length;
      if (failedCount > 0) {
        toast.error(t('attachmentUploadError'));
      }
      if (newAttachments.length > 0) {
        onAttachmentsChange([...attachments, ...newAttachments]);
      }
    },
    [attachments, onAttachmentsChange, t],
  );

  const handleFileUpload = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(e.target.files || []);
      e.target.value = '';
      uploadFiles(files);
    },
    [uploadFiles],
  );

  const formRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = formRef.current;
    if (!el) return;
    const onPaste = (e: Event) => {
      const ce = e as ClipboardEvent;
      const items = Array.from(ce.clipboardData?.items ?? []);
      const files = items
        .filter((item) => item.kind === 'file')
        .map((item) => item.getAsFile())
        .filter((f): f is File => f !== null);
      if (files.length > 0) {
        ce.preventDefault();
        uploadFiles(files);
      }
    };
    el.addEventListener('paste', onPaste);
    return () => el.removeEventListener('paste', onPaste);
  }, [uploadFiles]);

  const removeAttachment = useCallback(
    (fileId: string) => {
      onAttachmentsChange(attachments.filter((a) => a.file_id !== fileId));
    },
    [attachments, onAttachmentsChange],
  );

  if (variant === 'triage') {
    return (
      <div className="flex flex-col gap-1.5">
        <input
          value={title}
          onChange={(e) => onTitleChange(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
          placeholder={t('triageIdeaPlaceholder')}
          className="text-sm px-2 py-1.5 rounded border bg-background focus:outline-none focus:ring-1 focus:ring-purple-500"
          autoFocus
        />
        <p className="text-[10px] text-muted-foreground italic">{t('triageHelpHint')}</p>
        <div className="flex gap-1">
          <button
            onClick={handleSubmit}
            className="text-xs px-2 py-1 rounded bg-purple-500 text-white hover:bg-purple-600 transition-colors"
          >
            {t('add')}
          </button>
          <button onClick={onCancel} className="text-xs px-2 py-1 rounded hover:bg-muted">
            {t('cancel')}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div ref={formRef} className="flex flex-col gap-1.5">
      <input
        value={title}
        onChange={(e) => onTitleChange(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
        placeholder={t('taskTitlePlaceholder')}
        className="text-sm px-2 py-1.5 rounded border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
        autoFocus
      />
      <input
        value={description}
        onChange={(e) => onDescriptionChange(e.target.value)}
        placeholder={t('taskDescPlaceholder')}
        className="text-xs px-2 py-1 rounded border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
      />

      <div>
        <button
          onClick={onShowDepPickerToggle}
          className="text-[10px] text-primary/70 hover:text-primary transition-colors"
        >
          {showDepPicker ? t('hideDeps') : `+ ${t('addDep')}`}
          {selectedDeps.length > 0 && (
            <span className="ml-1 px-1 py-0.5 rounded bg-primary/10 text-primary">{selectedDeps.length}</span>
          )}
        </button>
        {showDepPicker && (
          <div className="mt-1 max-h-20 overflow-y-auto rounded border bg-muted/20 p-1">
            {allTasks.length === 0 ? (
              <p className="text-[10px] text-muted-foreground p-1">{t('noAvailableDeps')}</p>
            ) : (
              allTasks.map((tk) => (
                <label
                  key={tk.task_id}
                  className="flex items-center gap-1.5 text-[10px] px-1.5 py-0.5 rounded hover:bg-primary/10 cursor-pointer"
                >
                  <input
                    type="checkbox"
                    checked={selectedDeps.includes(tk.task_id)}
                    onChange={() => onSelectedDepsToggle(tk.task_id)}
                    className="rounded border-muted-foreground/30"
                  />
                  <span className="truncate">{tk.title}</span>
                </label>
              ))
            )}
          </div>
        )}
      </div>

      <div>
        <button
          onClick={onShowCriteriaToggle}
          className="text-[10px] text-primary/70 hover:text-primary transition-colors"
        >
          {showCriteria ? t('hideCriteria') : `+ ${t('showCriteria')}`}
          {criteria.trim() && !showCriteria && (
            <span className="ml-1 px-1 py-0.5 rounded bg-primary/10 text-primary">1</span>
          )}
        </button>
        {showCriteria && (
          <textarea
            value={criteria}
            onChange={(e) => onCriteriaChange(e.target.value)}
            placeholder={t('criteriaPlaceholder')}
            className="mt-1 w-full text-xs px-2 py-1.5 rounded border bg-background focus:outline-none focus:ring-1 focus:ring-primary resize-none"
            rows={2}
          />
        )}
      </div>

      <input
        value={skills}
        onChange={(e) => onSkillsChange(e.target.value)}
        placeholder={t('skillsPlaceholder')}
        className="text-xs px-2 py-1 rounded border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
      />

      <input
        value={branch}
        onChange={(e) => onBranchChange(e.target.value)}
        placeholder={t('branchPlaceholder')}
        className="text-xs px-2 py-1 rounded border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
      />

      <select
        value={maxRuntimeSeconds === null ? '' : String(maxRuntimeSeconds)}
        onChange={(e) => onMaxRuntimeChange(e.target.value ? Number(e.target.value) : null)}
        className="text-xs px-2 py-1 rounded border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
      >
        <option value="">{t('timeoutDefault')}</option>
        {TIMEOUT_PRESETS.map((p) => (
          <option key={p.value} value={p.value}>
            {t(p.labelKey)}
          </option>
        ))}
      </select>

      {agents.length > 0 && (
        <select
          value={agentId}
          onChange={(e) => onAgentIdChange(e.target.value)}
          className="text-xs px-2 py-1 rounded border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
        >
          <option value="">{t('selectAgent')}</option>
          {agents.map((ag) => (
            <option key={ag.id} value={ag.id}>
              {ag.name}
            </option>
          ))}
        </select>
      )}

      {/* Attachments */}
      <div>
        <label className="flex items-center gap-1 text-[10px] text-primary/70 hover:text-primary transition-colors cursor-pointer">
          <Paperclip size={10} />
          <span>{t('attachFile')}</span>
          <input
            type="file"
            multiple
            onChange={handleFileUpload}
            className="hidden"
            accept=".png,.jpg,.jpeg,.gif,.webp,.bmp,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv,.md,.json"
          />
          {attachments.length > 0 && (
            <span className="ml-1 px-1 py-0.5 rounded bg-primary/10 text-primary">{attachments.length}</span>
          )}
        </label>
        {attachments.length > 0 && (
          <div className="mt-1 flex flex-wrap gap-1">
            {attachments.map((att) => (
              <span
                key={att.file_id}
                className="inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded bg-muted/50 border"
              >
                <span className="truncate max-w-[100px]">{att.filename}</span>
                <button
                  type="button"
                  onClick={() => removeAttachment(att.file_id)}
                  className="text-muted-foreground hover:text-foreground"
                >
                  <X size={10} />
                </button>
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="flex gap-1">
        <button
          onClick={handleSubmit}
          className="text-xs px-2 py-1 rounded bg-primary text-primary-foreground hover:bg-primary/90"
        >
          {t('add')}
        </button>
        <button onClick={onCancel} className="text-xs px-2 py-1 rounded hover:bg-muted">
          {t('cancel')}
        </button>
      </div>
    </div>
  );
}
