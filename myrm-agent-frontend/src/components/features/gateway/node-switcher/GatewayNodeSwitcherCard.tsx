/**
 * Gateway Node Switcher Card
 * Web 瘦客户端多节点/多宿主 Agent 网关管理与无缝热切换卡片
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 零原生 emoji，全部采用 Lucide 矢量图标；
 * 3. 前端所有 if 显式包裹大括号；
 * 4. 严格遵守 a11y 规范（dialog, output, label htmlFor）；
 * 5. 行数严格受控在 400 行以内。
 */

import React from 'react';
import {
  Activity,
  Check,
  Cpu,
  Globe,
  HardDrive,
  Plus,
  RefreshCw,
  Server,
  ShieldCheck,
  Trash2,
  Wifi,
} from 'lucide-react';
import { GatewayAddNodeModal } from './GatewayAddNodeModal';
import { GatewayNodeStatus } from './gatewayNodeTypes';
import { useGatewayNodeStore } from './useGatewayNodeStore';

export interface GatewayNodeSwitcherCardProps {
  className?: string;
}

export const GatewayNodeSwitcherCard: React.FC<GatewayNodeSwitcherCardProps> = ({
  className = '',
}) => {
  const {
    activeNodeId,
    searchQuery,
    tagFilter,
    isAddModalOpen,
    switchActiveNode,
    addNode,
    deleteNode,
    probeNode,
    probeAllNodes,
    setSearchQuery,
    setTagFilter,
    setIsAddModalOpen,
    getFilteredNodes,
    getActiveNode,
  } = useGatewayNodeStore();

  const activeNode = getActiveNode();
  const nodes = getFilteredNodes();

  const renderStatusBadge = (status: GatewayNodeStatus): React.ReactElement => {
    if (status === 'healthy') {
      return (
        <span className="inline-flex items-center gap-1 rounded bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-400">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
          <span>健康在线</span>
        </span>
      );
    }
    if (status === 'degraded') {
      return (
        <span className="inline-flex items-center gap-1 rounded bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium text-amber-400">
          <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
          <span>延迟偏高</span>
        </span>
      );
    }
    if (status === 'checking') {
      return (
        <span className="inline-flex items-center gap-1 rounded bg-indigo-500/10 px-2 py-0.5 text-[10px] text-indigo-400">
          <RefreshCw className="h-2.5 w-2.5 animate-spin" />
          <span>探活中</span>
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 rounded bg-rose-500/10 px-2 py-0.5 text-[10px] font-medium text-rose-400">
        <span className="h-1.5 w-1.5 rounded-full bg-rose-400" />
        <span>无法连通</span>
      </span>
    );
  };

  return (
    <div
      data-testid="gateway-node-switcher-card"
      className={`flex flex-col gap-4 rounded-xl border border-neutral-800 bg-neutral-950 p-5 text-neutral-100 ${className}`}
    >
      {/* 头部：当前主连节点胶囊与全局探活 */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-neutral-800/80 pb-3.5">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-indigo-500/30 bg-indigo-950/40 text-indigo-400">
            <Server className="h-4 w-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-neutral-100">多宿主网关集群调度</h3>
              {activeNode && (
                <span
                  data-testid="current-active-badge"
                  className="inline-flex items-center gap-1 rounded bg-indigo-500/20 px-2 py-0.5 text-[10px] font-medium text-indigo-300"
                >
                  <ShieldCheck className="h-3 w-3" />
                  <span>主连: {activeNode.name}</span>
                </span>
              )}
            </div>
            <p className="text-xs text-neutral-400">
              单标签页平滑热切换本地机器、机房 GPU VPS 与家用 NAS
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => {
              void probeAllNodes();
            }}
            data-testid="probe-all-btn"
            className="flex items-center gap-1 rounded-lg border border-neutral-800 bg-neutral-900 px-2.5 py-1.5 text-xs text-neutral-400 hover:text-neutral-200"
            title="对集群全量节点进行心跳与 RTT 探测"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            <span>全量探活</span>
          </button>
          <button
            type="button"
            onClick={() => {
              setIsAddModalOpen(true);
            }}
            data-testid="open-add-modal-btn"
            className="flex items-center gap-1 rounded-lg bg-indigo-600 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-indigo-500"
          >
            <Plus className="h-3.5 w-3.5" />
            <span>添加宿主节点</span>
          </button>
        </div>
      </div>

      {/* 搜索与过滤栏 */}
      <div className="flex flex-wrap items-center justify-between gap-2.5">
        <div className="relative flex-1 min-w-[200px]">
          <label htmlFor="gateway-search-input" className="sr-only">
            按节点名称、IP 端口或标签筛选
          </label>
          <input
            id="gateway-search-input"
            type="text"
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
            }}
            placeholder="搜索节点名称、URL 或环境标签..."
            className="w-full rounded-md border border-neutral-800 bg-neutral-900 py-1.5 pl-3 pr-3 text-xs text-neutral-200 placeholder-neutral-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>

        <div className="flex items-center gap-1.5 text-xs">
          {['all', '本地', 'GPU 算力', 'NAS'].map((tag) => (
            <button
              key={tag}
              type="button"
              onClick={() => {
                setTagFilter(tag);
              }}
              data-testid={`tag-filter-${tag}`}
              className={`rounded px-2 py-1 text-xs transition-colors ${
                tagFilter === tag
                  ? 'bg-indigo-950 font-medium text-indigo-300 ring-1 ring-indigo-500/50'
                  : 'bg-neutral-900 text-neutral-400 hover:bg-neutral-800'
              }`}
            >
              {tag === 'all' ? '全部' : tag}
            </button>
          ))}
        </div>
      </div>

      {/* 节点名册网格 */}
      <div className="flex flex-col gap-2.5">
        {nodes.map((node) => {
          const isActive = node.id === activeNodeId;
          return (
            <div
              key={node.id}
              data-testid={`gateway-node-card-${node.id}`}
              className={`flex flex-col rounded-lg border p-3.5 text-xs transition-colors ${
                isActive
                  ? 'border-indigo-500/50 bg-indigo-950/20'
                  : 'border-neutral-800 bg-neutral-900/50 hover:border-neutral-700'
              }`}
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-neutral-200">{node.name}</span>
                  {renderStatusBadge(node.status)}
                  {node.isDefault && (
                    <span className="rounded bg-neutral-800 px-1.5 py-0.5 text-[10px] text-neutral-400">
                      默认
                    </span>
                  )}
                  {node.tags.map((t) => (
                    <span
                      key={t}
                      className="rounded bg-neutral-800/80 px-1.5 py-0.5 text-[10px] text-neutral-400"
                    >
                      {t}
                    </span>
                  ))}
                </div>

                <div className="flex items-center gap-2">
                  <div className="flex items-center gap-1 font-mono text-[11px] text-neutral-400">
                    <Wifi className="h-3 w-3 text-neutral-500" />
                    <span>{node.pingMs}ms</span>
                  </div>

                  <button
                    type="button"
                    onClick={() => {
                      void probeNode(node.id);
                    }}
                    data-testid={`probe-btn-${node.id}`}
                    className="rounded p-1 text-neutral-400 hover:bg-neutral-800 hover:text-neutral-200"
                    title="立即探测当前节点网络 RTT"
                  >
                    <RefreshCw className="h-3 w-3" />
                  </button>

                  {!isActive ? (
                    <button
                      type="button"
                      onClick={() => {
                        switchActiveNode(node.id);
                      }}
                      data-testid={`switch-node-btn-${node.id}`}
                      className="rounded border border-indigo-500/40 bg-indigo-950/40 px-2 py-1 text-xs text-indigo-300 hover:bg-indigo-900/50"
                    >
                      设为主节点
                    </button>
                  ) : (
                    <span className="flex items-center gap-1 rounded bg-indigo-500/20 px-2 py-1 text-xs font-medium text-indigo-300">
                      <Check className="h-3 w-3" />
                      当前活跃
                    </span>
                  )}

                  {!node.isDefault && (
                    <button
                      type="button"
                      onClick={() => {
                        deleteNode(node.id);
                      }}
                      data-testid={`delete-node-btn-${node.id}`}
                      className="rounded p-1 text-neutral-500 hover:bg-neutral-800 hover:text-rose-400"
                      title="移除该节点"
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  )}
                </div>
              </div>

              {/* 地址与硬件信息 */}
              <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-neutral-400">
                <div className="flex items-center gap-1.5 font-mono text-[11px]">
                  <Globe className="h-3 w-3 text-neutral-500" />
                  <span>{node.endpointUrl}</span>
                </div>

                {node.hardwareInfo && (
                  <div className="flex items-center gap-3 text-[11px] text-neutral-400 font-mono">
                    {node.hardwareInfo.gpu && (
                      <span className="flex items-center gap-1">
                        <Activity className="h-3 w-3 text-indigo-400" />
                        {node.hardwareInfo.gpu}
                      </span>
                    )}
                    {node.hardwareInfo.ramGb && (
                      <span className="flex items-center gap-1">
                        <HardDrive className="h-3 w-3 text-emerald-400" />
                        {node.hardwareInfo.ramGb}GB RAM
                      </span>
                    )}
                    {node.hardwareInfo.cpuCores && (
                      <span className="flex items-center gap-1">
                        <Cpu className="h-3 w-3 text-amber-400" />
                        {node.hardwareInfo.cpuCores} Cores
                      </span>
                    )}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* 新增节点模态弹窗组件 */}
      <GatewayAddNodeModal
        isOpen={isAddModalOpen}
        onClose={() => {
          setIsAddModalOpen(false);
        }}
        onAddNode={(nodeData) => {
          addNode(nodeData);
        }}
      />
    </div>
  );
};
