'use client';

/**
 * [INPUT]
 * @/services/memory/domainMesh::migrateFromHermes
 * @/components/primitives/dialog::Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription
 * @/hooks/shared/useToast::toast
 * next-intl::useTranslations (memory.mesh.migration)
 * lucide-react::UploadCloud, FileText, Loader2
 *
 * [OUTPUT]
 * HermesMigrationModal: Modal allowing users to migrate memory exports from Hermes or OpenViking formats.
 *
 * [POS]
 * Modal layer for zero-friction external memory import.
 */

import React, { useState, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { UploadCloud, FileText, Loader2 } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/primitives/dialog';
import { toast } from '@/hooks/shared/useToast';
import { migrateFromHermes } from '@/services/memory/domainMesh';

interface HermesMigrationModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess: () => void;
}

export const HermesMigrationModal: React.FC<HermesMigrationModalProps> = ({ open, onOpenChange, onSuccess }) => {
  const t = useTranslations('memory.mesh.migration');
  const [content, setContent] = useState('');
  const [format, setFormat] = useState<'markdown' | 'json'>('markdown');
  const [loading, setLoading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) {
      return;
    }

    const isJsonFile = file.name.endsWith('.json');
    setFormat(isJsonFile ? 'json' : 'markdown');

    const reader = new FileReader();
    reader.onload = (event) => {
      const text = event.target?.result as string;
      if (text) {
        setContent(text);
      }
    };
    reader.readAsText(file);
  };

  // The submit button stays disabled while the content is blank, so no empty payload reaches this handler.
  const handleSubmit = async () => {
    setLoading(true);
    try {
      const result = await migrateFromHermes({ content, format });
      if (result.success_count === 0) {
        // The API answers 200 even when nothing could be parsed; keep the dialog and the pasted text so the user can fix it.
        toast({ title: t('failedTitle'), description: t('nothingImported'), variant: 'destructive' });
        return;
      }
      toast({
        title: t('doneTitle'),
        description: t('doneDescription', { success: result.success_count, failed: result.fail_count }),
      });
      onSuccess();
      onOpenChange(false);
      setContent('');
    } catch {
      toast({
        title: t('failedTitle'),
        description: t('failedDescription'),
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl sm:max-w-xl max-h-[90vh] flex flex-col">
        <DialogHeader>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-primary">
            <UploadCloud className="h-4 w-4" />
            {t('eyebrow')}
          </div>
          <DialogTitle className="text-base font-semibold leading-snug">{t('title')}</DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground">{t('description')}</DialogDescription>
        </DialogHeader>

        <div className="flex flex-1 flex-col gap-3 overflow-y-auto pt-2 text-xs">
          {/* Format Selector */}
          <div className="flex items-center justify-between">
            <div className="inline-flex rounded-lg border border-border/60 bg-muted/40 p-0.5">
              <button
                type="button"
                onClick={() => setFormat('markdown')}
                className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                  format === 'markdown'
                    ? 'bg-background text-foreground shadow-xs'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                Markdown
              </button>
              <button
                type="button"
                onClick={() => setFormat('json')}
                className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                  format === 'json'
                    ? 'bg-background text-foreground shadow-xs'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                JSON
              </button>
            </div>

            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="inline-flex items-center gap-1.5 rounded-lg border border-border/80 bg-background px-2.5 py-1 text-xs font-medium text-foreground hover:bg-accent transition-colors"
            >
              <FileText className="h-3.5 w-3.5" />
              <span>{t('chooseFile')}</span>
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept=".md,.markdown,.json,.txt"
              onChange={handleFileUpload}
              className="hidden"
            />
          </div>

          {/* Textarea */}
          <div className="relative flex-1">
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder={
                format === 'markdown'
                  ? '---\nid: mem-1\ntype: semantic\ndomain: user\ncategory: preferences\n---\n# User Preference\n...'
                  : '[\n  {\n    "id": "mem-1",\n    "type": "semantic",\n    "domain": "user",\n    "category": "preferences",\n    "content": "..."\n  }\n]'
              }
              rows={10}
              className="w-full rounded-lg border border-border/80 bg-background/80 p-3 font-mono text-xs leading-relaxed text-foreground placeholder:text-muted-foreground/60 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center justify-end gap-2 pt-3 border-t border-border/40">
          <button
            type="button"
            disabled={loading}
            onClick={() => onOpenChange(false)}
            className="rounded-lg border border-border/80 px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
          >
            {t('cancel')}
          </button>
          <button
            type="button"
            disabled={loading || !content.trim()}
            onClick={handleSubmit}
            className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3.5 py-1.5 text-xs font-semibold text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
          >
            {loading ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                <span>{t('importing')}</span>
              </>
            ) : (
              <>
                <UploadCloud className="h-3.5 w-3.5" />
                <span>{t('start')}</span>
              </>
            )}
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
};
