/**
 * [INPUT] initialSuites, initialConnectors, initialJobs, onSelectSuite
 * [OUTPUT] UnifiedSpecialtyWorkplaceHub component unifying specialty suites, enterprise connectors,
 *          scheduled jobs and zero-config mobile companion pairing
 * [POS] specialty-suites-gateway/UnifiedSpecialtyWorkplaceHub.tsx
 */

'use client';

import React, { useState } from 'react';
import {
  Briefcase,
  Smartphone,
  CloudLightning,
  Clock,
  Layers,
  ChevronRight,
  ShieldCheck,
  CheckCircle2,
  Cpu,
  Laptop,
  Scale,
  DollarSign,
  BarChart3,
  Terminal,
  Activity,
} from 'lucide-react';
import type {
  SpecialtySuiteItem,
  EnterpriseConnector,
  ScheduledJobSummary,
  SpecialtyDomain,
} from './specialtyGatewayTypes';
import { ZeroConfigMobilePairingModal } from './ZeroConfigMobilePairingModal';

export interface UnifiedSpecialtyWorkplaceHubProps {
  suites?: SpecialtySuiteItem[];
  connectors?: EnterpriseConnector[];
  scheduledJobs?: ScheduledJobSummary[];
  onSelectSuite?: (suite: SpecialtySuiteItem) => void;
  className?: string;
}

const DOMAIN_ICON_MAP: Record<SpecialtyDomain, React.FC<{ className?: string }>> = {
  finance: DollarSign,
  legal: Scale,
  data: BarChart3,
  engineering: Terminal,
  operations: Activity,
};

const DEFAULT_SUITES: SpecialtySuiteItem[] = [
  {
    id: 'suite-finance',
    name: '财务与税务审计专家',
    domain: 'finance',
    description: '报表核算、预算监控与财报自动校核',
    iconName: 'DollarSign',
    status: 'active',
    skillsCount: 6,
  },
  {
    id: 'suite-legal',
    name: '法务合规风控专家',
    domain: 'legal',
    description: '合同条款审核、合规风险筛查与法条检索',
    iconName: 'Scale',
    status: 'idle',
    skillsCount: 5,
  },
  {
    id: 'suite-data',
    name: '商业数据智能专家',
    domain: 'data',
    description: '指标异动归因、看板自渲染与 SQL 调优',
    iconName: 'BarChart3',
    status: 'active',
    skillsCount: 8,
  },
  {
    id: 'suite-engineering',
    name: '全栈工程自进化专家',
    domain: 'engineering',
    description: '架构重构、代码审查与单测回归闭环',
    iconName: 'Terminal',
    status: 'active',
    skillsCount: 12,
  },
];

const DEFAULT_CONNECTORS: EnterpriseConnector[] = [
  {
    id: 'conn-feishu',
    channel: 'feishu',
    displayName: '飞书协作通道',
    isConnected: true,
    isCloudRelayEnabled: true,
    lastActiveTime: Date.now() - 1000 * 60 * 5,
  },
  {
    id: 'conn-wechat',
    channel: 'wechat_work',
    displayName: '企业微信工作台',
    isConnected: false,
    isCloudRelayEnabled: false,
  },
  {
    id: 'conn-dingtalk',
    channel: 'dingtalk',
    displayName: '钉钉群机器人',
    isConnected: true,
    isCloudRelayEnabled: true,
    lastActiveTime: Date.now() - 1000 * 60 * 30,
  },
];

const DEFAULT_SCHEDULED_JOBS: ScheduledJobSummary[] = [
  {
    id: 'job-1',
    title: '每日早报与代码库健康巡检',
    cronExpression: '0 8 * * *',
    executionTarget: 'cloud',
    nextRunTime: Date.now() + 1000 * 60 * 60 * 14,
    status: 'active',
  },
  {
    id: 'job-2',
    title: '本地开发沙箱构建缓存修剪',
    cronExpression: '0 23 * * 5',
    executionTarget: 'local_device',
    nextRunTime: Date.now() + 1000 * 60 * 60 * 48,
    status: 'active',
  },
];

export const UnifiedSpecialtyWorkplaceHub: React.FC<UnifiedSpecialtyWorkplaceHubProps> = ({
  suites = DEFAULT_SUITES,
  connectors = DEFAULT_CONNECTORS,
  scheduledJobs = DEFAULT_SCHEDULED_JOBS,
  onSelectSuite,
  className = '',
}) => {
  const [activeTab, setActiveTab] = useState<'suites' | 'connectors' | 'cron'>('suites');
  const [isPairingModalOpen, setIsPairingModalOpen] = useState<boolean>(false);

  return (
    <div
      data-testid="unified-specialty-workplace-hub"
      className={`flex flex-col rounded-xl border border-border/70 bg-card text-card-foreground shadow-sm overflow-hidden ${className}`}
    >
      {/* Header with Quick Mobile Companion Button */}
      <div className="flex items-center justify-between border-b px-4 py-3 bg-muted/20">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary border border-primary/20">
            <Briefcase className="h-4 w-4" />
          </div>
          <div>
            <h3 className="text-xs font-semibold text-foreground tracking-tight">
              数字员工专业套件工作台
            </h3>
            <p className="text-[10px] text-muted-foreground">
              统一专业套件 · 统一定时中心 · 免配置移动伴侣
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => {
            setIsPairingModalOpen(true);
          }}
          className="inline-flex items-center gap-1.5 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground px-2.5 py-1 text-xs font-medium shadow-xs transition-colors"
        >
          <Smartphone className="h-3.5 w-3.5" />
          <span>连接移动伴侣</span>
        </button>
      </div>

      {/* Navigation Tabs */}
      <div className="flex items-center border-b px-4 bg-muted/10 gap-4 text-xs font-medium">
        <button
          type="button"
          onClick={() => {
            setActiveTab('suites');
          }}
          className={`py-2.5 border-b-2 transition-all flex items-center gap-1.5 ${
            activeTab === 'suites'
              ? 'border-primary text-primary font-semibold'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          <Layers className="h-3.5 w-3.5" />
          <span>专家智能体 ({suites.length})</span>
        </button>

        <button
          type="button"
          onClick={() => {
            setActiveTab('connectors');
          }}
          className={`py-2.5 border-b-2 transition-all flex items-center gap-1.5 ${
            activeTab === 'connectors'
              ? 'border-primary text-primary font-semibold'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          <CloudLightning className="h-3.5 w-3.5" />
          <span>企业连接器 ({connectors.length})</span>
        </button>

        <button
          type="button"
          onClick={() => {
            setActiveTab('cron');
          }}
          className={`py-2.5 border-b-2 transition-all flex items-center gap-1.5 ${
            activeTab === 'cron'
              ? 'border-primary text-primary font-semibold'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          <Clock className="h-3.5 w-3.5" />
          <span>统一定时任务 ({scheduledJobs.length})</span>
        </button>
      </div>

      {/* Body Content */}
      <div className="p-4 overflow-y-auto max-h-[460px] space-y-2.5 text-xs">
        {/* Tab 1: Suites */}
        {activeTab === 'suites' && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
            {suites.map((suite) => {
              const IconComp = DOMAIN_ICON_MAP[suite.domain] || Cpu;
              return (
                <button
                  type="button"
                  key={suite.id}
                  onClick={() => {
                    if (onSelectSuite) {
                      onSelectSuite(suite);
                    }
                  }}
                  className="rounded-xl border border-border/60 bg-muted/20 hover:bg-muted/40 p-3 transition-all cursor-pointer flex flex-col justify-between space-y-2 text-left w-full"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary/10 text-primary shrink-0">
                        <IconComp className="h-4 w-4" />
                      </div>
                      <span className="font-semibold text-foreground text-xs leading-tight">
                        {suite.name}
                      </span>
                    </div>

                    <span
                      className={`rounded px-1.5 py-0.5 text-[10px] font-mono font-medium ${
                        suite.status === 'active'
                          ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                          : 'bg-muted text-muted-foreground'
                      }`}
                    >
                      {suite.status === 'active' ? '就绪中' : '待命'}
                    </span>
                  </div>

                  <p className="text-muted-foreground text-[11px] leading-relaxed line-clamp-2">
                    {suite.description}
                  </p>

                  <div className="flex items-center justify-between text-[11px] text-muted-foreground pt-1 border-t border-border/40">
                    <span>搭载技能：{suite.skillsCount} 个</span>
                    <ChevronRight className="h-3.5 w-3.5 opacity-60" />
                  </div>
                </button>
              );
            })}
          </div>
        )}

        {/* Tab 2: Connectors */}
        {activeTab === 'connectors' && (
          <div className="space-y-2">
            {connectors.map((conn) => {
              return (
                <div
                  key={conn.id}
                  className="flex items-center justify-between rounded-xl border border-border/60 bg-muted/20 p-3"
                >
                  <div className="flex items-center gap-2.5">
                    <div
                      className={`flex h-8 w-8 items-center justify-center rounded-lg border ${
                        conn.isConnected
                          ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20'
                          : 'bg-muted text-muted-foreground border-border/50'
                      }`}
                    >
                      <CloudLightning className="h-4 w-4" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-foreground text-xs">
                          {conn.displayName}
                        </span>
                        <span
                          className={`rounded px-1.5 py-0.2 text-[10px] ${
                            conn.isConnected
                              ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                              : 'bg-muted text-muted-foreground'
                          }`}
                        >
                          {conn.isConnected ? '已连接' : '未配置'}
                        </span>
                      </div>
                      <span className="text-[11px] text-muted-foreground">
                        云端中继状态：{conn.isCloudRelayEnabled ? '随走随用开启' : '未开启'}
                      </span>
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => {
                      setIsPairingModalOpen(true);
                    }}
                    className="rounded-lg border px-2.5 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                  >
                    配置 / 扫码
                  </button>
                </div>
              );
            })}
          </div>
        )}

        {/* Tab 3: Cron Jobs */}
        {activeTab === 'cron' && (
          <div className="space-y-2">
            {scheduledJobs.map((job) => {
              const isCloud = job.executionTarget === 'cloud';
              return (
                <div
                  key={job.id}
                  className="flex items-center justify-between rounded-xl border border-border/60 bg-muted/20 p-3"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-foreground text-xs">
                        {job.title}
                      </span>
                      <span
                        className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium ${
                          isCloud
                            ? 'bg-primary/10 text-primary border border-primary/20'
                            : 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20'
                        }`}
                      >
                        {isCloud ? (
                          <CloudLightning className="h-2.5 w-2.5" />
                        ) : (
                          <Laptop className="h-2.5 w-2.5" />
                        )}
                        {isCloud ? '云端常驻' : '本机设备'}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 text-[11px] font-mono text-muted-foreground">
                      <span>Cron: {job.cronExpression}</span>
                      <span>状态: {job.status === 'active' ? '运行中' : '暂停'}</span>
                    </div>
                  </div>

                  <span className="text-[11px] text-muted-foreground font-mono">
                    下次执行: {new Date(job.nextRunTime).toLocaleDateString()}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Zero Config Pairing Modal */}
      <ZeroConfigMobilePairingModal
        isOpen={isPairingModalOpen}
        onClose={() => {
          setIsPairingModalOpen(false);
        }}
      />
    </div>
  );
};
