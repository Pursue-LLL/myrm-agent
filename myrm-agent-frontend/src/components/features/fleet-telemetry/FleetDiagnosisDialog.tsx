'use client';

/**
 * [INPUT]
 * - @/services/fleetTelemetry::FleetDiagnosisResponse, diagnoseFleetNode, FleetDiagnoseParams (POS: 机队健康排障诊断服务)
 * - @/components/primitives/dialog::Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription (POS: 模态框组件)
 *
 * [OUTPUT]
 * - FleetDiagnosisDialog: 分布式节点六态全流程自省诊断定位弹窗
 *
 * [POS]
 * 表现层/机队可观测性：呈现五级渐进式自省探针流水线执行详情，精准呈现根因与行动建议，消灭黑盒断连。
 */

import React, { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/primitives/dialog';
import {
  type FleetDiagnosisResponse,
  type FleetDiagnoseParams,
  diagnoseFleetNode,
} from '@/services/fleetTelemetry';
import {
  Activity,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  RefreshCw,
  Server,
  Key,
  Cpu,
  Coins,
  Radio,
} from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';

interface FleetDiagnosisDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  nodeParams: FleetDiagnoseParams;
  initialReport?: FleetDiagnosisResponse | null;
}

const STAGE_LABELS: Record<string, { label: string; icon: React.FC<{ className?: string }> }> = {
  physical_network: { label: '物理网络连通性 (TCP/Ping)', icon: Radio },
  credential_auth: { label: '主机凭据与 TLS 握手 (Auth/TLS)', icon: Key },
  gateway_daemon: { label: '服务端守护进程 (Myrm Daemon)', icon: Server },
  runner_executor: { label: '代码沙箱与执行器 (Runner/Docker)', icon: Cpu },
  provider_quota: { label: '上游模型配额与额度 (Provider Quota)', icon: Coins },
};

export const FleetDiagnosisDialog: React.FC<FleetDiagnosisDialogProps> = ({
  open,
  onOpenChange,
  nodeParams,
  initialReport,
}) => {
  const [report, setReport] = useState<FleetDiagnosisResponse | null>(initialReport ?? null);
  const [loading, setLoading] = useState<boolean>(false);

  const handleRunDiagnosis = async () => {
    setLoading(true);
    try {
      const res = await diagnoseFleetNode(nodeParams);
      setReport(res);
    } catch (err) {
      // 容错降级
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg p-5 rounded-2xl bg-popover/95 backdrop-blur-md border border-border/80 shadow-2xl">
        <DialogHeader className="space-y-1">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Activity className="w-5 h-5 text-primary" />
              <DialogTitle className="text-base font-semibold text-foreground">
                节点自省诊断 · {nodeParams.node_name}
              </DialogTitle>
            </div>
            <button
              type="button"
              onClick={handleRunDiagnosis}
              disabled={loading}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-lg border border-border bg-background hover:bg-muted font-medium transition-colors cursor-pointer disabled:opacity-50"
            >
              <RefreshCw className={cn('w-3.5 h-3.5', loading && 'animate-spin')} />
              <span>重新诊断</span>
            </button>
          </div>
          <DialogDescription className="text-xs text-muted-foreground">
            目标地址：{nodeParams.host}:{nodeParams.port ?? 8000} · 排除网络伪断连，精准定位额度与进程故障
          </DialogDescription>
        </DialogHeader>

        <div className="mt-4 space-y-4">
          {/* 五级探针流水线展示 */}
          <div className="space-y-2">
            <div className="text-xs font-medium text-foreground">五级排障自省探针</div>
            <div className="space-y-1.5">
              {['physical_network', 'credential_auth', 'gateway_daemon', 'runner_executor', 'provider_quota'].map(
                (stageKey) => {
                  const stageMeta = STAGE_LABELS[stageKey];
                  const Icon = stageMeta.icon;
                  const stageResult = report?.stages.find((s) => s.stage === stageKey);
                  const isPassed = stageResult?.passed === true;
                  const isFailed = stageResult?.passed === false;
                  const isPending = !stageResult;

                  return (
                    <div
                      key={stageKey}
                      className={cn(
                        'flex items-center justify-between p-2 rounded-lg border text-xs transition-colors',
                        isPassed && 'border-emerald-500/20 bg-emerald-500/5',
                        isFailed && 'border-rose-500/30 bg-rose-500/5',
                        isPending && 'border-border/40 bg-muted/20 text-muted-foreground'
                      )}
                    >
                      <div className="flex items-center gap-2">
                        <Icon className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                        <span className="font-medium text-foreground">{stageMeta.label}</span>
                      </div>
                      <div className="flex items-center gap-1.5 font-mono text-[11px]">
                        {stageResult && (
                          <span className="text-muted-foreground">{stageResult.latency_ms.toFixed(1)}ms</span>
                        )}
                        {isPassed && <CheckCircle2 className="w-4 h-4 text-emerald-500" />}
                        {isFailed && <XCircle className="w-4 h-4 text-rose-500" />}
                        {isPending && <span className="text-[10px] text-muted-foreground">待检测</span>}
                      </div>
                    </div>
                  );
                }
              )}
            </div>
          </div>

          {/* 故障根因与行动建议卡片 */}
          {report && (
            <div
              className={cn(
                'p-3.5 rounded-xl border text-xs space-y-2',
                report.state === 'online'
                  ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-950 dark:text-emerald-100'
                  : 'border-amber-500/30 bg-amber-500/10 text-amber-950 dark:text-amber-100'
              )}
            >
              <div className="flex items-center gap-1.5 font-semibold">
                {report.state === 'online' ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                ) : (
                  <AlertTriangle className="w-4 h-4 text-amber-500" />
                )}
                <span>
                  {report.state === 'online' ? '全维健康就绪' : `诊断结论：${report.state.toUpperCase()}`}
                </span>
              </div>
              <div className="text-[11px] leading-relaxed">
                <span className="font-medium">根因分析：</span>
                {report.root_cause}
              </div>
              <div className="text-[11px] leading-relaxed pt-1 border-t border-border/40">
                <span className="font-medium">建议操作：</span>
                {report.recommended_action}
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};
