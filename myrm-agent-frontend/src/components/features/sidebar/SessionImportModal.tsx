'use client';

/**
 * External session transcript import modal.
 *
 * [INPUT]
 * - open: boolean modal visibility state
 * - onOpenChange: (open: boolean) => void
 * - onImportSuccess?: (chatId: string) => void
 *
 * [OUTPUT]
 * - SessionImportModal: Modern dialog for importing Claude Code, Codex, and Hermes sessions.
 *
 * [POS]
 * Client UI for cross-assistant continuous conversation resumption.
 * Zero native emoji. Lucide icons only. Dual-theme compatible.
 */

import React, { useState, useCallback, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import {
  UploadCloud,
  FileCode2,
  Sparkles,
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
  Loader2,
  ArrowRight,
  Terminal,
} from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import { cn } from '@/lib/utils/classnameUtils';
import { importTranscriptFile, importTranscriptJson, type ImportTranscriptResult } from '@/services/sessionImport';
import { toast } from 'sonner';

export interface SessionImportModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onImportSuccess?: (chatId: string) => void;
}

export const SessionImportModal: React.FC<SessionImportModalProps> = ({ open, onOpenChange, onImportSuccess }) => {
  const t = useTranslations();
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [activeTab, setActiveTab] = useState<'upload' | 'paste'>('upload');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [rawText, setRawText] = useState<string>('');
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(false);
  const [importResult, setImportResult] = useState<ImportTranscriptResult | null>(null);

  const resetState = useCallback(() => {
    setSelectedFile(null);
    setRawText('');
    setLoading(false);
    setImportResult(null);
    setIsDragging(false);
  }, []);

  const handleModalClose = useCallback(
    (nextOpen: boolean) => {
      if (!nextOpen) {
        resetState();
      }
      onOpenChange(nextOpen);
    },
    [onOpenChange, resetState],
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        const file = e.dataTransfer.files[0];
        if (file.name.endsWith('.json') || file.name.endsWith('.jsonl')) {
          setSelectedFile(file);
        } else {
          toast.error(t('chat.import.invalidFileType') || 'Please upload a .json or .jsonl transcript file');
        }
      }
    },
    [t],
  );

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setSelectedFile(e.target.files[0]);
    }
  }, []);

  const executeImport = async () => {
    setLoading(true);
    setImportResult(null);
    try {
      let result: ImportTranscriptResult;
      if (activeTab === 'upload') {
        if (!selectedFile) {
          toast.error(t('chat.import.noFileSelected') || 'Please select a file to import');
          setLoading(false);
          return;
        }
        result = await importTranscriptFile(selectedFile);
      } else {
        if (!rawText.trim()) {
          toast.error(t('chat.import.noTextProvided') || 'Please paste transcript JSON or JSONL content');
          setLoading(false);
          return;
        }
        result = await importTranscriptJson({ raw_content: rawText });
      }

      setImportResult(result);
      toast.success(
        t('chat.import.successToast', { count: result.turns_count }) ||
          `Imported ${result.turns_count} turns successfully`,
      );
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Import failed';
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  const navigateToChat = useCallback(() => {
    if (!importResult) {
      return;
    }
    const cid = importResult.chat_id;
    handleModalClose(false);
    if (onImportSuccess) {
      onImportSuccess(cid);
    }
    router.push(`/chat/${cid}`);
  }, [importResult, handleModalClose, onImportSuccess, router]);

  return (
    <Dialog open={open} onOpenChange={handleModalClose}>
      <DialogContent data-testid="session-import-modal" className="max-w-xl w-[92vw] p-0 overflow-hidden bg-background/95 backdrop-blur-md border border-border/80 shadow-2xl rounded-2xl">
        <DialogHeader className="p-6 pb-4 border-b border-border/40">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary flex-shrink-0">
              <Terminal className="w-5 h-5" />
            </div>
            <div>
              <DialogTitle className="text-lg font-semibold tracking-tight text-foreground flex items-center gap-2">
                <span>{t('chat.import.modalTitle') || 'Import External Transcript'}</span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-primary/15 text-primary font-medium">
                  {t('chat.import.cleanRecordBadge') || 'Clean Record'}
                </span>
              </DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground mt-1">
                {t('chat.import.modalSubtitle') ||
                  'Import sessions from Claude Code, Codex CLI, or Hermes Agent and resume instantly.'}
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="p-6 space-y-5">
          {/* Result Banner after import */}
          {importResult ? (
            <div data-testid="import-result-stats" className="p-5 rounded-xl bg-card border border-primary/30 space-y-4 animate-in fade-in zoom-in-95 duration-200">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-2.5 text-primary">
                  <CheckCircle2 className="w-5 h-5" />
                  <span className="font-semibold text-sm">
                    {t('chat.import.successTitle') || 'Session Ready for Resumption'}
                  </span>
                </div>
                <span className="text-xs font-mono uppercase bg-muted/70 px-2 py-0.5 rounded text-muted-foreground">
                  {importResult.source_platform}
                </span>
              </div>

              <div className="text-xs text-foreground font-medium truncate">{importResult.title}</div>

              <div className="grid grid-cols-3 gap-3 pt-2">
                <div className="p-3 rounded-lg bg-muted/40 border border-border/50 text-center">
                  <div className="text-xs text-muted-foreground">{t('chat.import.turns') || 'Turns'}</div>
                  <div className="text-sm font-semibold text-foreground mt-0.5">{importResult.turns_count}</div>
                </div>
                <div className="p-3 rounded-lg bg-muted/40 border border-border/50 text-center">
                  <div className="text-xs text-muted-foreground">{t('chat.import.tokenSaved') || 'Compression'}</div>
                  <div className="text-sm font-semibold text-primary mt-0.5">
                    {Math.round(importResult.reduction_ratio * 100)}%
                  </div>
                </div>
                <div className="p-3 rounded-lg bg-muted/40 border border-border/50 text-center">
                  <div className="text-xs text-muted-foreground">{t('chat.import.privacy') || 'Privacy'}</div>
                  <div className="text-sm font-semibold text-foreground mt-0.5 flex items-center justify-center gap-1">
                    <ShieldCheck className="w-3.5 h-3.5 text-primary" />
                    <span>{t('chat.import.redacted') || 'Clean'}</span>
                  </div>
                </div>
              </div>

              <div className="pt-2 flex justify-end gap-2">
                <Button variant="outline" size="sm" onClick={resetState}>
                  {t('chat.import.importAnother') || 'Import Another'}
                </Button>
                <Button data-testid="import-resume-btn" size="sm" onClick={navigateToChat} className="gap-2">
                  <span>{t('chat.import.resumeNow') || 'Resume Chat Now'}</span>
                  <ArrowRight className="w-4 h-4" />
                </Button>
              </div>
            </div>
          ) : (
            <>
              {/* Tab Selector */}
              <div className="flex p-1 rounded-xl bg-muted/50 border border-border/40 text-xs">
                <button
                  type="button"
                  data-testid="import-tab-upload"
                  onClick={() => setActiveTab('upload')}
                  className={cn(
                    'flex-1 py-1.5 rounded-lg font-medium transition-all duration-150 flex items-center justify-center gap-2',
                    activeTab === 'upload'
                      ? 'bg-background text-foreground shadow-sm'
                      : 'text-muted-foreground hover:text-foreground',
                  )}
                >
                  <FileCode2 className="w-3.5 h-3.5" />
                  <span>{t('chat.import.tabUpload') || 'Upload File'}</span>
                </button>
                <button
                  type="button"
                  data-testid="import-tab-paste"
                  onClick={() => setActiveTab('paste')}
                  className={cn(
                    'flex-1 py-1.5 rounded-lg font-medium transition-all duration-150 flex items-center justify-center gap-2',
                    activeTab === 'paste'
                      ? 'bg-background text-foreground shadow-sm'
                      : 'text-muted-foreground hover:text-foreground',
                  )}
                >
                  <Terminal className="w-3.5 h-3.5" />
                  <span>{t('chat.import.tabPaste') || 'Paste JSON / JSONL'}</span>
                </button>
              </div>

              {/* Upload mode */}
              {activeTab === 'upload' ? (
                <>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".json,.jsonl"
                    className="hidden"
                    onChange={handleFileChange}
                  />
                  <button
                    type="button"
                    onDragOver={handleDragOver}
                    onDragLeave={handleDragLeave}
                    onDrop={handleDrop}
                    onClick={() => fileInputRef.current?.click()}
                    className={cn(
                      'w-full border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all duration-200 block',
                      isDragging
                        ? 'border-primary bg-primary/5 scale-[0.99]'
                        : selectedFile
                          ? 'border-primary/50 bg-primary/5'
                          : 'border-border/60 hover:border-border hover:bg-muted/30',
                    )}
                  >
                    <div className="flex flex-col items-center gap-2">
                      <div className="w-12 h-12 rounded-full bg-muted/60 border border-border/50 flex items-center justify-center text-muted-foreground">
                        <UploadCloud className="w-6 h-6" />
                      </div>
                      {selectedFile ? (
                        <div className="space-y-1">
                          <div className="text-sm font-semibold text-foreground">{selectedFile.name}</div>
                          <div className="text-xs text-muted-foreground">
                            {(selectedFile.size / 1024).toFixed(1)} KB ·{' '}
                            {t('chat.import.clickToChange') || 'Click to change'}
                          </div>
                        </div>
                      ) : (
                        <div className="space-y-1">
                          <div className="text-sm font-medium text-foreground">
                            {t('chat.import.dropHint') || 'Drop transcript .json or .jsonl file here'}
                          </div>
                          <div className="text-xs text-muted-foreground">
                            {t('chat.import.formatHint') || 'Supports Claude Code, Codex CLI, and Hermes Agent'}
                          </div>
                        </div>
                      )}
                    </div>
                  </button>
                </>
              ) : (
                /* Paste mode */
                <div className="space-y-1.5">
                  <textarea
                    data-testid="import-paste-textarea"
                    value={rawText}
                    onChange={(e) => setRawText(e.target.value)}
                    placeholder={
                      t('chat.import.pastePlaceholder') ||
                      'Paste raw JSON / JSONL transcript events here (e.g. from ~/.claude/projects/ or ~/.hermes/sessions/)...'
                    }
                    rows={8}
                    className="w-full text-xs font-mono p-3 rounded-xl bg-card border border-border/60 focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary text-foreground resize-none"
                  />
                </div>
              )}

              {/* Feature highlight bullet */}
              <div className="flex items-center gap-2 text-xs text-muted-foreground px-1">
                <Sparkles className="w-3.5 h-3.5 text-primary flex-shrink-0" />
                <span>
                  {t('chat.import.featuresSummary') ||
                    'Auto-scrubs credentials, folds verbose tool stdout, and preserves 100% prompt cache prefix.'}
                </span>
              </div>

              {/* Action buttons */}
              <div className="flex justify-end gap-2.5 pt-2">
                <Button variant="outline" size="sm" onClick={() => handleModalClose(false)} disabled={loading}>
                  {t('common.cancel') || 'Cancel'}
                </Button>
                <Button
                  data-testid="import-submit-btn"
                  size="sm"
                  onClick={executeImport}
                  disabled={
                    loading || (activeTab === 'upload' && !selectedFile) || (activeTab === 'paste' && !rawText.trim())
                  }
                  className="gap-2"
                >
                  {loading ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>{t('chat.import.processing') || 'Processing...'}</span>
                    </>
                  ) : (
                    <>
                      <CheckCircle2 className="w-4 h-4" />
                      <span>{t('chat.import.startImport') || 'Import & Resume'}</span>
                    </>
                  )}
                </Button>
              </div>
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default SessionImportModal;
