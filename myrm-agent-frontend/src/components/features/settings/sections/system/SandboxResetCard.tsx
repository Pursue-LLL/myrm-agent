'use client';

/**
 * [INPUT]
 * - @/lib/api::apiRequest, ApiError (POS: 前端 API 接入层，统一封装请求基址、超时与错误归一化；409 表示沙箱拒绝，仍有任务在运行)
 * - @/lib/utils/toast::toast (POS: Toast 包装器，统一 shadcn/ui 与 Sonner 的调用方式)
 * - @/components/features/app-shell/confirm-dialog::ConfirmDialog (POS: 带触发器与加载态的确认对话框)
 * - next-intl::useTranslations('settings.system.sandboxReset')
 *
 * [OUTPUT]
 * - SandboxResetCard: 云托管沙箱的「重置环境」设置卡
 *
 * [POS]
 * 设置 → 系统页的云托管沙箱重置入口（非本地模式由 SystemSection 挂载）。确认后经 server 请求控制平面换容器，并让智能体装过的 Python 包随重启清空。
 */

import { memo, useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { RefreshCw, HardDrive, AlertTriangle } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from '@/lib/utils/toast';
import { ApiError, apiRequest } from '@/lib/api';
import { ConfirmDialog } from '@/components/features/app-shell/confirm-dialog';

const HTTP_CONFLICT = 409;

const SandboxResetCard = memo(() => {
  const t = useTranslations('settings.system.sandboxReset');
  const [isResetting, setIsResetting] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  const handleReset = useCallback(async () => {
    setIsResetting(true);
    try {
      // silent: the server answers in English; this card shows the localized message itself.
      await apiRequest('/system/sandbox/recreate', {
        method: 'POST',
        body: JSON.stringify({ reset_python_env: true }),
        silent: true,
      });
      toast.success(t('success'));
    } catch (error) {
      // 409: tasks are still running; a reset now would kill them.
      toast.error(error instanceof ApiError && error.code === HTTP_CONFLICT ? t('busy') : t('failed'));
    } finally {
      setIsResetting(false);
      setShowConfirm(false);
    }
  }, [t]);

  return (
    <section className="space-y-6">
      <div className="flex items-center gap-3 px-2">
        <HardDrive className="w-5 h-5 text-muted-foreground" />
        <h2 className="text-sm font-black uppercase tracking-[0.2em] text-muted-foreground/70">{t('title')}</h2>
      </div>

      <div className="p-6 sm:p-8 rounded-[2.5rem] bg-white/5 border border-white/10 space-y-6">
        <div className="flex items-start gap-4">
          <div className="p-3 rounded-2xl bg-amber-500/10 border border-amber-500/20 flex-shrink-0">
            <AlertTriangle className="w-6 h-6 text-amber-500" />
          </div>
          <p className="flex-1 text-sm text-muted-foreground leading-relaxed">{t('description')}</p>
        </div>

        <div className="h-px bg-white/5" />

        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="space-y-1">
            <p className="text-xs text-muted-foreground/70">{t('preserved')}</p>
            <p className="text-xs text-muted-foreground/70">{t('reset')}</p>
          </div>

          <ConfirmDialog
            open={showConfirm}
            onOpenChange={setShowConfirm}
            title={t('confirmTitle')}
            description={t('confirmDescription')}
            confirmText={t('confirm')}
            cancelText={t('cancel')}
            loadingText={t('resetting')}
            variant="warning"
            onConfirm={handleReset}
            trigger={
              <button
                disabled={isResetting}
                className={cn(
                  'flex items-center justify-center gap-2 w-full sm:w-auto px-5 py-2.5 rounded-xl font-bold text-sm transition-all border',
                  'bg-amber-500/10 text-amber-500 border-amber-500/20 hover:bg-amber-500/20',
                  'disabled:opacity-50 disabled:cursor-not-allowed',
                )}
              >
                <RefreshCw className={cn('w-4 h-4', isResetting && 'animate-spin')} />
                {t('button')}
              </button>
            }
          />
        </div>
      </div>
    </section>
  );
});

SandboxResetCard.displayName = 'SandboxResetCard';

export default SandboxResetCard;
