'use client';

import { useCallback, useRef, useState } from 'react';
import { CheckCircle2, ClipboardPaste, Copy, Folder, Loader2, Search, ShieldAlert, Upload } from 'lucide-react';

import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import { getMigrationSourceDisplayName, type ExternalSource } from '@/services/migrationDiscovery';
import { cn } from '@/lib/utils/classnameUtils';

import type { TranslationFn } from './wizardShared';

export function CloudUploadZone({
  uploading,
  onUpload,
  t,
}: {
  uploading: boolean;
  onUpload: (file: File) => void;
  t: TranslationFn;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  const handleFile = useCallback(
    (file: File) => {
      if (file.name.toLowerCase().endsWith('.zip')) {
        onUpload(file);
      }
    },
    [onUpload],
  );

  return (
    <div
      className={cn(
        'rounded-xl border-2 border-dashed p-8 text-center transition-colors',
        dragOver ? 'border-primary bg-primary/5' : 'border-border/50 bg-secondary/20',
      )}
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        const file = e.dataTransfer.files[0];
        if (file) {
          handleFile(file);
        }
      }}
    >
      <Upload className="mx-auto mb-3 h-8 w-8 text-muted-foreground/40" />
      <p className="text-sm font-medium text-muted-foreground">{t('cloudUploadTitle')}</p>
      <p className="mt-1 text-xs text-muted-foreground/60">{t('cloudUploadGuide')}</p>
      <input
        ref={inputRef}
        type="file"
        accept=".zip"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) {
            handleFile(file);
          }
        }}
      />
      <Button
        size="sm"
        variant="outline"
        className="mt-4"
        disabled={uploading}
        onClick={() => inputRef.current?.click()}
      >
        {uploading ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : <Upload className="mr-2 h-3.5 w-3.5" />}
        {uploading ? t('cloudUploading') : t('cloudUploadButton')}
      </Button>
    </div>
  );
}

export function PasteImportLane({
  text,
  pasting,
  modelExtraction,
  onTextChange,
  onModelExtractionChange,
  onPreview,
  t,
}: {
  text: string;
  pasting: boolean;
  modelExtraction: boolean;
  onTextChange: (value: string) => void;
  onModelExtractionChange: (value: boolean) => void;
  onPreview: () => void;
  t: TranslationFn;
}) {
  const [copied, setCopied] = useState(false);
  const promptText = t('paste.promptText');

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(promptText);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }, [promptText]);

  return (
    <div className="space-y-3 rounded-xl border border-border/50 bg-secondary/20 p-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-start gap-3">
          <div className="rounded-lg bg-accent/10 p-2.5">
            <ClipboardPaste className="h-5 w-5 text-accent-foreground" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground">{t('paste.title')}</h3>
            <p className="mt-0.5 text-xs text-muted-foreground">{t('paste.description')}</p>
          </div>
        </div>
        <Button size="sm" variant="outline" className="h-8 shrink-0 gap-1.5 text-xs" onClick={handleCopy}>
          {copied ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
          {copied ? t('paste.copied') : t('paste.copyPrompt')}
        </Button>
      </div>
      <details className="group rounded-lg border border-border/40 bg-background/60">
        <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-muted-foreground">
          {t('paste.promptLabel')}
        </summary>
        <pre className="max-h-48 overflow-auto whitespace-pre-wrap px-3 pb-3 text-[11px] leading-relaxed text-muted-foreground">
          {promptText}
        </pre>
      </details>
      <textarea
        data-testid="migration-paste-textarea"
        value={text}
        onChange={(event) => onTextChange(event.target.value)}
        placeholder={t('paste.placeholder')}
        rows={6}
        spellCheck={false}
        className="w-full resize-y rounded-lg border border-border bg-background px-3 py-2 text-xs leading-relaxed text-foreground placeholder:text-muted-foreground/50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
      />
      <p className="text-[11px] text-muted-foreground/70">{t('paste.sizeHint')}</p>
      <label className="flex items-start gap-2 rounded-lg border border-border/40 bg-background/60 px-3 py-2">
        <input
          type="checkbox"
          data-testid="migration-paste-model-toggle"
          checked={modelExtraction}
          onChange={(event) => onModelExtractionChange(event.target.checked)}
          className="mt-0.5 rounded border-border"
        />
        <span className="min-w-0">
          <span className="block text-xs font-medium text-foreground">{t('paste.modelLabel')}</span>
          <span className="mt-0.5 block text-[11px] leading-relaxed text-muted-foreground">
            {t('paste.modelDescription')}
          </span>
        </span>
      </label>
      <Button
        size="sm"
        className="h-8 gap-1.5 text-xs"
        disabled={pasting || text.trim().length === 0}
        onClick={onPreview}
      >
        {pasting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ClipboardPaste className="h-3.5 w-3.5" />}
        {pasting ? t('paste.previewing') : t('paste.previewButton')}
      </Button>
    </div>
  );
}

export function SourceCard({
  source,
  previewing,
  disabled,
  onPreview,
  t,
}: {
  source: ExternalSource;
  previewing: boolean;
  disabled: boolean;
  onPreview: () => void;
  t: TranslationFn;
}) {
  const confidenceVariant =
    source.confidence === 'high' ? 'default' : source.confidence === 'medium' ? 'secondary' : 'outline';
  const confidenceLabel =
    source.confidence === 'high'
      ? t('sourceCard.confidenceHigh')
      : source.confidence === 'medium'
        ? t('sourceCard.confidenceMedium')
        : t('sourceCard.confidenceLow');

  return (
    <div className="rounded-xl border border-border/50 bg-card p-5 space-y-3 hover:border-border transition-colors">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2.5">
          <div className="rounded-lg bg-primary/10 p-2">
            <Folder className="h-4 w-4 text-primary" />
          </div>
          <div>
            <span className="text-sm font-semibold">{getMigrationSourceDisplayName(source.competitor)}</span>
            <Badge variant={confidenceVariant} className="ml-2 text-[10px]">
              {confidenceLabel}
            </Badge>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
        {source.memory_count_estimate > 0 && (
          <span className="rounded-md bg-secondary/60 px-2 py-0.5">
            {t('sourceCard.memories', { count: source.memory_count_estimate })}
          </span>
        )}
        {source.skill_count > 0 && (
          <span className="rounded-md bg-secondary/60 px-2 py-0.5">
            {t('sourceCard.skills', { count: source.skill_count })}
          </span>
        )}
        <span className="rounded-md bg-secondary/60 px-2 py-0.5">
          {t('sourceCard.files', { count: source.files.length })}
        </span>
      </div>

      {source.has_api_keys && (
        <div className="flex items-center gap-1.5 text-xs text-amber-600 dark:text-amber-400">
          <ShieldAlert className="h-3.5 w-3.5" />
          {t('sourceCard.apiKeysDetected')}
        </div>
      )}

      <div className="text-[11px] text-muted-foreground/50 truncate" title={source.root}>
        {t('sourceCard.rootPath')}: {source.root}
      </div>

      <Button size="sm" className="w-full h-8 text-xs" onClick={onPreview} disabled={disabled}>
        {previewing ? (
          <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
        ) : (
          <Search className="mr-1.5 h-3.5 w-3.5" />
        )}
        {previewing ? t('sourceCard.previewing') : t('sourceCard.previewButton')}
      </Button>
    </div>
  );
}
