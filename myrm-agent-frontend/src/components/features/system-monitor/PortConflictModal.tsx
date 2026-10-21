'use client';

/**
 * [INPUT]
 * - ./types::PortInspectResponse, ProcessKillResponse (POS: 端口与进程模型)
 * - ./ProcessLineageView (POS: 进程树溯源组件)
 * - @/components/primitives/dialog::Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription (POS: 模态框基元)
 * - lucide-react::Radio, AlertCircle, CheckCircle2, ShieldAlert, Skull, RefreshCw, Loader2 (POS: 视觉指示图标)
 *
 * [OUTPUT]
 * - PortConflictModal: 端口冲突排查诊断与一键安全查杀交互视窗
 *
 * [POS]
 * src/components/features/system-monitor/PortConflictModal.tsx — 端口占用与查杀弹窗。
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/primitives/dialog';
import {
  Radio,
  AlertCircle,
  CheckCircle2,
  ShieldAlert,
  Skull,
  RefreshCw,
  Loader2,
} from 'lucide-react';
import type { PortInspectResponse, ProcessKillResponse } from './types';
import { ProcessLineageView } from './ProcessLineageView';

interface PortConflictModalProps {
  port: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onResolved?: (port: number) => void;
  initialData?: PortInspectResponse | null;
}

export const PortConflictModal: React.FC<PortConflictModalProps> = ({
  port,
  open,
  onOpenChange,
  onResolved,
  initialData = null,
}) => {
  const [data, setData] = useState<PortInspectResponse | null>(initialData);
  const [loading, setLoading] = useState<boolean>(false);
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const fetchInspection = useCallback(async () => {
    if (port <= 0) return;
    setLoading(true);
    setErrorMsg(null);
    try {
      const resp = await fetch(`/api/v1/system/ports/${port}/inspect`);
      if (!resp.ok) {
        throw new Error(`Failed to inspect port (status: ${resp.status})`);
      }
      const json: PortInspectResponse = await resp.json();
      setData(json);
      if (!json.is_in_use && onResolved) {
        onResolved(port);
      }
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : '检测端口状态失败');
    } finally {
      setLoading(false);
    }
  }, [port, onResolved]);

  useEffect(() => {
    if (open) {
      if (initialData) {
        setData(initialData);
        if (!initialData.is_in_use && onResolved) {
          onResolved(port);
        }
      } else {
        void fetchInspection();
      }
    }
  }, [open, initialData, fetchInspection, onResolved, port]);

  const handleKillProcess = async (force: boolean) => {
    if (!data?.process) return;
    setActionLoading(true);
    setErrorMsg(null);
    try {
      const resp = await fetch(`/api/v1/system/processes/${data.process.pid}/kill`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          force,
          reason: `port_${port}_conflict_kill`,
        }),
      });

      if (!resp.ok) {
        const errorData = await resp.json().catch(() => ({ detail: '查杀进程被系统拒绝' }));
        throw new Error(errorData.detail || `操作失败 (status ${resp.status})`);
      }

      const res: ProcessKillResponse = await resp.json();
      if (res.success) {
        // 延时刷新确认端口释放
        setTimeout(() => {
          void fetchInspection();
        }, 150);
      }
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : '无法终止进程');
    } finally {
      setActionLoading(false);
    }
  };

  const proc = data?.process;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        data-testid="port-conflict-modal"
        className="max-w-xl max-h-[85vh] overflow-y-auto space-y-4"
      >
        <DialogHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Radio className="w-5 h-5 text-amber-500" />
              <DialogTitle className="text-base font-semibold">
                端口占用诊断与查杀 (Port :{port})
              </DialogTitle>
            </div>
            <button
              type="button"
              onClick={fetchInspection}
              disabled={loading || actionLoading}
              title="重新检测端口状态"
              className="p-1 text-muted-foreground hover:text-foreground rounded transition-colors disabled:opacity-40"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>
          <DialogDescription className="text-xs text-muted-foreground">
            排查本地或沙箱开发服务端口冲突，精准定位占用者父子派生链并支持一键安全终止。
          </DialogDescription>
        </DialogHeader>

        {errorMsg && (
          <div className="p-3 text-xs rounded-md bg-destructive/10 border border-destructive/30 text-destructive flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}

        {loading && !data && (
          <div className="py-8 flex flex-col items-center justify-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="w-5 h-5 animate-spin text-primary" />
            <span>正在检测端口 {port} 占用状态...</span>
          </div>
        )}

        {data && !data.is_in_use && (
          <div className="py-6 flex flex-col items-center justify-center gap-2 text-center text-xs">
            <CheckCircle2 className="w-8 h-8 text-emerald-500" />
            <span className="font-semibold text-emerald-600 dark:text-emerald-400">
              端口 :{port} 当前空闲无占用
            </span>
            <span className="text-muted-foreground text-[11px]">
              本地开发服务或测试任务现在可以正常启动并绑定该端口。
            </span>
          </div>
        )}

        {data && data.is_in_use && proc && (
          <div className="space-y-3.5">
            {/* 占用进程主信息卡 */}
            <div className="p-3 rounded-lg border border-border/80 bg-muted/20 text-xs space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-sm text-foreground">{proc.name}</span>
                  <span className="px-1.5 py-0.5 rounded font-mono text-[11px] bg-muted/60 text-muted-foreground">
                    PID {proc.pid}
                  </span>
                  {proc.username && (
                    <span className="text-[11px] text-muted-foreground">
                      属主: {proc.username}
                    </span>
                  )}
                </div>
                {proc.is_protected ? (
                  <span className="inline-flex items-center gap-1 text-[11px] font-medium text-destructive">
                    <ShieldAlert className="w-3.5 h-3.5" />
                    系统受保护进程
                  </span>
                ) : (
                  <span className="text-[11px] text-muted-foreground">
                    CPU {proc.cpu_percent}% · 内存 {proc.memory_mb} MB
                  </span>
                )}
              </div>

              {proc.is_protected && (
                <div className="p-2 text-[11px] rounded bg-destructive/10 text-destructive border border-destructive/20">
                  ⚠️ 该进程属于系统核心守护进程或当前运行实例，系统防火墙已将其列入白名单硬保护，禁止直接终止。
                </div>
              )}
            </div>

            {/* 完整启动链路回溯 */}
            <ProcessLineageView lineage={data.lineage} />

            {/* 操作控制区 */}
            <div className="flex items-center justify-end gap-2 pt-2 border-t border-border/40">
              <button
                type="button"
                onClick={() => onOpenChange(false)}
                className="px-3 py-1.5 text-xs rounded border border-border/60 hover:bg-muted/40 transition-colors"
              >
                关闭
              </button>
              <button
                type="button"
                data-testid="safe-kill-btn"
                onClick={() => handleKillProcess(false)}
                disabled={actionLoading || proc.is_protected}
                className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded border border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300 hover:bg-amber-500/20 transition-colors disabled:opacity-40"
              >
                {actionLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
                <span>安全终止 (SIGTERM)</span>
              </button>
              <button
                type="button"
                data-testid="force-kill-btn"
                onClick={() => handleKillProcess(true)}
                disabled={actionLoading || proc.is_protected}
                className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded bg-destructive text-destructive-foreground hover:bg-destructive/90 transition-colors disabled:opacity-40"
              >
                {actionLoading ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Skull className="w-3.5 h-3.5" />
                )}
                <span>强制结束 (SIGKILL)</span>
              </button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};
