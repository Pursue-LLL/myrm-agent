'use client';

/**
 * Permission Approval Dialog
 *
 * 权限审批对话框，当 Agent 执行需要用户确认的操作时显示。
 * 仅 Tauri/Self-hosted 模式显示。
 */

import { useTranslations } from 'next-intl';

import {
  AlertTriangle,
  CheckCircle,
  Code,
  FileEdit,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Terminal,
  XCircle,
} from 'lucide-react';

import { cn } from '@/lib/utils/classnameUtils';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

export type RiskLevel = 'low' | 'medium' | 'high' | 'critical';

export interface PendingPermission {
  id: string;
  turn_id?: string;
  action: string;
  resource: string;
  details: Record<string, unknown>;
  risk_level: RiskLevel;
  reason: string;
  created_at: string;
}

interface PermissionDialogProps {
  permission: PendingPermission | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onApprove: (id: string) => void;
  onDeny: (id: string) => void;
  isLoading?: boolean;
}

// Risk level badge
const RiskBadge = ({ level }: { level: RiskLevel }) => {
  const t = useTranslations('agentEvents.risk');

  const config = {
    low: {
      label: t('low'),
      variant: 'outline' as const,
      className: 'border-green-500 text-green-500',
      icon: ShieldCheck,
    },
    medium: {
      label: t('medium'),
      variant: 'outline' as const,
      className: 'border-yellow-500 text-yellow-500',
      icon: Shield,
    },
    high: {
      label: t('high'),
      variant: 'outline' as const,
      className: 'border-orange-500 text-orange-500',
      icon: ShieldAlert,
    },
    critical: {
      label: t('critical'),
      variant: 'destructive' as const,
      className: '',
      icon: AlertTriangle,
    },
  };

  const { label, variant, className, icon: Icon } = config[level];

  return (
    <Badge variant={variant} className={cn('gap-1', className)}>
      <Icon className="h-3 w-3" />
      {label}
    </Badge>
  );
};

// Action icon
const getActionIcon = (action: string) => {
  switch (action) {
    case 'tool_call':
      return <Code className="h-5 w-5" />;
    case 'command':
      return <Terminal className="h-5 w-5" />;
    case 'file_write':
    case 'file_delete':
      return <FileEdit className="h-5 w-5" />;
    default:
      return <Shield className="h-5 w-5" />;
  }
};

export function PermissionDialog({
  permission,
  open,
  onOpenChange,
  onApprove,
  onDeny,
  isLoading,
}: PermissionDialogProps) {
  const t = useTranslations('agentEvents.permission');

  if (!permission) return null;

  const actionLabels: Record<string, string> = {
    tool_call: t('actions.toolCall'),
    command: t('actions.command'),
    file_write: t('actions.fileWrite'),
    file_delete: t('actions.fileDelete'),
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-yellow-500/10 text-yellow-500">
              {getActionIcon(permission.action)}
            </div>
            <div>
              <DialogTitle className="flex items-center gap-2">
                {t('title')}
                <RiskBadge level={permission.risk_level} />
              </DialogTitle>
              <DialogDescription>{actionLabels[permission.action] || permission.action}</DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Resource */}
          <div>
            <label className="text-sm font-medium text-muted-foreground">{t('resource')}</label>
            <div className="mt-1 rounded-full bg-muted p-3 font-mono text-sm">{permission.resource}</div>
          </div>

          {/* Reason */}
          <div>
            <label className="text-sm font-medium text-muted-foreground">{t('reason')}</label>
            <p className="mt-1 text-sm">{permission.reason}</p>
          </div>

          {/* Details */}
          {Object.keys(permission.details).length > 0 && (
            <div>
              <label className="text-sm font-medium text-muted-foreground">{t('details')}</label>
              <pre className="mt-1 max-h-32 overflow-auto rounded-full bg-muted p-3 text-xs">
                {JSON.stringify(permission.details, null, 2)}
              </pre>
            </div>
          )}

          {/* Warning for high/critical */}
          {(permission.risk_level === 'high' || permission.risk_level === 'critical') && (
            <div className="flex items-start gap-2 rounded-full border border-destructive/50 bg-destructive/5 p-3">
              <AlertTriangle className="mt-0.5 h-4 w-4 text-destructive" />
              <div className="text-sm text-destructive">
                {permission.risk_level === 'critical' ? t('warningCritical') : t('warningHigh')}
              </div>
            </div>
          )}
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={() => onDeny(permission.id)} disabled={isLoading}>
            <XCircle className="mr-2 h-4 w-4" />
            {t('deny')}
          </Button>
          <Button
            variant={permission.risk_level === 'critical' ? 'destructive' : 'default'}
            onClick={() => onApprove(permission.id)}
            disabled={isLoading}
          >
            <CheckCircle className="mr-2 h-4 w-4" />
            {t('approve')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// Permission mode selector
export type PermissionMode = 'safe' | 'ask' | 'allow_all';

interface PermissionModeSelectorProps {
  mode: PermissionMode;
  onModeChange: (mode: PermissionMode) => void;
  disabled?: boolean;
}

export function PermissionModeSelector({ mode, onModeChange, disabled }: PermissionModeSelectorProps) {
  const t = useTranslations('agentEvents.permissionMode');

  const modes: { value: PermissionMode; label: string; description: string }[] = [
    {
      value: 'safe',
      label: t('safe.label'),
      description: t('safe.description'),
    },
    {
      value: 'ask',
      label: t('ask.label'),
      description: t('ask.description'),
    },
    {
      value: 'allow_all',
      label: t('allowAll.label'),
      description: t('allowAll.description'),
    },
  ];

  return (
    <div className="space-y-2">
      <label className="text-sm font-medium">{t('title')}</label>
      <div className="grid gap-2">
        {modes.map((m) => (
          <button
            key={m.value}
            type="button"
            disabled={disabled}
            onClick={() => onModeChange(m.value)}
            className={cn(
              'flex items-start gap-3 rounded-lg border p-3 text-left transition-colors',
              'hover:bg-muted/50',
              mode === m.value && 'border-primary bg-primary/5',
              disabled && 'cursor-not-allowed opacity-50',
            )}
          >
            <div
              className={cn(
                'mt-0.5 h-4 w-4 rounded-full border-2',
                mode === m.value ? 'border-primary bg-primary' : 'border-muted-foreground',
              )}
            />
            <div>
              <div className="font-medium">{m.label}</div>
              <div className="text-sm text-muted-foreground">{m.description}</div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
