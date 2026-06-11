'use client';

import { memo, useState, useEffect, useCallback, type KeyboardEvent } from 'react';
import { useTranslations } from 'next-intl';
import { Loader2, Save, X } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/primitives/dialog';
import type { Memory, MemoryType } from '@/store/memory';
import { useMemoryStore } from '@/store/memory';
import MemoryTypeIcon from './MemoryTypeIcon';
import { toast } from '@/hooks/useToast';

interface MemoryEditDialogProps {
  memory: Memory | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const EDITABLE_TYPES: MemoryType[] = ['semantic', 'episodic', 'procedural'];

const MemoryEditDialog = memo<MemoryEditDialogProps>(({ memory, open, onOpenChange }) => {
  const t = useTranslations('memory');
  const { updateMemory } = useMemoryStore();

  const [content, setContent] = useState('');
  const [reasoning, setReasoning] = useState('');
  const [application, setApplication] = useState('');
  const [importance, setImportance] = useState('0.5');
  const [tags, setTags] = useState<string[]>([]);
  const [tagInput, setTagInput] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (memory) {
      setContent(memory.content);
      setReasoning(memory.reasoning ?? '');
      setApplication(memory.application ?? '');
      setImportance((memory.importance ?? 0.5).toString());
      setTags(memory.tags ?? []);
      setTagInput('');
    }
  }, [memory]);

  const supportsTag = memory && (memory.memory_type === 'semantic' || memory.memory_type === 'episodic');

  const addTag = useCallback((raw: string) => {
    const tag = raw.trim().toLowerCase();
    if (!tag) return;
    setTags((prev) => prev.includes(tag) ? prev : [...prev, tag]);
  }, []);

  const removeTag = useCallback((tag: string) => {
    setTags((prev) => prev.filter((t) => t !== tag));
  }, []);

  const handleTagKeyDown = useCallback((e: KeyboardEvent<HTMLInputElement>) => {
    if ((e.key === 'Enter' || e.key === ',') && tagInput.trim()) {
      e.preventDefault();
      addTag(tagInput);
      setTagInput('');
    } else if (e.key === 'Backspace' && !tagInput && tags.length > 0) {
      removeTag(tags[tags.length - 1]);
    }
  }, [tagInput, tags, addTag, removeTag]);

  const canEdit = memory && EDITABLE_TYPES.includes(memory.memory_type);

  const tagsChanged = memory && JSON.stringify(tags) !== JSON.stringify(memory.tags ?? []);

  const isChanged =
    memory && (
      content.trim() !== memory.content || 
      reasoning.trim() !== (memory.reasoning ?? '') ||
      application.trim() !== (memory.application ?? '') ||
      parseFloat(importance) !== (memory.importance ?? 0.5) ||
      tagsChanged
    );

  const handleSave = useCallback(async () => {
    if (!memory || !canEdit || !isChanged) return;
    setIsSubmitting(true);
    try {
      await updateMemory(memory.memory_type, memory.id, {
        content: content.trim() !== memory.content ? content.trim() : undefined,
        reasoning: memory.memory_type === 'procedural' && reasoning.trim() !== (memory.reasoning ?? '') ? reasoning.trim() : undefined,
        application: memory.memory_type === 'procedural' && application.trim() !== (memory.application ?? '') ? application.trim() : undefined,
        importance: parseFloat(importance) !== (memory.importance ?? 0.5) ? parseFloat(importance) : undefined,
        tags: tagsChanged ? tags : undefined,
      });
      toast({ title: t('editDialog.success'), description: t('editDialog.successDesc') });
      onOpenChange(false);
    } catch (error) {
      toast({
        title: t('editDialog.failed'),
        description: error instanceof Error ? error.message : t('unknownError'),
        variant: 'destructive',
      });
    } finally {
      setIsSubmitting(false);
    }
  }, [memory, canEdit, isChanged, content, reasoning, application, importance, tags, tagsChanged, updateMemory, onOpenChange, t]);

  if (!memory) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[480px] p-0 overflow-hidden">
        <div className="absolute inset-x-0 top-0 h-32 bg-gradient-to-b from-primary/5 to-transparent pointer-events-none" />
        <div className="relative p-6">
          <DialogHeader className="space-y-2">
            <div className="flex items-center gap-3">
              <MemoryTypeIcon type={memory.memory_type} size={18} showBackground />
              <div>
                <DialogTitle className="text-xl font-semibold">{t('editDialog.title')}</DialogTitle>
                <DialogDescription>{t('editDialog.description')}</DialogDescription>
              </div>
            </div>
          </DialogHeader>

          <div className="mt-6 space-y-5">
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              maxLength={2000}
              rows={4}
              disabled={!canEdit}
              className={cn(
                'w-full px-4 py-3 rounded-xl resize-none',
                'bg-accent/30 border border-border/50',
                'text-sm text-foreground placeholder:text-muted-foreground/50',
                'focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50',
                'transition-all duration-200',
                !canEdit && 'opacity-60 cursor-not-allowed',
              )}
            />

            {supportsTag && (
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">{t('tags')}</label>
                <div
                  className={cn(
                    'flex flex-wrap items-center gap-1.5 px-3 py-2 rounded-lg min-h-[38px]',
                    'bg-accent/30 border border-border/50',
                    'focus-within:ring-2 focus-within:ring-primary/20 focus-within:border-primary/50',
                    'transition-all duration-200',
                    !canEdit && 'opacity-60 cursor-not-allowed',
                  )}
                >
                  {tags.map((tag) => (
                    <span
                      key={tag}
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-primary/10 text-xs font-medium text-primary"
                    >
                      {tag}
                      {canEdit && (
                        <button type="button" onClick={() => removeTag(tag)} className="hover:text-destructive">
                          <X size={10} />
                        </button>
                      )}
                    </span>
                  ))}
                  {canEdit && (
                    <input
                      type="text"
                      value={tagInput}
                      onChange={(e) => setTagInput(e.target.value)}
                      onKeyDown={handleTagKeyDown}
                      onBlur={() => {
                        if (tagInput.trim()) { addTag(tagInput); setTagInput(''); }
                      }}
                      placeholder={tags.length === 0 ? t('createDialog.tagsPlaceholder') : ''}
                      className="flex-1 min-w-[80px] bg-transparent text-sm outline-none placeholder:text-muted-foreground/50"
                    />
                  )}
                </div>
              </div>
            )}

            {memory.memory_type === 'procedural' && (
              <div className="space-y-3">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">Why (Context/Rationale)</label>
                  <input
                    type="text"
                    value={reasoning}
                    onChange={(e) => setReasoning(e.target.value)}
                    disabled={!canEdit}
                    className={cn(
                      'w-full px-3 py-2 rounded-lg',
                      'bg-accent/30 border border-border/50',
                      'text-sm text-foreground placeholder:text-muted-foreground/50',
                      'focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50',
                      'transition-all duration-200',
                      !canEdit && 'opacity-60 cursor-not-allowed'
                    )}
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">How (Nuances/Boundaries)</label>
                  <input
                    type="text"
                    value={application}
                    onChange={(e) => setApplication(e.target.value)}
                    disabled={!canEdit}
                    className={cn(
                      'w-full px-3 py-2 rounded-lg',
                      'bg-accent/30 border border-border/50',
                      'text-sm text-foreground placeholder:text-muted-foreground/50',
                      'focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50',
                      'transition-all duration-200',
                      !canEdit && 'opacity-60 cursor-not-allowed'
                    )}
                  />
                </div>
              </div>
            )}

            {canEdit && (
              <div className="flex items-center gap-3">
                <label className="text-sm text-muted-foreground whitespace-nowrap">{t('importance')}</label>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.1"
                  value={importance}
                  onChange={(e) => setImportance(e.target.value)}
                  className="flex-1 accent-primary"
                />
                <span className="text-sm font-mono text-foreground w-8 text-right">
                  {parseFloat(importance).toFixed(1)}
                </span>
              </div>
            )}

            {!canEdit && (
              <p className="text-xs text-muted-foreground/70 italic px-1">
                {memory.memory_type === 'profile'
                  ? t('editDialog.profileNotEditable')
                  : t('editDialog.proceduralNotEditable')}
              </p>
            )}
          </div>

          <DialogFooter className="mt-6">
            <button
              onClick={handleSave}
              disabled={isSubmitting || !canEdit || !isChanged}
              className={cn(
                'flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg',
                'text-sm font-medium transition-all duration-200',
                'bg-primary text-primary-foreground',
                'hover:bg-primary/90',
                'shadow-lg shadow-primary/20',
                'disabled:opacity-50 disabled:cursor-not-allowed',
              )}
            >
              {isSubmitting ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
              {t('editDialog.save')}
            </button>
          </DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  );
});

MemoryEditDialog.displayName = 'MemoryEditDialog';

export default MemoryEditDialog;
