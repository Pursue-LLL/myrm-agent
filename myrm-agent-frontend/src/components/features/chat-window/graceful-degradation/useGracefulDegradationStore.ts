import { create } from 'zustand';
import {
  ComponentHealthRecord,
  DegradationEvent,
} from './gracefulDegradationTypes';

interface GracefulDegradationState {
  components: Record<string, ComponentHealthRecord>;
  activeDegradations: Record<string, DegradationEvent>;
  isHealthIndicatorModalOpen: boolean;

  registerOrUpdateComponent: (record: ComponentHealthRecord) => void;
  triggerDegradation: (event: DegradationEvent) => void;
  resolveDegradation: (eventId: string) => void;
  toggleHealthModal: (open?: boolean) => void;
  reset: () => void;
}

const INITIAL_MOCK_COMPONENTS: Record<string, ComponentHealthRecord> = {
  'comp-main-model': {
    id: 'comp-main-model',
    name: '主认知推理模型 (Claude / GPT)',
    type: 'model',
    status: 'closed',
    latencyMs: 380,
    errorRatePercent: 0.1,
    lastCheckedAt: Date.now() - 5000,
    fallbackStrategy: '多供应商自动轮换（Secondary Provider Failover）',
  },
  'comp-web-search': {
    id: 'comp-web-search',
    name: '联网实时检索与抓取集群',
    type: 'search',
    status: 'half_open',
    latencyMs: 1420,
    errorRatePercent: 8.5,
    lastCheckedAt: Date.now() - 3000,
    failureReason: '上游搜索代理出现偶发 503 频率限制',
    fallbackStrategy: '自动切入本地向量记忆与模型原生先验知识（Zero-Block Fallback）',
  },
  'comp-code-sandbox': {
    id: 'comp-code-sandbox',
    name: '轻量隔离代码执行沙箱 (Wasm/Container)',
    type: 'sandbox',
    status: 'closed',
    latencyMs: 120,
    errorRatePercent: 0,
    lastCheckedAt: Date.now() - 8000,
    fallbackStrategy: '降级为只读静态语法/AST 分析模式',
  },
  'comp-knowledge-vector': {
    id: 'comp-knowledge-vector',
    name: '项目知识库与多维向量索引',
    type: 'knowledge_base',
    status: 'closed',
    latencyMs: 65,
    errorRatePercent: 0,
    lastCheckedAt: Date.now() - 10000,
    fallbackStrategy: '内存快速全文倒排搜索',
  },
};

const INITIAL_MOCK_DEGRADATIONS: Record<string, DegradationEvent> = {
  'deg-search-01': {
    id: 'deg-search-01',
    componentId: 'comp-web-search',
    componentName: '联网实时检索集群',
    severity: 'warning',
    title: '检索网络抖动熔断',
    explanation:
      '上游检索节点响应时延超过 3500ms 阈值，已触发断路器半开保护。回答已平滑切换至本地知识库与模型自有先验事实，避免界面白屏死等。',
    fallbackActive: true,
    fallbackActionLabel: '已无缝采用知识库降级策略',
    recoveryEtaSec: 45,
    timestamp: Date.now() - 15000,
  },
};

export const useGracefulDegradationStore = create<GracefulDegradationState>(
  (set) => ({
    components: INITIAL_MOCK_COMPONENTS,
    activeDegradations: INITIAL_MOCK_DEGRADATIONS,
    isHealthIndicatorModalOpen: false,

    registerOrUpdateComponent: (record: ComponentHealthRecord): void => {
      set((state) => ({
        components: {
          ...state.components,
          [record.id]: record,
        },
      }));
    },

    triggerDegradation: (event: DegradationEvent): void => {
      set((state) => ({
        activeDegradations: {
          ...state.activeDegradations,
          [event.id]: event,
        },
      }));
    },

    resolveDegradation: (eventId: string): void => {
      set((state) => {
        const next = { ...state.activeDegradations };
        delete next[eventId];
        return { activeDegradations: next };
      });
    },

    toggleHealthModal: (open?: boolean): void => {
      set((state) => ({
        isHealthIndicatorModalOpen:
          open !== undefined ? open : !state.isHealthIndicatorModalOpen,
      }));
    },

    reset: (): void => {
      set({
        components: {},
        activeDegradations: {},
        isHealthIndicatorModalOpen: false,
      });
    },
  }),
);
