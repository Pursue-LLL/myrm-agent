/**
 * [INPUT]
 * - 无外部输入，纯 TypeScript 类型契约
 *
 * [OUTPUT]
 * - PortProcessInfo: 端口占用进程详细信息
 * - ProcessLineageNode: 进程调用派生链节点
 * - PortInspectResponse: 端口检测响应体
 * - ProcessKillRequest: 终止进程请求体
 * - ProcessKillResponse: 终止进程操作响应体
 *
 * [POS]
 * src/components/features/system-monitor/types.ts — 端口冲突检测与进程树溯源类型契约。
 */

export interface PortProcessInfo {
  pid: number;
  name: string;
  cmdline: string[];
  cpu_percent: number;
  memory_mb: number;
  status: string;
  username: string;
  cwd?: string | null;
  create_time: number;
  is_protected: boolean;
}

export interface ProcessLineageNode {
  pid: number;
  ppid: number;
  name: string;
  cmdline: string[];
  cwd?: string | null;
  username: string;
  is_high_resource: boolean;
}

export interface PortInspectResponse {
  port: number;
  is_in_use: boolean;
  process?: PortProcessInfo | null;
  lineage: ProcessLineageNode[];
}

export interface ProcessKillRequest {
  force?: boolean;
  reason?: string;
}

export interface ProcessKillResponse {
  success: boolean;
  pid: number;
  signal_sent: string;
  message: string;
}
