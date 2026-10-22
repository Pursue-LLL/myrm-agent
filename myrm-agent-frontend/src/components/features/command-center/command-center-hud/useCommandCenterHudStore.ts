'use client';

import { create } from 'zustand';
import {
  DiagnosticCheckItem,
  GatewayHealthStatus,
  PinnedWorkstream,
  TimeRangeKey,
  UsageSpendSummary,
} from './commandCenterTypes';
import {
  generateConfigBackupPayload,
  remediateDiagnosticIssue,
  runSystemDoctorDiagnostic,
} from './commandCenterEngine';

export interface CommandCenterHudState {
  isOpen: boolean;
  searchQuery: string;
  selectedTimeRange: TimeRangeKey;
  gatewayHealth: GatewayHealthStatus;
  diagnosticChecks: DiagnosticCheckItem[];
  isRunningDoctor: boolean;
  pinnedWorkstreams: PinnedWorkstream[];
  spendSummaries: Record<TimeRangeKey, UsageSpendSummary>;
  lastBackupPayload: string | null;

  openHud: () => void;
  closeHud: () => void;
  toggleHud: () => void;
  setSearchQuery: (query: string) => void;
  setSelectedTimeRange: (range: TimeRangeKey) => void;
  togglePinWorkstream: (id: string) => void;
  runDoctor: () => void;
  remediateIssue: (id: string) => void;
  backupConfig: () => string;
  reset: () => void;
}

const INITIAL_CHECKS: DiagnosticCheckItem[] = [
  {
    id: 'chk-gateway',
    category: 'gateway',
    name: '多协议实时通信网关 (Gateway)',
    status: 'pass',
    detail: 'HTTP/SSE 与 WebSocket 双工通道正常，RTT 14ms',
    remediable: false,
  },
  {
    id: 'chk-sandbox',
    category: 'sandbox',
    name: '代码执行安全沙箱 (Docker/PTY)',
    status: 'warning',
    detail: '临时沙箱文件快照累计超过 500MB，建议执行缓存修剪',
    remediable: true,
  },
  {
    id: 'chk-storage',
    category: 'storage',
    name: '持久化会话与向量索引库 (Storage)',
    status: 'pass',
    detail: 'SQLite WAL 模式与 sqlite-vec 扩展就绪，事务零延迟',
    remediable: false,
  },
  {
    id: 'chk-security',
    category: 'security',
    name: '高危工具调用白名单守卫 (Security)',
    status: 'pass',
    detail: '文件写入与终端执行已绑定二次交互确认防护闸门',
    remediable: false,
  },
];

const INITIAL_WORKSTREAMS: PinnedWorkstream[] = [
  {
    id: 'ws-1',
    title: '全栈电商营销活动 UI 原型设计',
    lastActive: '5分钟前',
    category: 'workflow',
    isPinned: true,
  },
  {
    id: 'ws-2',
    title: '生产环境网关长任务并发调度排障',
    lastActive: '32分钟前',
    category: 'chat',
    isPinned: true,
  },
  {
    id: 'ws-3',
    title: 'Hermes 协议跨进程 RPC 适配方案',
    lastActive: '2小时前',
    category: 'artifact',
    isPinned: false,
  },
  {
    id: 'ws-4',
    title: '团队算力配额与多模型费率审计大盘',
    lastActive: '昨天',
    category: 'workflow',
    isPinned: false,
  },
];

const INITIAL_SPEND_SUMMARIES: Record<TimeRangeKey, UsageSpendSummary> = {
  '7d': {
    period: '7d',
    totalTokens: 1420000,
    estimatedCostUsd: 2.48,
    dailyTrend: [
      { day: '周一', tokens: 180000, cost: 0.31 },
      { day: '周二', tokens: 210000, cost: 0.36 },
      { day: '周三', tokens: 260000, cost: 0.45 },
      { day: '周四', tokens: 190000, cost: 0.33 },
      { day: '周五', tokens: 320000, cost: 0.56 },
      { day: '周六', tokens: 140000, cost: 0.24 },
      { day: '周日', tokens: 120000, cost: 0.23 },
    ],
    topModels: [
      { modelId: 'claude-3-7-sonnet', name: 'Claude 3.7 Sonnet', tokens: 920000, percentage: 65 },
      { modelId: 'deepseek-v3', name: 'DeepSeek V3', tokens: 380000, percentage: 27 },
      { modelId: 'gpt-4o', name: 'GPT-4o', tokens: 120000, percentage: 8 },
    ],
    topSkills: [
      { skillId: 'canvas-designer', name: '无限画布设计套件', invocationCount: 68 },
      { skillId: 'code-review', name: '代码质量巡检门禁', invocationCount: 42 },
      { skillId: 'web-search', name: '实时网络检索', invocationCount: 29 },
    ],
  },
  '30d': {
    period: '30d',
    totalTokens: 6850000,
    estimatedCostUsd: 11.95,
    dailyTrend: [
      { day: '第1周', tokens: 1500000, cost: 2.62 },
      { day: '第2周', tokens: 1820000, cost: 3.18 },
      { day: '第3周', tokens: 1780000, cost: 3.11 },
      { day: '第4周', tokens: 1750000, cost: 3.04 },
    ],
    topModels: [
      { modelId: 'claude-3-7-sonnet', name: 'Claude 3.7 Sonnet', tokens: 4450000, percentage: 65 },
      { modelId: 'deepseek-v3', name: 'DeepSeek V3', tokens: 1920000, percentage: 28 },
      { modelId: 'gpt-4o', name: 'GPT-4o', tokens: 480000, percentage: 7 },
    ],
    topSkills: [
      { skillId: 'canvas-designer', name: '无限画布设计套件', invocationCount: 284 },
      { skillId: 'code-review', name: '代码质量巡检门禁', invocationCount: 165 },
      { skillId: 'web-search', name: '实时网络检索', invocationCount: 118 },
    ],
  },
  '90d': {
    period: '90d',
    totalTokens: 19800000,
    estimatedCostUsd: 34.65,
    dailyTrend: [
      { day: '第1月', tokens: 6200000, cost: 10.85 },
      { day: '第2月', tokens: 6750000, cost: 11.81 },
      { day: '第3月', tokens: 6850000, cost: 11.99 },
    ],
    topModels: [
      { modelId: 'claude-3-7-sonnet', name: 'Claude 3.7 Sonnet', tokens: 12870000, percentage: 65 },
      { modelId: 'deepseek-v3', name: 'DeepSeek V3', tokens: 5540000, percentage: 28 },
      { modelId: 'gpt-4o', name: 'GPT-4o', tokens: 1390000, percentage: 7 },
    ],
    topSkills: [
      { skillId: 'canvas-designer', name: '无限画布设计套件', invocationCount: 812 },
      { skillId: 'code-review', name: '代码质量巡检门禁', invocationCount: 490 },
      { skillId: 'web-search', name: '实时网络检索', invocationCount: 326 },
    ],
  },
};

export const useCommandCenterHudStore = create<CommandCenterHudState>((set, get) => ({
  isOpen: false,
  searchQuery: '',
  selectedTimeRange: '7d',
  gatewayHealth: 'healthy',
  diagnosticChecks: INITIAL_CHECKS,
  isRunningDoctor: false,
  pinnedWorkstreams: INITIAL_WORKSTREAMS,
  spendSummaries: INITIAL_SPEND_SUMMARIES,
  lastBackupPayload: null,

  openHud: () => {
    set({ isOpen: true });
  },

  closeHud: () => {
    set({ isOpen: false, searchQuery: '' });
  },

  toggleHud: () => {
    set((state) => ({ isOpen: !state.isOpen, searchQuery: '' }));
  },

  setSearchQuery: (query: string) => {
    set({ searchQuery: query });
  },

  setSelectedTimeRange: (range: TimeRangeKey) => {
    set({ selectedTimeRange: range });
  },

  togglePinWorkstream: (id: string) => {
    set((state) => ({
      pinnedWorkstreams: state.pinnedWorkstreams.map((w) =>
        w.id === id ? { ...w, isPinned: !w.isPinned } : w
      ),
    }));
  },

  runDoctor: () => {
    set({ isRunningDoctor: true });
    // 模拟运行诊断检测后更新
    const nextChecks = runSystemDoctorDiagnostic(get().diagnosticChecks);
    set({
      diagnosticChecks: nextChecks,
      isRunningDoctor: false,
      gatewayHealth: 'healthy',
    });
  },

  remediateIssue: (id: string) => {
    const { diagnosticChecks } = get();
    const updated = remediateDiagnosticIssue(diagnosticChecks, id);
    set({ diagnosticChecks: updated });
  },

  backupConfig: () => {
    const { pinnedWorkstreams, diagnosticChecks } = get();
    const payload = generateConfigBackupPayload(pinnedWorkstreams, diagnosticChecks);
    set({ lastBackupPayload: payload });
    return payload;
  },

  reset: () => {
    set({
      isOpen: false,
      searchQuery: '',
      selectedTimeRange: '7d',
      gatewayHealth: 'healthy',
      diagnosticChecks: INITIAL_CHECKS,
      isRunningDoctor: false,
      pinnedWorkstreams: INITIAL_WORKSTREAMS,
      spendSummaries: INITIAL_SPEND_SUMMARIES,
      lastBackupPayload: null,
    });
  },
}));
