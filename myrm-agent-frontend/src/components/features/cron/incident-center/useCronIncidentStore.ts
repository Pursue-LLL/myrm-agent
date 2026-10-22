/**
 * Cron Incident Center Zustand Store
 * 全局定时任务事故待办中心状态机与一键 Ack 签收调度
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any；
 * 2. 所有 if 显式包裹大括号；
 * 3. 行数严格受控在 400 行以内。
 */

import { create } from 'zustand';
import {
  ArtifactAcceptanceCriteria,
  CronIncident,
  IncidentCategory,
  IncidentMetrics,
  TaskExecutionRun,
} from './cronIncidentTypes';
import {
  classifyExecutionRun,
  computeIncidentMetrics,
} from './silentFailureBarrierEngine';

interface CronIncidentStoreState {
  incidents: CronIncident[];
  isDrawerOpen: boolean;
  selectedIncidentId: string | null;
  filterCategory: IncidentCategory | 'all';
  onlyUnacknowledged: boolean;
  searchQuery: string;

  // Actions
  setIsDrawerOpen: (open: boolean) => void;
  setSelectedIncidentId: (id: string | null) => void;
  setFilterCategory: (category: IncidentCategory | 'all') => void;
  setOnlyUnacknowledged: (only: boolean) => void;
  setSearchQuery: (query: string) => void;
  acknowledgeIncident: (id: string) => void;
  acknowledgeAll: (ids?: string[]) => void;
  retryIncidentRun: (id: string) => void;
  recordExecutionRun: (run: TaskExecutionRun, criteria?: ArtifactAcceptanceCriteria) => { passed: boolean; incident?: CronIncident };
  resetToDefault: () => void;
  getMetrics: () => IncidentMetrics;
  getFilteredIncidents: () => CronIncident[];
}

export const INITIAL_DEMO_INCIDENTS: CronIncident[] = [
  {
    id: 'inc-demo-silent-01',
    jobId: 'job-morning-finance-sync',
    jobName: '晨间财务报表同步任务',
    runId: 'run-8921-a',
    category: 'silent_failure',
    severity: 'critical',
    occurredAt: new Date(Date.now() - 1000 * 60 * 25).toISOString(),
    exitCode: 0,
    summary: '进程返回 exit 0 假成功，但未产出实质交付物',
    failureReason: '缺失预期交付物文件: daily_finance_report.csv; 产物总字节数 (0 B) 低于验收基准 (1024 B)',
    verificationDetails: {
      passed: false,
      isSilentFailure: true,
      reasons: [
        '缺失预期交付物文件: daily_finance_report.csv',
        '产物总字节数 (0 B) 低于验收基准 (1024 B) 且 stdout 为空',
      ],
      missingArtifacts: ['daily_finance_report.csv'],
      missingKeywords: [],
      actualBytes: 0,
    },
    acknowledged: false,
    retryCount: 0,
  },
  {
    id: 'inc-demo-quota-02',
    jobId: 'job-vector-index-rebuild',
    jobName: '知识库向量索引增量重建',
    runId: 'run-8920-b',
    category: 'quota_exhausted',
    severity: 'warning',
    occurredAt: new Date(Date.now() - 1000 * 60 * 90).toISOString(),
    exitCode: 1,
    summary: '模型或上游 API 配额超限 (429 Rate Limit)',
    failureReason: 'HTTP 429 Too Many Requests: TPM rate limit exceeded for embedding model',
    acknowledged: false,
    retryCount: 1,
  },
  {
    id: 'inc-demo-auth-03',
    jobId: 'job-github-release-watcher',
    jobName: '开源版本发布订阅检查',
    runId: 'run-8919-c',
    category: 'auth_expired',
    severity: 'critical',
    occurredAt: new Date(Date.now() - 1000 * 60 * 180).toISOString(),
    exitCode: 2,
    summary: '调用凭证失效或鉴权失败 (401 Unauthorized)',
    failureReason: 'Bad credentials: The personal access token has expired',
    acknowledged: true,
    acknowledgedAt: new Date(Date.now() - 1000 * 60 * 120).toISOString(),
    retryCount: 0,
  },
];

export const useCronIncidentStore = create<CronIncidentStoreState>((set, get) => ({
  incidents: INITIAL_DEMO_INCIDENTS,
  isDrawerOpen: false,
  selectedIncidentId: null,
  filterCategory: 'all',
  onlyUnacknowledged: true,
  searchQuery: '',

  setIsDrawerOpen: (open: boolean) => {
    set({ isDrawerOpen: open });
  },

  setSelectedIncidentId: (id: string | null) => {
    set({ selectedIncidentId: id });
  },

  setFilterCategory: (category: IncidentCategory | 'all') => {
    set({ filterCategory: category });
  },

  setOnlyUnacknowledged: (only: boolean) => {
    set({ onlyUnacknowledged: only });
  },

  setSearchQuery: (query: string) => {
    set({ searchQuery: query });
  },

  acknowledgeIncident: (id: string) => {
    set((state) => ({
      incidents: state.incidents.map((item) => {
        if (item.id === id) {
          return {
            ...item,
            acknowledged: true,
            acknowledgedAt: new Date().toISOString(),
          };
        }
        return item;
      }),
    }));
  },

  acknowledgeAll: (ids?: string[]) => {
    const timestamp = new Date().toISOString();
    set((state) => ({
      incidents: state.incidents.map((item) => {
        if (!ids || ids.includes(item.id)) {
          return {
            ...item,
            acknowledged: true,
            acknowledgedAt: timestamp,
          };
        }
        return item;
      }),
    }));
  },

  retryIncidentRun: (id: string) => {
    set((state) => ({
      incidents: state.incidents.map((item) => {
        if (item.id === id) {
          return {
            ...item,
            retryCount: item.retryCount + 1,
          };
        }
        return item;
      }),
    }));
  },

  recordExecutionRun: (run: TaskExecutionRun, criteria?: ArtifactAcceptanceCriteria) => {
    const result = classifyExecutionRun(run, criteria);
    if (!result.passed && result.incident) {
      const newIncident = result.incident;
      set((state) => ({
        incidents: [newIncident, ...state.incidents],
      }));
    }
    return result;
  },

  resetToDefault: () => {
    set({
      incidents: JSON.parse(JSON.stringify(INITIAL_DEMO_INCIDENTS)) as CronIncident[],
      isDrawerOpen: false,
      selectedIncidentId: null,
      filterCategory: 'all',
      onlyUnacknowledged: true,
      searchQuery: '',
    });
  },

  getMetrics: () => {
    return computeIncidentMetrics(get().incidents);
  },

  getFilteredIncidents: () => {
    const state = get();
    return state.incidents.filter((item) => {
      if (state.onlyUnacknowledged && item.acknowledged) {
        return false;
      }
      if (state.filterCategory !== 'all' && item.category !== state.filterCategory) {
        return false;
      }
      if (state.searchQuery.trim().length > 0) {
        const query = state.searchQuery.toLowerCase();
        const matchesName = item.jobName.toLowerCase().includes(query);
        const matchesSummary = item.summary.toLowerCase().includes(query);
        const matchesReason = item.failureReason.toLowerCase().includes(query);
        if (!matchesName && !matchesSummary && !matchesReason) {
          return false;
        }
      }
      return true;
    });
  },
}));
