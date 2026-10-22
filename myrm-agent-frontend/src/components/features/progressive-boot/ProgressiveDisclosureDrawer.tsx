import React from 'react';
import {
  X,
  Layers,
  Sparkles,
  Cpu,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Trash2,
  Sliders,
} from 'lucide-react';
import { useProgressiveBootStore } from './useProgressiveBootStore';
import type { DisclosureTier } from './progressiveBootTypes';

export const ProgressiveDisclosureDrawer: React.FC = () => {
  const {
    isDrawerOpen,
    tier,
    services,
    silencedNotices,
    toggleDrawer,
    setDisclosureTier,
    dismissNotice,
  } = useProgressiveBootStore();

  if (!isDrawerOpen) {
    return null;
  }

  const tiersConfig: Array<{
    id: DisclosureTier;
    label: string;
    desc: string;
    icon: React.ComponentType<{ className?: string }>;
  }> = [
    {
      id: 'minimal',
      label: '极简稳健档',
      desc: '零干扰纯净对话，底层工具与连接器全部静默待命',
      icon: Sparkles,
    },
    {
      id: 'standard',
      label: '标准生产档',
      desc: '按需披露当前会话依赖的预置技能与任务进度卡片',
      icon: Layers,
    },
    {
      id: 'expert',
      label: '底层专家档',
      desc: '全量展开 MCP 连接器调试、沙箱资源拓扑与长程控制台',
      icon: Cpu,
    },
  ];

  return (
    <section
      aria-label="能力披露与后台静默控制中心"
      className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-slate-800 bg-slate-900/95 text-slate-100 shadow-2xl backdrop-blur-xl transition-all animate-in slide-in-from-right duration-200"
    >
      {/* 抽屉头部 */}
      <div className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
        <div className="flex items-center gap-2">
          <Sliders className="h-4 w-4 text-indigo-400" />
          <h2 className="text-base font-semibold text-white">
            渐进式能力披露与服务状态
          </h2>
        </div>
        <button
          type="button"
          onClick={() => {
            toggleDrawer(false);
          }}
          aria-label="关闭抽屉"
          className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-5 space-y-6">
        {/* 1. 渐进式披露档位切换 */}
        <section aria-label="能力披露档位选择">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3">
            界面复杂度与披露档位
          </h3>
          <div className="space-y-2">
            {tiersConfig.map((item) => {
              const Icon = item.icon;
              const isSelected = tier === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => {
                    setDisclosureTier(item.id);
                  }}
                  className={`w-full text-left rounded-lg border p-3 transition-all ${
                    isSelected
                      ? 'border-indigo-500 bg-indigo-600/10 text-white shadow-sm ring-1 ring-indigo-500/50'
                      : 'border-slate-800 bg-slate-800/40 text-slate-300 hover:border-slate-700 hover:bg-slate-800/70'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2.5">
                      <Icon
                        className={`h-4 w-4 ${
                          isSelected ? 'text-indigo-400' : 'text-slate-400'
                        }`}
                      />
                      <span className="text-sm font-semibold">{item.label}</span>
                    </div>
                    {isSelected && (
                      <span className="inline-flex items-center gap-1 text-[11px] font-medium text-indigo-400">
                        <CheckCircle2 className="h-3 w-3" />
                        当前激活
                      </span>
                    )}
                  </div>
                  <p className="mt-1 text-xs text-slate-400 pl-6.5">
                    {item.desc}
                  </p>
                </button>
              );
            })}
          </div>
        </section>

        {/* 2. 静默拦截通知箱 (原弹窗拦截归档) */}
        <section aria-label="被静默拦截的非阻断通知">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              已静默拦截的通知 ({silencedNotices.length})
            </h3>
          </div>

          {silencedNotices.length === 0 ? (
            <div className="rounded-lg border border-slate-800 bg-slate-800/20 p-4 text-center">
              <CheckCircle2 className="mx-auto h-5 w-5 text-emerald-400 mb-1" />
              <p className="text-xs text-slate-300">
                启动阶段零干扰，无任何侵入式弹窗产生
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {silencedNotices.map((notice) => (
                <div
                  key={notice.id}
                  className="rounded-lg border border-slate-800 bg-slate-800/50 p-3 text-xs"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-start gap-2">
                      {notice.severity === 'warning' ? (
                        <AlertTriangle className="h-3.5 w-3.5 text-amber-400 mt-0.5 shrink-0" />
                      ) : (
                        <Sparkles className="h-3.5 w-3.5 text-indigo-400 mt-0.5 shrink-0" />
                      )}
                      <div>
                        <div className="font-semibold text-slate-200">
                          {notice.title}
                        </div>
                        <div className="text-[11px] text-slate-400">
                          来源: {notice.source}
                        </div>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        dismissNotice(notice.id);
                      }}
                      aria-label="移除此条通知"
                      className="text-slate-500 hover:text-slate-300 p-0.5"
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </div>
                  {notice.details && (
                    <p className="mt-2 text-slate-400 text-[11px] pl-5.5">
                      {notice.details}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>

        {/* 3. 后台服务健康待命状态 */}
        <section aria-label="后台静默服务健康矩阵">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3">
            后台静默守护服务矩阵
          </h3>
          <div className="space-y-2">
            {services.map((srv) => (
              <div
                key={srv.id}
                className="flex items-center justify-between rounded-lg border border-slate-800/60 bg-slate-800/30 p-2.5 text-xs"
              >
                <div>
                  <div className="font-medium text-slate-200">{srv.name}</div>
                  <div className="text-[11px] text-slate-400">
                    {srv.description}
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="flex items-center gap-1 text-[11px] text-slate-400">
                    <Clock className="h-3 w-3 text-slate-500" />
                    {srv.latencyMs}ms
                  </span>
                  <span
                    className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${
                      srv.isReady
                        ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                        : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                    }`}
                  >
                    {srv.isReady ? '待命中' : '探活中'}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </section>
  );
};
