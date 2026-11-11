'use client';

import { useState, useCallback, useTransition } from 'react';
import { useTranslations } from 'next-intl';
import { useTheme } from 'next-themes';
import {
  FileCode2,
  FileText,
  FileJson,
  Archive,
  ShieldCheck,
  Brain,
  Wrench,
  Download,
  Copy,
  Check,
  Loader2,
} from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import { Checkbox } from '@/components/primitives/checkbox';
import { Label } from '@/components/primitives/label';
import { toast } from '@/hooks/shared/useToast';
import { exportChat } from '@/services/chat';
import { exportSessionZipPack } from '@/services/chatExportPack';
import {
  downloadAsHtml,
  downloadAsMarkdown,
  downloadAsJson,
  copyAsMarkdown,
  getExportLang,
  type ExportFormatOptions,
} from '@/lib/utils/chat-export';

export type ExportFormatType = 'html' | 'markdown' | 'json' | 'zip';

export interface SessionExportModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  chatId: string;
  chatTitle?: string | null;
  initialFormat?: ExportFormatType;
}

export function SessionExportModal({ open, onOpenChange, chatId, chatTitle, initialFormat }: SessionExportModalProps) {
  const t = useTranslations('chat');
  const tCommon = useTranslations('common');
  const { resolvedTheme } = useTheme();
  const [selectedFormat, setSelectedFormat] = useState<ExportFormatType>(initialFormat ?? 'html');
  const [redactSecrets, setRedactSecrets] = useState(true);
  const [includeReasoning, setIncludeReasoning] = useState(true);
  const [includeToolCalls, setIncludeToolCalls] = useState(true);
  const [isExporting, setIsExporting] = useState(false);
  const [isCopied, setIsCopied] = useState(false);
  const [, startTransition] = useTransition();

  // The format the caller asks for applies when the dialog opens or the ask changes, and only then, so the user's own
  // pick stands while the dialog stays open. Adjusting during render puts it on the first frame of the open dialog.
  const requestedFormat = open ? initialFormat : undefined;
  const [prevRequestedFormat, setPrevRequestedFormat] = useState(requestedFormat);
  if (requestedFormat !== prevRequestedFormat) {
    setPrevRequestedFormat(requestedFormat);
    if (requestedFormat) {
      setSelectedFormat(requestedFormat);
    }
  }

  const handleExport = useCallback(async () => {
    if (!chatId || isExporting) {
      return;
    }
    setIsExporting(true);

    try {
      if (selectedFormat === 'zip') {
        await exportSessionZipPack(chatId, {
          redactSecrets,
          includeArtifacts: true,
          includeSubagents: true,
        });
        toast({
          title: t('exportChat.success'),
          variant: 'default',
        });
        onOpenChange(false);
        return;
      }

      const exportData = await exportChat(chatId, { redactSecrets });
      if (!exportData || exportData.messages.length === 0) {
        toast({
          title: t('exportChat.noMessages'),
          variant: 'default',
        });
        return;
      }

      const formatOptions: ExportFormatOptions = {
        includeReasoning,
        includeToolCalls,
      };

      const isDark = resolvedTheme === 'dark';

      switch (selectedFormat) {
        case 'html':
          await downloadAsHtml(exportData, isDark ? 'dark' : 'light', getExportLang(), formatOptions);
          break;
        case 'markdown':
          downloadAsMarkdown(exportData, formatOptions);
          break;
        case 'json':
          downloadAsJson(exportData, formatOptions);
          break;
      }

      toast({
        title: redactSecrets ? t('exportChat.successRedacted') : t('exportChat.success'),
        variant: 'default',
      });
      onOpenChange(false);
    } catch (err) {
      console.error('[SessionExportModal] Export failed:', err);
      toast({
        title: t('exportChat.error'),
        description: err instanceof Error ? err.message : tCommon('unknownError'),
        variant: 'destructive',
      });
    } finally {
      setIsExporting(false);
    }
  }, [
    chatId,
    isExporting,
    selectedFormat,
    redactSecrets,
    includeReasoning,
    includeToolCalls,
    resolvedTheme,
    t,
    tCommon,
    onOpenChange,
  ]);

  const handleCopyMarkdown = useCallback(async () => {
    if (!chatId || isExporting) {
      return;
    }
    setIsExporting(true);

    try {
      const exportData = await exportChat(chatId, { redactSecrets });
      if (!exportData || exportData.messages.length === 0) {
        toast({
          title: t('exportChat.noMessages'),
          variant: 'default',
        });
        return;
      }

      await copyAsMarkdown(exportData, {
        includeReasoning,
        includeToolCalls,
      });

      startTransition(() => {
        setIsCopied(true);
      });
      setTimeout(() => {
        setIsCopied(false);
      }, 2000);

      toast({
        title: redactSecrets ? t('exportChat.copySuccessRedacted') : t('exportChat.copySuccess'),
        variant: 'default',
      });
    } catch (err) {
      console.error('[SessionExportModal] Copy markdown failed:', err);
      toast({
        title: t('exportChat.error'),
        description: err instanceof Error ? err.message : tCommon('unknownError'),
        variant: 'destructive',
      });
    } finally {
      setIsExporting(false);
    }
  }, [chatId, isExporting, redactSecrets, includeReasoning, includeToolCalls, t, tCommon]);

  const formats: Array<{
    id: ExportFormatType;
    title: string;
    description: string;
    icon: typeof FileCode2;
    badge?: string;
  }> = [
    {
      id: 'html',
      title: 'HTML',
      description: t('exportChat.htmlDesc'),
      icon: FileCode2,
      badge: t('exportChat.recommended'),
    },
    {
      id: 'markdown',
      title: 'Markdown',
      description: t('exportChat.markdownDesc'),
      icon: FileText,
    },
    {
      id: 'json',
      title: 'JSON',
      description: t('exportChat.jsonDesc'),
      icon: FileJson,
    },
    {
      id: 'zip',
      title: 'ZIP Pack',
      description: t('exportChat.zipDesc'),
      icon: Archive,
    },
  ];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base font-semibold">
            <Download className="h-4 w-4 text-primary" />
            <span>{t('exportChat.modalTitle')}</span>
          </DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground truncate">
            {chatTitle || chatId}
          </DialogDescription>
        </DialogHeader>

        {/* 格式选择 */}
        <div className="space-y-2 py-1">
          <Label className="text-xs font-medium text-muted-foreground">{t('exportChat.selectFormat')}</Label>
          <div className="grid grid-cols-2 gap-2">
            {formats.map((fmt) => {
              const Icon = fmt.icon;
              const isSelected = selectedFormat === fmt.id;
              return (
                <button
                  key={fmt.id}
                  type="button"
                  onClick={() => setSelectedFormat(fmt.id)}
                  className={`flex flex-col text-left p-3 rounded-lg border transition-all ${
                    isSelected
                      ? 'border-primary bg-primary/5 text-foreground shadow-xs'
                      : 'border-border/60 hover:border-border hover:bg-muted/40 text-muted-foreground'
                  }`}
                >
                  <div className="flex items-center justify-between w-full mb-1">
                    <div className="flex items-center gap-1.5 font-medium text-xs text-foreground">
                      <Icon className={`h-4 w-4 ${isSelected ? 'text-primary' : 'text-muted-foreground'}`} />
                      <span>{fmt.title}</span>
                    </div>
                    {fmt.badge ? (
                      <span className="text-[10px] uppercase font-semibold px-1.5 py-0.2 rounded-full bg-primary/10 text-primary">
                        {fmt.badge}
                      </span>
                    ) : null}
                  </div>
                  <span className="text-[11px] leading-tight text-muted-foreground line-clamp-2">
                    {fmt.description}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* 选项配置 */}
        <div className="space-y-3 pt-2 pb-1 border-t border-border/50">
          <Label className="text-xs font-medium text-muted-foreground">{t('exportChat.options')}</Label>

          <div className="space-y-2">
            <div className="flex items-start gap-2.5">
              <Checkbox
                id="redact-secrets"
                checked={redactSecrets}
                onCheckedChange={(checked) => setRedactSecrets(Boolean(checked))}
                className="mt-0.5"
              />
              <div className="grid gap-0.5 leading-none">
                <label
                  htmlFor="redact-secrets"
                  className="text-xs font-medium cursor-pointer flex items-center gap-1 text-foreground"
                >
                  <ShieldCheck className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
                  <span>{t('exportChat.redactSecretsLabel')}</span>
                </label>
                <p className="text-[11px] text-muted-foreground">{t('exportChat.redactSecretsHint')}</p>
              </div>
            </div>

            {selectedFormat !== 'zip' && (
              <>
                <div className="flex items-start gap-2.5">
                  <Checkbox
                    id="include-reasoning"
                    checked={includeReasoning}
                    onCheckedChange={(checked) => setIncludeReasoning(Boolean(checked))}
                    className="mt-0.5"
                  />
                  <div className="grid gap-0.5 leading-none">
                    <label
                      htmlFor="include-reasoning"
                      className="text-xs font-medium cursor-pointer flex items-center gap-1 text-foreground"
                    >
                      <Brain className="h-3.5 w-3.5 text-indigo-500" />
                      <span>{t('exportChat.includeReasoningLabel')}</span>
                    </label>
                    <p className="text-[11px] text-muted-foreground">{t('exportChat.includeReasoningHint')}</p>
                  </div>
                </div>

                <div className="flex items-start gap-2.5">
                  <Checkbox
                    id="include-tool-calls"
                    checked={includeToolCalls}
                    onCheckedChange={(checked) => setIncludeToolCalls(Boolean(checked))}
                    className="mt-0.5"
                  />
                  <div className="grid gap-0.5 leading-none">
                    <label
                      htmlFor="include-tool-calls"
                      className="text-xs font-medium cursor-pointer flex items-center gap-1 text-foreground"
                    >
                      <Wrench className="h-3.5 w-3.5 text-amber-500" />
                      <span>{t('exportChat.includeToolCallsLabel')}</span>
                    </label>
                    <p className="text-[11px] text-muted-foreground">{t('exportChat.includeToolCallsHint')}</p>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>

        <DialogFooter className="flex flex-col-reverse sm:flex-row sm:justify-end gap-2 pt-2 border-t border-border/50">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleCopyMarkdown}
            disabled={isExporting}
            className="gap-1.5 text-xs"
          >
            {isCopied ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
            <span>{isCopied ? t('exportChat.copied') : t('exportChat.copyMarkdown')}</span>
          </Button>
          <Button type="button" size="sm" onClick={handleExport} disabled={isExporting} className="gap-1.5 text-xs">
            {isExporting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
            <span>{t('exportChat.downloadAction')}</span>
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
