'use client';

/**
 * [INPUT]
 * - @/services/agentRecovery::fetchProfileRecoveryHealth, rollbackProfileToLastKnownGood, exportProfileRecoveryDiagnostics
 * - @/hooks/shared/useToast::toast
 *
 * [OUTPUT]
 * - StartupRecoveryDialog: 渲染启动/配置异常自愈面板，支持一键回滚 Last-Known-Good 与导出诊断
 *
 * [POS]
 * Agent 启动异常自愈面板。
 * 当 Skill/MCP/Agent 配置发生冲突或无法启动时弹出，提供无痛回滚与排障能力。
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import {
  AlertTriangle,
  RotateCcw,
  Download,
  CheckCircle2,
  XCircle,
  ShieldAlert,
} from 'lucide-react';
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
} from '@/components/primitives/alert-dialog';
import { Button } from '@/components/primitives/button';
import { toast } from '@/hooks/shared/useToast';
import {
  fetchProfileRecoveryHealth,
  rollbackProfileToLastKnownGood,
  exportProfileRecoveryDiagnostics,
  type ProfileRecoveryHealthReport,
} from '@/services/agentRecovery';

interface StartupRecoveryDialogProps {
  agentId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onRecovered?: () => void;
}

export const StartupRecoveryDialog: React.FC<StartupRecoveryDialogProps> = ({
  agentId,
  open,
  onOpenChange,
  onRecovered,
}) => {
  const t = useTranslations('recovery');
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState<ProfileRecoveryHealthReport | null>(null);

  const loadHealth = useCallback(async () => {
    if (!agentId) return;
    setLoading(true);
    try {
      const data = await fetchProfileRecoveryHealth(agentId);
      setReport(data);
    } catch {
      toast({
        title: '获取健康诊断失败',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  }, [agentId]);

  useEffect(() => {
    if (open) {
      void loadHealth();
    }
  }, [open, loadHealth]);

  const handleRollback = async () => {
    if (!agentId) return;
    setLoading(true);
    try {
      const success = await rollbackProfileToLastKnownGood(agentId);
      if (success) {
        toast({
          title: '已成功回滚至最近良好配置',
        });
        onRecovered?.();
        onOpenChange(false);
      }
    } catch (error) {
      toast({
        title: '回滚失败',
        description: error instanceof Error ? error.message : String(error),
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  const handleExportDiagnostics = async () => {
    if (!agentId) return;
    try {
      const diagnostics = await exportProfileRecoveryDiagnostics(agentId);
      const blob = new Blob([JSON.stringify(diagnostics, null, 2)], {
        type: 'application/json',
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `agent-recovery-diagnostics-${agentId}-${Date.now()}.json`;
      a.click();
      URL.revokeObjectURL(url);
      toast({
        title: '已导出排障诊断包',
      });
    } catch (error) {
      toast({
        title: '导出诊断失败',
        description: error instanceof Error ? error.message : String(error),
        variant: 'destructive',
      });
    }
  };

  if (!open) return null;

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent className="max-w-lg">
        <AlertDialogHeader>
          <div className="flex items-center gap-2 text-amber-500">
            <ShieldAlert className="h-5 w-5" />
            <AlertDialogTitle className="text-base font-semibold">
              Agent 启动与配置自愈中心
            </AlertDialogTitle>
          </div>
          <AlertDialogDescription className="text-xs text-muted-foreground">
            检测到当前 Agent 绑定的组件或配置在启动期存在异常。您可以一键恢复至最后已知良好配置，或导出诊断包进行排查。
          </AlertDialogDescription>
        </AlertDialogHeader>

        <div className="my-3 space-y-3">
          {report && (
            <div className="rounded-lg border bg-muted/40 p-3 text-xs space-y-2">
              <div className="flex items-center justify-between font-medium">
                <span>组件探针状态</span>
                <span
                  className={
                    report.is_healthy ? 'text-emerald-500' : 'text-amber-500'
                  }
                >
                  {report.is_healthy ? '全部正常' : '发现故障隔离项'}
                </span>
              </div>

              {report.quarantined_components.length > 0 ? (
                <div className="space-y-1.5 pt-1">
                  {report.quarantined_components.map((c) => (
                    <div
                      key={`${c.component_type}-${c.component_id}`}
                      className="flex items-start gap-2 rounded bg-background p-2 border border-destructive/20 text-destructive text-[11px]"
                    >
                      <XCircle className="h-4 w-4 shrink-0 mt-0.5" />
                      <div>
                        <div className="font-semibold">
                          [{c.component_type}] {c.component_id}
                        </div>
                        {c.error_message && (
                          <div className="text-muted-foreground">
                            {c.error_message}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="flex items-center gap-1.5 text-emerald-600 text-[11px]">
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  <span>所有 Skill/MCP 及核心组件校验通过</span>
                </div>
              )}
            </div>
          )}
        </div>

        <AlertDialogFooter className="flex flex-row items-center justify-between gap-2 sm:justify-between">
          <Button
            variant="outline"
            size="sm"
            onClick={() => void handleExportDiagnostics()}
            className="gap-1.5 text-xs"
          >
            <Download className="h-3.5 w-3.5" />
            导出诊断包
          </Button>

          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onOpenChange(false)}
              className="text-xs"
            >
              忽略并继续
            </Button>
            {report?.has_last_known_good && (
              <Button
                variant="default"
                size="sm"
                onClick={() => void handleRollback()}
                disabled={loading}
                className="gap-1.5 text-xs bg-amber-600 hover:bg-amber-700 text-white"
              >
                <RotateCcw className="h-3.5 w-3.5" />
                回滚良好配置
              </Button>
            )}
          </div>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
};
