/**
 * Multi-Node Gateway Switcher Zustand Store
 * 多宿主 Agent 网关节点注册表与平滑热切换状态调度
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 所有 if 显式包裹大括号；
 * 3. 行数严格受控在 400 行以内。
 */

import { create } from 'zustand';
import {
  filterAndSortNodes,
  normalizeEndpointUrl,
  probeGatewayNode,
} from './gatewayHealthProbe';
import {
  GatewayNodeDescriptor,
  GatewaySwitchEventDetail,
} from './gatewayNodeTypes';

interface GatewayNodeStoreState {
  nodes: GatewayNodeDescriptor[];
  activeNodeId: string;
  searchQuery: string;
  tagFilter: string;
  isAddModalOpen: boolean;
  isSwitching: boolean;

  // Actions
  switchActiveNode: (nodeId: string) => void;
  addNode: (node: Omit<GatewayNodeDescriptor, 'id' | 'status' | 'pingMs' | 'lastCheckedAt'>) => string;
  updateNode: (id: string, updates: Partial<GatewayNodeDescriptor>) => void;
  deleteNode: (id: string) => void;
  probeNode: (id: string) => Promise<void>;
  probeAllNodes: () => Promise<void>;
  setSearchQuery: (query: string) => void;
  setTagFilter: (tag: string) => void;
  setIsAddModalOpen: (open: boolean) => void;
  getFilteredNodes: () => GatewayNodeDescriptor[];
  getActiveNode: () => GatewayNodeDescriptor | undefined;
  resetToDefault: () => void;
}

const INITIAL_NODES: GatewayNodeDescriptor[] = [
  {
    id: 'node-localhost-01',
    name: '本地开发主力机 (Localhost)',
    endpointUrl: 'http://localhost:8000',
    isDefault: true,
    pingMs: 4,
    status: 'healthy',
    tags: ['本地', '开发环境'],
    hardwareInfo: {
      gpu: 'Apple M3 Max (36-core)',
      ramGb: 64,
      cpuCores: 16,
      osPlatform: 'macOS 15.2',
    },
    lastCheckedAt: new Date().toISOString(),
  },
  {
    id: 'node-gpu-vps-02',
    name: '机房远程 GPU 算力节点',
    endpointUrl: 'https://vps-gpu.corp.myrm.internal:8443',
    token: 'myrm_vps_token_sec_9821',
    isDefault: false,
    pingMs: 42,
    status: 'healthy',
    tags: ['GPU 算力', '远程 VPS'],
    hardwareInfo: {
      gpu: 'NVIDIA RTX 4090 (24GB)',
      ramGb: 128,
      cpuCores: 32,
      osPlatform: 'Ubuntu 24.04 LTS',
    },
    lastCheckedAt: new Date(Date.now() - 1000 * 60 * 2).toISOString(),
  },
  {
    id: 'node-home-nas-03',
    name: '家用 NAS 私有云网关',
    endpointUrl: 'http://192.168.31.200:8000',
    isDefault: false,
    pingMs: 18,
    status: 'degraded',
    tags: ['NAS', '局域网'],
    hardwareInfo: {
      gpu: 'Intel UHD 770',
      ramGb: 32,
      cpuCores: 8,
      osPlatform: 'TrueNAS SCALE',
    },
    lastCheckedAt: new Date(Date.now() - 1000 * 60 * 10).toISOString(),
  },
];

export const useGatewayNodeStore = create<GatewayNodeStoreState>((set, get) => ({
  nodes: INITIAL_NODES,
  activeNodeId: 'node-localhost-01',
  searchQuery: '',
  tagFilter: 'all',
  isAddModalOpen: false,
  isSwitching: false,

  switchActiveNode: (nodeId: string) => {
    const previousNodeId = get().activeNodeId;
    if (previousNodeId === nodeId) {
      return;
    }

    const targetNode = get().nodes.find((n) => n.id === nodeId);
    if (!targetNode) {
      return;
    }

    set({ isSwitching: true });

    // 触发标准 window 事件广播
    if (typeof window !== 'undefined') {
      const detail: GatewaySwitchEventDetail = {
        previousNodeId,
        currentNodeId: nodeId,
        endpointUrl: targetNode.endpointUrl,
      };
      window.dispatchEvent(
        new CustomEvent<GatewaySwitchEventDetail>('myrm:gateway-node-switched', {
          detail,
        })
      );
    }

    set({
      activeNodeId: nodeId,
      isSwitching: false,
    });
  },

  addNode: (nodeData) => {
    const id = `node-${Date.now().toString(36)}`;
    const newNode: GatewayNodeDescriptor = {
      ...nodeData,
      id,
      endpointUrl: normalizeEndpointUrl(nodeData.endpointUrl),
      status: 'checking',
      pingMs: 0,
      lastCheckedAt: new Date().toISOString(),
    };

    set((state) => ({
      nodes: [...state.nodes, newNode],
      isAddModalOpen: false,
    }));

    void get().probeNode(id);
    return id;
  },

  updateNode: (id: string, updates: Partial<GatewayNodeDescriptor>) => {
    set((state) => ({
      nodes: state.nodes.map((node) => {
        if (node.id === id) {
          return {
            ...node,
            ...updates,
            endpointUrl: updates.endpointUrl
              ? normalizeEndpointUrl(updates.endpointUrl)
              : node.endpointUrl,
          };
        }
        return node;
      }),
    }));
  },

  deleteNode: (id: string) => {
    set((state) => {
      const remaining = state.nodes.filter((n) => n.id !== id);
      const nextActiveId =
        state.activeNodeId === id
          ? remaining.length > 0
            ? remaining[0].id
            : ''
          : state.activeNodeId;

      return {
        nodes: remaining,
        activeNodeId: nextActiveId,
      };
    });
  },

  probeNode: async (id: string) => {
    const targetNode = get().nodes.find((n) => n.id === id);
    if (!targetNode) {
      return;
    }

    set((state) => ({
      nodes: state.nodes.map((n) => {
        if (n.id === id) {
          return { ...n, status: 'checking' };
        }
        return n;
      }),
    }));

    const result = await probeGatewayNode(targetNode);

    set((state) => ({
      nodes: state.nodes.map((n) => {
        if (n.id === id) {
          return {
            ...n,
            status: result.status,
            pingMs: result.pingMs,
            lastCheckedAt: new Date().toISOString(),
          };
        }
        return n;
      }),
    }));
  },

  probeAllNodes: async () => {
    const nodeIds = get().nodes.map((n) => n.id);
    await Promise.all(nodeIds.map((id) => get().probeNode(id)));
  },

  setSearchQuery: (query: string) => {
    set({ searchQuery: query });
  },

  setTagFilter: (tag: string) => {
    set({ tagFilter: tag });
  },

  setIsAddModalOpen: (open: boolean) => {
    set({ isAddModalOpen: open });
  },

  getFilteredNodes: () => {
    const state = get();
    return filterAndSortNodes(state.nodes, state.searchQuery, state.tagFilter);
  },

  getActiveNode: () => {
    const state = get();
    return state.nodes.find((n) => n.id === state.activeNodeId) || state.nodes[0];
  },

  resetToDefault: () => {
    set({
      nodes: JSON.parse(JSON.stringify(INITIAL_NODES)) as GatewayNodeDescriptor[],
      activeNodeId: 'node-localhost-01',
      searchQuery: '',
      tagFilter: 'all',
      isAddModalOpen: false,
      isSwitching: false,
    });
  },
}));
