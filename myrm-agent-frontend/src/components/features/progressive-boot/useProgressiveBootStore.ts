import { create } from 'zustand';
import type {
  DisclosureTier,
  ProgressiveBootState,
  SilencedNotice,
  SilentServiceItem,
} from './progressiveBootTypes';

const INITIAL_SERVICES: SilentServiceItem[] = [
  {
    id: 'srv_model_gateway',
    name: '智能路由网关',
    category: 'model_gateway',
    isReady: true,
    latencyMs: 18,
    description: '毫秒级自动匹配最优模型与多模型 Fallback 保底链路',
  },
  {
    id: 'srv_sandbox',
    name: '安全沙箱容器',
    category: 'sandbox',
    isReady: true,
    latencyMs: 32,
    description: '受限虚拟工作区与执行进程生命周期管理',
  },
  {
    id: 'srv_skill_mesh',
    name: '技能工具网格',
    category: 'skill_mesh',
    isReady: true,
    latencyMs: 12,
    description: '内置核心技能与动态按需加载能力',
  },
  {
    id: 'srv_mcp_bridge',
    name: '标准 MCP 桥接器',
    category: 'mcp_bridge',
    isReady: true,
    latencyMs: 25,
    description: '外部系统、数据库与三方 API 标准协议互通通道',
  },
  {
    id: 'srv_vector_memory',
    name: '分层持久记忆',
    category: 'vector_memory',
    isReady: true,
    latencyMs: 15,
    description: '会话上下文摘要与分层经验混合向量检索引擎',
  },
];

export const useProgressiveBootStore = create<ProgressiveBootState>((set, get) => ({
  tier: 'minimal',
  isDrawerOpen: false,
  services: INITIAL_SERVICES,
  silencedNotices: [],
  bootCompletedAt: new Date().toISOString(),

  setDisclosureTier: (tier: DisclosureTier) => {
    set({ tier });
  },

  toggleDrawer: (open?: boolean) => {
    set((state) => ({
      isDrawerOpen: open !== undefined ? open : !state.isDrawerOpen,
    }));
  },

  suppressBlockingModal: (notice: Omit<SilencedNotice, 'id' | 'timestamp'>): string => {
    const id = `notice_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
    const newNotice: SilencedNotice = {
      ...notice,
      id,
      timestamp: new Date().toISOString(),
    };

    set((state) => ({
      silencedNotices: [newNotice, ...state.silencedNotices],
    }));

    return id;
  },

  dismissNotice: (id: string) => {
    set((state) => ({
      silencedNotices: state.silencedNotices.filter((n) => n.id !== id),
    }));
  },

  updateServiceStatus: (serviceId: string, isReady: boolean, latencyMs: number) => {
    set((state) => ({
      services: state.services.map((srv) => {
        if (srv.id === serviceId) {
          return { ...srv, isReady, latencyMs };
        }
        return srv;
      }),
    }));
  },

  resetBootState: () => {
    set({
      tier: 'minimal',
      isDrawerOpen: false,
      services: INITIAL_SERVICES,
      silencedNotices: [],
      bootCompletedAt: new Date().toISOString(),
    });
  },
}));
