/**
 * [INPUT]
 * - `useCrashLoopGuard` hook (POS: crashLoopActive 状态)
 * - `@/lib/tauri` (`invokeTauriCommand`, `tauriBackend`)
 * - `tauri-plugin-dialog` (POS: 目录选择器)
 *
 * [OUTPUT]
 * - `CrashRecoveryDialog`: watchdog 放弃重启后的全屏容灾 UI
 *
 * [POS]
 * 将毁灭性后端崩溃转化为可控的容灾体验。提供无后端数据导出、
 * 日志查看、手动重启三大操作。仅在 Tauri 桌面模式下激活。
 */
'use client';

import { useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { AlertCircle, Download, FolderOpen, RefreshCw } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { invokeTauriCommand, tauriBackend } from '@/lib/tauri';

interface CrashRecoveryDialogProps {
  visible: boolean;
  onDismiss: () => void;
}

type BusyAction = 'export' | 'logs' | 'restart' | null;

export default function CrashRecoveryDialog({ visible, onDismiss }: CrashRecoveryDialogProps) {
  const t = useTranslations('common.crashRecovery');
  const [busy, setBusy] = useState<BusyAction>(null);
  const [result, setResult] = useState<string | null>(null);

  const handleExport = useCallback(async () => {
    setBusy('export');
    setResult(null);
    try {
      const { open } = await import('@tauri-apps/plugin-dialog');
      const selected = await open({ directory: true, title: t('selectExportFolder') });
      if (!selected) {
        setBusy(null);
        return;
      }
      const msg = await invokeTauriCommand<string>('export_local_sqlite', {
        targetDir: selected,
      });
      setResult(msg);
    } catch (e) {
      setResult(String(e));
    } finally {
      setBusy(null);
    }
  }, [t]);

  const handleRevealLogs = useCallback(async () => {
    setBusy('logs');
    try {
      await invokeTauriCommand('reveal_app_folder', { folderType: 'logs' });
    } catch {
      // best effort
    } finally {
      setBusy(null);
    }
  }, []);

  const handleRestart = useCallback(async () => {
    setBusy('restart');
    setResult(null);
    try {
      await tauriBackend.start();
      onDismiss();
    } catch (e) {
      setResult(String(e));
    } finally {
      setBusy(null);
    }
  }, [onDismiss]);

  if (!visible) return null;

  return (
    <div className="fixed inset-0 z-[1500] flex items-center justify-center bg-background/95 p-6 backdrop-blur-sm">
      <div className="w-full max-w-lg overflow-hidden rounded-xl border border-destructive/30 bg-card shadow-2xl">
        <div className="flex items-start gap-3 border-b border-border/50 px-5 py-4">
          <AlertCircle className="mt-0.5 h-5 w-5 flex-shrink-0 text-destructive" />
          <div>
            <h2 className="text-[15px] font-semibold tracking-tight">{t('title')}</h2>
            <p className="mt-1 text-[13px] leading-5 text-muted-foreground">
              {t('description')}
            </p>
          </div>
        </div>

        <div className="space-y-3 p-5">
          <div className="flex flex-wrap gap-2">
            <Button
              onClick={handleExport}
              disabled={busy !== null}
              variant="default"
              size="sm"
            >
              {busy === 'export' ? (
                <RefreshCw className="h-4 w-4 animate-spin" />
              ) : (
                <Download className="h-4 w-4" />
              )}
              {t('exportDatabase')}
            </Button>

            <Button
              onClick={handleRevealLogs}
              disabled={busy !== null}
              variant="secondary"
              size="sm"
            >
              <FolderOpen className="h-4 w-4" />
              {t('viewLogs')}
            </Button>

            <Button
              onClick={handleRestart}
              disabled={busy !== null}
              variant="outline"
              size="sm"
            >
              {busy === 'restart' ? (
                <RefreshCw className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
              {t('retryStart')}
            </Button>
          </div>

          {result ? (
            <p className="rounded-md bg-muted/50 px-3 py-2 text-xs text-muted-foreground">
              {result}
            </p>
          ) : null}

          <p className="text-xs text-muted-foreground/70">{t('hint')}</p>
        </div>
      </div>
    </div>
  );
}
