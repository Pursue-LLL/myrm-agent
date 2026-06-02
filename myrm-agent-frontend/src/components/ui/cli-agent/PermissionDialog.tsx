'use client';

/**
 * CLI Agent 权限对话框
 *
 * 当 Agent 请求执行需要确认的操作时显示。
 * 借鉴 craft-agents 的设计：
 * - 显示工具名称和命令
 * - 危险命令高亮警告
 * - 支持 "Always Allow" 选项
 */

import { useTranslations } from 'next-intl';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { useState } from 'react';
import { usePermissionDialog, useCLIAgent } from '@/hooks/useCLIAgent';
import { cn } from '@/lib/utils/classnameUtils';
import {
  IconAlertTriangle,
  IconTerminal,
  IconShield,
  IconCheck,
  IconX,
  IconExplore,
  IconAsk,
  IconAuto,
} from '@/components/ui/icons/PremiumIcons';
import { PremiumTooltip } from '@/components/ui/PremiumTooltip';

export function PermissionDialog() {
  const t = useTranslations('cliAgent');
  const { isOpen, request, allow, deny, pendingCount } = usePermissionDialog();
  const [alwaysAllow, setAlwaysAllow] = useState(false);

  if (!request) return null;

  const handleAllow = () => {
    allow(alwaysAllow);
    setAlwaysAllow(false);
  };

  const handleDeny = () => {
    deny();
    setAlwaysAllow(false);
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && handleDeny()}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {request.isDangerous ? (
              <IconAlertTriangle className="h-5 w-5 text-destructive" />
            ) : (
              <IconShield className="h-5 w-5 text-primary" />
            )}
            {t('permissionRequest')}
          </DialogTitle>
          <DialogDescription>
            {request.isDangerous ? t('dangerousCommandWarning') : t('permissionRequestDescription')}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* 工具名称 */}
          <div className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">{t('tool')}:</span>
            <code className="rounded bg-muted px-2 py-1 font-mono">{request.toolName}</code>
          </div>

          {/* 命令内容 */}
          <div
            className={cn(
              'rounded-lg border p-4',
              request.isDangerous ? 'border-destructive/50 bg-destructive/10' : 'border-border bg-muted/50',
            )}
          >
            <div className="flex items-start gap-3">
              <IconTerminal className="mt-0.5 h-4 w-4 text-muted-foreground" />
              <code className="flex-1 break-all font-mono text-sm">{request.command}</code>
            </div>
          </div>

          {/* 危险警告 */}
          {request.isDangerous && (
            <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
              <IconAlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <p>{t('dangerousCommandExplanation')}</p>
            </div>
          )}

          {/* Always Allow 选项（仅非危险命令） */}
          {!request.isDangerous && (
            <div className="flex items-center space-x-2">
              <Checkbox
                id="always-allow"
                checked={alwaysAllow}
                onCheckedChange={(checked) => setAlwaysAllow(checked === true)}
              />
              <label htmlFor="always-allow" className="text-sm text-muted-foreground cursor-pointer">
                {t('alwaysAllowThisTool')}
              </label>
            </div>
          )}

          {/* 待处理数量 */}
          {pendingCount > 1 && (
            <p className="text-xs text-muted-foreground">{t('pendingPermissions', { count: pendingCount - 1 })}</p>
          )}
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={handleDeny}>
            <IconX className="mr-2 h-4 w-4" />
            {t('deny')}
          </Button>
          <Button onClick={handleAllow} variant={request.isDangerous ? 'destructive' : 'default'}>
            <IconCheck className="mr-2 h-4 w-4" />
            {request.isDangerous ? t('allowAnyway') : t('allow')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/**
 * 权限模式指示器
 *
 * 显示当前权限模式，点击或 SHIFT+TAB 切换。
 */
export function PermissionModeIndicator() {
  const t = useTranslations('cliAgent');
  const { permissionMode, cycleMode } = useCLIAgent();

  const modeConfig = {
    explore: {
      icon: <IconExplore className="w-3.5 h-3.5" />,
      label: t('modeExplore'),
      description: t('modeExploreDescription'),
      color: 'text-blue-500',
      bg: 'bg-blue-500/10',
    },
    ask: {
      icon: <IconAsk className="w-3.5 h-3.5" />,
      label: t('modeAsk'),
      description: t('modeAskDescription'),
      color: 'text-yellow-500',
      bg: 'bg-yellow-500/10',
    },
    auto: {
      icon: <IconAuto className="w-3.5 h-3.5" />,
      label: t('modeAuto'),
      description: t('modeAutoDescription'),
      color: 'text-green-500',
      bg: 'bg-green-500/10',
    },
  };

  const config = modeConfig[permissionMode];

  return (
    <PremiumTooltip
      tooltipContent={
        <div className="flex flex-col gap-1">
          <span>{config.description}</span>
          <span className="text-zinc-500 dark:text-zinc-400 text-[10px] uppercase font-bold">
            {t('pressShiftTabToSwitch')}
          </span>
        </div>
      }
    >
      <button
        onClick={cycleMode}
        className={cn(
          'flex items-center gap-2 rounded-full px-3 py-1.5 text-sm transition-colors',
          config.bg,
          'hover:opacity-80',
        )}
      >
        <span className={config.color}>{config.icon}</span>
        <span className={config.color}>{config.label}</span>
      </button>
    </PremiumTooltip>
  );
}
