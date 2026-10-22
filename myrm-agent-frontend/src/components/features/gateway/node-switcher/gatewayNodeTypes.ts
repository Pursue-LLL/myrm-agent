/**
 * Multi-Node Gateway Switcher Types
 * Web 瘦客户端多节点/多宿主 Agent 网关管理与无缝切换类型系统
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 规范定义多节点描述符、健康探针状态机与硬件资源指纹；
 * 3. 行数严格受控在 400 行以内。
 */

export type GatewayNodeStatus =
  | 'healthy'
  | 'unreachable'
  | 'degraded'
  | 'checking'
  | 'offline';

export interface GatewayHardwareInfo {
  gpu?: string;
  ramGb?: number;
  cpuCores?: number;
  osPlatform?: string;
}

export interface GatewayNodeDescriptor {
  id: string;
  name: string;
  endpointUrl: string;
  token?: string;
  isDefault: boolean;
  pingMs: number;
  status: GatewayNodeStatus;
  tags: string[];
  hardwareInfo?: GatewayHardwareInfo;
  lastCheckedAt: string;
}

export interface ProbeResult {
  nodeId: string;
  status: GatewayNodeStatus;
  pingMs: number;
  error?: string;
  hardwareInfo?: GatewayHardwareInfo;
}

export interface GatewaySwitchEventDetail {
  previousNodeId: string;
  currentNodeId: string;
  endpointUrl: string;
}
