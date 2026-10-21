/**
 * [INPUT]
 * - react (POS: UI 组件与交互状态)
 * - lucide-react (POS: 矢量图标库)
 * - @/lib/utils/classnameUtils::cn (POS: Tailwind 样式合并纯函数)
 *
 * [OUTPUT]
 * - DeviceMeshPanel: 边缘设备硬件网格调度与拓扑管理面板
 * - DeviceMeshPanelProps: 组件属性契约
 * - MeshDeviceNodeItem: 边缘设备节点数据契约
 * - DeviceNodeKind: 硬件类型枚举联合
 * - DeviceNodeStatus: 节点状态枚举联合
 *
 * [POS]
 * 对话窗口边缘硬件设备网格监控与调度面板（EdgeDeviceMeshNodeScheduler）。
 * 展示树莓派、Mac Mini、边缘 GPU 服务器等硬件拓扑、遥测指标与命令派发。
 */
import React, { useState } from 'react';
import {
  Server,
  Cpu,
  Laptop,
  Smartphone,
  Zap,
  HardDrive,
  RefreshCw,
  Send,
  Key,
  Trash2,
  Activity,
  CheckCircle2,
  AlertCircle,
  Clock,
} from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';

export type DeviceNodeKind =
  | 'linux_server'
  | 'mac_mini'
  | 'raspberry_pi'
  | 'mobile_device'
  | 'edge_accelerator'
  | 'custom';

export type DeviceNodeStatus = 'online' | 'offline' | 'busy' | 'unpaired';

export interface DeviceTelemetryData {
  cpuUsagePct: number;
  memoryUsagePct: number;
  gpuUsagePct?: number | null;
  uptimeSeconds: number;
  activeTasks: number;
}

export interface MeshDeviceNodeItem {
  nodeId: string;
  name: string;
  kind: DeviceNodeKind;
  ipOrHostname: string;
  status: DeviceNodeStatus;
  capabilities: string[];
  telemetry: DeviceTelemetryData;
  lastHeartbeat?: number;
}

export interface DeviceMeshPanelProps {
  nodes: MeshDeviceNodeItem[];
  isLoading?: boolean;
  onRefresh?: () => Promise<void> | void;
  onPairNode?: (nodeId: string, pairingToken: string) => Promise<boolean | void> | boolean | void;
  onDispatchCommand?: (nodeId: string, command: string) => Promise<string | void> | string | void;
  onRemoveNode?: (nodeId: string) => Promise<void> | void;
  className?: string;
}

function getNodeKindIcon(kind: DeviceNodeKind): React.ReactElement {
  switch (kind) {
    case 'raspberry_pi':
      return <Cpu className="w-4 h-4 text-rose-500" />;
    case 'mac_mini':
      return <Laptop className="w-4 h-4 text-sky-500" />;
    case 'linux_server':
      return <Server className="w-4 h-4 text-emerald-500" />;
    case 'mobile_device':
      return <Smartphone className="w-4 h-4 text-violet-500" />;
    case 'edge_accelerator':
      return <Zap className="w-4 h-4 text-amber-500" />;
    default:
      return <HardDrive className="w-4 h-4 text-slate-500" />;
  }
}

function getStatusBadge(status: DeviceNodeStatus): React.ReactElement {
  switch (status) {
    case 'online':
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
          在线
        </span>
      );
    case 'busy':
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-ping" />
          忙碌
        </span>
      );
    case 'unpaired':
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-500/10 text-yellow-600 dark:text-yellow-400 border border-yellow-500/20">
          <AlertCircle className="w-3 h-3 text-yellow-500" />
          未配对
        </span>
      );
    case 'offline':
    default:
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-muted text-muted-foreground border border-border">
          <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground" />
          离线
        </span>
      );
  }
}

export const DeviceMeshPanel: React.FC<DeviceMeshPanelProps> = ({
  nodes,
  isLoading = false,
  onRefresh,
  onPairNode,
  onDispatchCommand,
  onRemoveNode,
  className,
}) => {
  const [pairingInputs, setPairingInputs] = useState<Record<string, string>>({});
  const [commandInputs, setCommandInputs] = useState<Record<string, string>>({});
  const [activeActionNode, setActiveActionNode] = useState<string | null>(null);
  const [dispatchFeedback, setDispatchFeedback] = useState<Record<string, string>>({});

  const onlineCount = nodes.filter((n) => n.status === 'online').length;
  const busyCount = nodes.filter((n) => n.status === 'busy').length;
  const unpairedCount = nodes.filter((n) => n.status === 'unpaired').length;

  const handlePair = async (nodeId: string): Promise<void> => {
    const token = pairingInputs[nodeId]?.trim();
    if (!token || !onPairNode) {
      return;
    }
    setActiveActionNode(nodeId);
    try {
      await onPairNode(nodeId, token);
      setPairingInputs((prev) => ({ ...prev, [nodeId]: '' }));
    } finally {
      setActiveActionNode(null);
    }
  };

  const handleDispatch = async (nodeId: string): Promise<void> => {
    const cmd = commandInputs[nodeId]?.trim();
    if (!cmd || !onDispatchCommand) {
      return;
    }
    setActiveActionNode(nodeId);
    try {
      const output = await onDispatchCommand(nodeId, cmd);
      setDispatchFeedback((prev) => ({
        ...prev,
        [nodeId]: typeof output === 'string' ? output : '命令已成功派发至设备',
      }));
      setCommandInputs((prev) => ({ ...prev, [nodeId]: '' }));
    } finally {
      setActiveActionNode(null);
    }
  };

  return (
    <div
      data-testid="device-mesh-panel"
      className={cn(
        'rounded-xl border border-border bg-card p-4 shadow-sm space-y-4',
        className
      )}
    >
      {/* Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/60 pb-3">
        <div className="flex items-center gap-2">
          <div className="p-2 rounded-lg bg-primary/10 text-primary">
            <Activity className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
              边缘计算设备网格
              <span className="text-xs font-normal text-muted-foreground">
                ({nodes.length} 台设备)
              </span>
            </h3>
            <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5">
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block" />
                在线 {onlineCount}
              </span>
              <span>•</span>
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-amber-500 inline-block" />
                忙碌 {busyCount}
              </span>
              <span>•</span>
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-yellow-500 inline-block" />
                待配对 {unpairedCount}
              </span>
            </div>
          </div>
        </div>

        {onRefresh && (
          <button
            type="button"
            data-testid="refresh-mesh-btn"
            disabled={isLoading}
            onClick={() => void onRefresh()}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-border hover:bg-muted/80 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={cn('w-3.5 h-3.5', isLoading && 'animate-spin')} />
            刷新状态
          </button>
        )}
      </div>

      {/* Nodes Grid / Empty State */}
      {nodes.length === 0 ? (
        <div
          data-testid="empty-mesh-state"
          className="text-center py-8 px-4 rounded-lg border border-dashed border-border"
        >
          <Server className="w-8 h-8 text-muted-foreground/60 mx-auto mb-2" />
          <p className="text-xs font-medium text-foreground">暂无连接的边缘设备</p>
          <p className="text-[11px] text-muted-foreground mt-1">
            注册 Raspberry Pi、Mac Mini 或 Linux GPU 节点后即可实现分布式任务编排
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3" data-testid="nodes-grid">
          {nodes.map((node) => {
            const isActing = activeActionNode === node.nodeId;
            const feedback = dispatchFeedback[node.nodeId];

            return (
              <div
                key={node.nodeId}
                data-testid={`mesh-node-card-${node.nodeId}`}
                className="rounded-lg border border-border/80 bg-background/50 p-3 flex flex-col justify-between space-y-3 hover:border-primary/40 transition-colors"
              >
                {/* Node Header */}
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-start gap-2">
                    <div className="p-1.5 rounded-md bg-muted text-foreground mt-0.5">
                      {getNodeKindIcon(node.kind)}
                    </div>
                    <div>
                      <div className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                        {node.name}
                      </div>
                      <div className="text-[11px] font-mono text-muted-foreground">
                        {node.ipOrHostname} • <span className="opacity-75">{node.nodeId}</span>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    {getStatusBadge(node.status)}
                    {onRemoveNode && (
                      <button
                        type="button"
                        data-testid={`remove-node-${node.nodeId}`}
                        title="移除节点"
                        onClick={() => void onRemoveNode(node.nodeId)}
                        className="p-1 text-muted-foreground hover:text-destructive transition-colors rounded"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                </div>

                {/* Capabilities Chips */}
                {node.capabilities.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {node.capabilities.map((cap) => (
                      <span
                        key={cap}
                        className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-muted/60 text-muted-foreground border border-border/40"
                      >
                        {cap}
                      </span>
                    ))}
                  </div>
                )}

                {/* Telemetry Metrics */}
                <div className="grid grid-cols-3 gap-2 bg-muted/30 p-2 rounded-md text-[11px]">
                  <div>
                    <div className="text-muted-foreground">CPU 负载</div>
                    <div className="font-semibold text-foreground">
                      {node.telemetry.cpuUsagePct.toFixed(1)}%
                    </div>
                  </div>
                  <div>
                    <div className="text-muted-foreground">内存占用</div>
                    <div className="font-semibold text-foreground">
                      {node.telemetry.memoryUsagePct.toFixed(1)}%
                    </div>
                  </div>
                  <div>
                    <div className="text-muted-foreground">活跃任务</div>
                    <div className="font-semibold text-foreground flex items-center gap-1">
                      <Clock className="w-3 h-3 text-primary inline" />
                      {node.telemetry.activeTasks}
                    </div>
                  </div>
                </div>

                {/* Feedback Alert if available */}
                {feedback && (
                  <div className="text-[11px] p-2 rounded bg-primary/10 text-primary border border-primary/20 flex items-start gap-1.5">
                    <CheckCircle2 className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                    <span className="line-clamp-2">{feedback}</span>
                  </div>
                )}

                {/* Action Area: Pairing or Dispatch */}
                {node.status === 'unpaired' ? (
                  <div className="flex items-center gap-1.5 pt-1">
                    <div className="relative flex-1">
                      <Key className="w-3.5 h-3.5 absolute left-2 top-2 text-muted-foreground" />
                      <input
                        type="password"
                        data-testid={`pairing-token-input-${node.nodeId}`}
                        placeholder="输入配对 Token..."
                        value={pairingInputs[node.nodeId] || ''}
                        onChange={(e) =>
                          setPairingInputs((prev) => ({
                            ...prev,
                            [node.nodeId]: e.target.value,
                          }))
                        }
                        className="w-full pl-7 pr-2 py-1 text-xs rounded border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                      />
                    </div>
                    <button
                      type="button"
                      data-testid={`pair-node-btn-${node.nodeId}`}
                      disabled={isActing || !pairingInputs[node.nodeId]?.trim()}
                      onClick={() => void handlePair(node.nodeId)}
                      className="px-2.5 py-1 text-xs font-medium rounded bg-yellow-500 hover:bg-yellow-600 text-white disabled:opacity-50 transition-colors"
                    >
                      {isActing ? '配对中...' : '配对'}
                    </button>
                  </div>
                ) : (
                  <div className="flex items-center gap-1.5 pt-1">
                    <input
                      type="text"
                      data-testid={`command-input-${node.nodeId}`}
                      placeholder="派发 Shell 命令 (如 uname -a)..."
                      value={commandInputs[node.nodeId] || ''}
                      onChange={(e) =>
                        setCommandInputs((prev) => ({
                          ...prev,
                          [node.nodeId]: e.target.value,
                        }))
                      }
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          void handleDispatch(node.nodeId);
                        }
                      }}
                      className="flex-1 px-2.5 py-1 text-xs font-mono rounded border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                    <button
                      type="button"
                      data-testid={`dispatch-btn-${node.nodeId}`}
                      disabled={isActing || !commandInputs[node.nodeId]?.trim()}
                      onClick={() => void handleDispatch(node.nodeId)}
                      className="px-2.5 py-1 text-xs font-medium rounded bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors flex items-center gap-1"
                    >
                      <Send className="w-3 h-3" />
                      <span>{isActing ? '派发中' : '派发'}</span>
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
