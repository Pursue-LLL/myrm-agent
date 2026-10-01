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
  type ExportFormatOptions,
} from '@/lib/utils/chatExport';

export type ExportFormatType = 'html' | 'markdown' | 'json' | 'zip';

export interface SessionExportModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  chatId: string;
  chatTitle?: string | null;
}

export function SessionExportModal({ open, onOpenChange, chatId, chatTitle }: SessionExportModalProps) {
  const t = useTranslations('chat');
  const { resolvedTheme } = useTheme();
  const [selectedFormat, setSelectedFormat] = useState<ExportFormatType>('html');
  const [redactSecrets, setRedactSecrets] = useState(true);
  const [includeReasoning, setIncludeReasoning] = useState(true);
  const [includeToolCalls, setIncludeToolCalls] = useState(true);
  const [isExporting, setIsExporting] = useState(false);
  const [isCopied, setIsCopied] = useState(false);
  const [, startTransition] = useTransition();

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
          title: t('exportChat.success', { defaultMessage: '导出会话成功' }),
          variant: 'default',
        });
        onOpenChange(false);
        return;
      }

      const exportData = await exportChat(chatId, { redactSecrets });
      if (!exportData || exportData.messages.length === 0) {
        toast({
          title: t('exportChat.noMessages', { defaultMessage: '没有可导出的消息' }),
          variant: 'default',
        });
        return;
      }

      const formatOptions: ExportFormatOptions = {
        includeReasoning,
        includeToolCalls,
      };

      const isDark = resolvedTheme === 'dark';
      const lang = typeof navigator !== 'undefined' && navigator.language.startsWith('zh') ? 'zh' : 'en';

      switch (selectedFormat) {
        case 'html':
          await downloadAsHtml(exportData, isDark ? 'dark' : 'light', lang, formatOptions);
          break;
        case 'markdown':
          downloadAsMarkdown(exportData, formatOptions);
          break;
        case 'json':
          downloadAsJson(exportData, formatOptions);
          break;
      }

      toast({
        title: redactSecrets
          ? t('exportChat.successRedacted', { defaultMessage: '已安全脱敏导出' })
          : t('exportChat.success', { defaultMessage: '导出会话成功' }),
        variant: 'default',
      });
      onOpenChange(false);
    } catch (err) {
      console.error('[SessionExportModal] Export failed:', err);
      toast({
        title: t('exportChat.error', { defaultMessage: '导出失败' }),
        description: err instanceof Error ? err.message : 'Unknown error',
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
          title: t('exportChat.noMessages', { defaultMessage: '没有可导出的消息' }),
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
        title: redactSecrets
          ? t('exportChat.copySuccessRedacted', { defaultMessage: '已复制脱敏 Markdown' })
          : t('exportChat.copySuccess', { defaultMessage: '已复制 Markdown 到剪贴板' }),
        variant: 'default',
      });
    } catch (err) {
      console.error('[SessionExportModal] Copy markdown failed:', err);
      toast({
        title: t('exportChat.error', { defaultMessage: '复制失败' }),
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      });
    } finally {
      setIsExporting(false);
    }
  }, [chatId, isExporting, redactSecrets, includeReasoning, includeToolCalls, t]);

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
      description: t('exportChat.htmlDesc', { defaultMessage: '自包含单文件，内置暗色模式、公式与高亮' }),
      icon: FileCode2,
      badge: t('exportChat.recommended', { defaultMessage: '推荐' }),
    },
    {
      id: 'markdown',
      title: 'Markdown',
      description: t('exportChat.markdownDesc', { defaultMessage: '标准文档，易于知识库与文档管理系统沉淀' }),
      icon: FileText,
    },
    {
      id: 'json',
      title: 'JSON',
      description: t('exportChat.jsonDesc', { defaultMessage: '机器可读完整数据包，便于二次解析与加工' }),
      icon: FileJson,
    },
    {
      id: 'zip',
      title: 'ZIP Pack',
      description: t('exportChat.zipDesc', { defaultMessage: '包含会话原始事件日志、子代理轨迹与所有工件' }),
      icon: Archive,
    },
  ];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base font-semibold">
            <Download className="h-4 w-4 text-primary" />
            <span>{t('exportChat.modalTitle', { defaultMessage: '导出会话与知识分享' })}</span>
          </DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground truncate">
            {chatTitle || chatId}
          </DialogDescription>
        </DialogHeader>

        {/* 格式选择 */}
        <div className="space-y-2 py-1">
          <Label className="text-xs font-medium text-muted-foreground">
            {t('exportChat.selectFormat', { defaultMessage: '选择导出格式' })}
          </Label>
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
          <Label className="text-xs font-medium text-muted-foreground">
            {t('exportChat.options', { defaultMessage: '导出选项' })}
          </Label>

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
                  <span>{t('exportChat.redactSecretsLabel', { defaultMessage: '自动脱敏敏感凭据' })}</span>
                </label>
                <p className="text-[11px] text-muted-foreground">
                  {t('exportChat.redactSecretsHint', {
                    defaultMessage: '自动屏蔽 API Key、Token、私钥与密码等安全机密',
                  })}
                </p>
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
                      <span>
                        {t('exportChat.includeReasoningLabel', { defaultMessage: '包含模型思考过程 (Thinking)' })}
                      </span>
                    </label>
                    <p className="text-[11px] text-muted-foreground">
                      {t('exportChat.includeReasoningHint', {
                        defaultMessage: '保留大模型的深度推理链折叠卡片',
                      })}
                    </p>
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
                      <span>{t('exportChat.includeToolCallsLabel', { defaultMessage: '包含工具调用与耗时分析' })}</span>
                    </label>
                    <p className="text-[11px] text-muted-foreground">
                      {t('exportChat.includeToolCallsHint', {
                        defaultMessage: '记录工具调用入参摘要、执行耗时与成功状态',
                      })}
                    </p>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>

        <DialogFooter className="gap-2 sm:gap-0 pt-2 border-t border-border/50">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleCopyMarkdown}
            disabled={isExporting}
            className="gap-1.5 text-xs"
          >
            {isCopied ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
            <span>
              {isCopied
                ? t('exportChat.copied', { defaultMessage: '已复制' })
                : t('exportChat.copyMarkdown', { defaultMessage: '复制 Markdown' })}
            </span>
          </Button>
          <Button type="button" size="sm" onClick={handleExport} disabled={isExporting} className="gap-1.5 text-xs">
            {isExporting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
            <span>{t('exportChat.downloadAction', { defaultMessage: '下载所选格式' })}</span>
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
