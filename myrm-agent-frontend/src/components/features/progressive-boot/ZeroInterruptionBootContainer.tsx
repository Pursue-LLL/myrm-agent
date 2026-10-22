import React, { useState } from 'react';
import {
  Sparkles,
  Search,
  ArrowRight,
  Terminal,
  Cpu,
  Layers,
  Shield,
  Zap,
  HelpCircle,
} from 'lucide-react';
import { useProgressiveBootStore } from './useProgressiveBootStore';
import { SilentDaemonStatusBadge } from './SilentDaemonStatusBadge';
import { ProgressiveDisclosureDrawer } from './ProgressiveDisclosureDrawer';

export const ZeroInterruptionBootContainer: React.FC = () => {
  const { tier, suppressBlockingModal } = useProgressiveBootStore();
  const [promptInput, setPromptInput] = useState('');

  const quickStarters = [
    {
      title: '重构现有模块代码结构',
      desc: '识别坏味道、消除循环依赖并控制单文件行数',
    },
    {
      title: '排查沙箱运行时崩溃',
      desc: '捕获受限 stderr 环形缓冲并自动分类根因',
    },
    {
      title: '动态表单审批调和验证',
      desc: '验证 User AnswersState 优先于 Spec 默认值',
    },
  ];

  const handleSimulateBlockingPopup = () => {
    suppressBlockingModal({
      title: '检测到新版本插件待配置 (已静默)',
      source: 'ExternalPluginUpdater',
      severity: 'info',
      details: '该插件已在后台自动完成热加载，已自动豁免用户手动点按确认。',
    });
  };

  return (
    <div className="relative min-h-[560px] w-full rounded-2xl border border-slate-800 bg-slate-950 p-6 text-slate-100 shadow-2xl overflow-hidden">
      {/* 顶部极简导航栏 */}
      <header className="flex flex-col gap-4 border-b border-slate-800 pb-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-600/20 border border-indigo-500/30 text-indigo-400">
            <Sparkles className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-white tracking-tight">
              Myrmidon 智能体工作台
            </h1>
            <p className="text-xs text-slate-400">
              零阻断极简启动 • 渐进式能力披露 ({tier === 'minimal' ? '极简稳健档' : tier === 'standard' ? '标准生产档' : '专家底层档'})
            </p>
          </div>
        </div>

        {/* 右侧微型状态药丸与静默测试按钮 */}
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={handleSimulateBlockingPopup}
            aria-label="模拟触发侵入式弹窗"
            className="hidden sm:inline-flex items-center gap-1.5 rounded-lg border border-slate-800 bg-slate-900 px-2.5 py-1 text-xs text-slate-400 hover:text-slate-200 hover:border-slate-700 transition-colors"
          >
            <Shield className="h-3.5 w-3.5 text-indigo-400" />
            测试阻断弹窗静默拦截
          </button>
          <SilentDaemonStatusBadge />
        </div>
      </header>

      {/* 主体交互区域 */}
      <main className="mt-8 max-w-3xl mx-auto flex flex-col items-center text-center">
        <div className="inline-flex items-center gap-2 rounded-full border border-indigo-500/20 bg-indigo-500/10 px-3 py-1 text-xs font-medium text-indigo-300 mb-4">
          <Zap className="h-3.5 w-3.5 text-indigo-400" />
          开箱即用：底层 5 项服务已在后台静默待命
        </div>

        <h2 className="text-2xl font-bold text-white sm:text-3xl">
          需要我协助您完成什么任务？
        </h2>
        <p className="mt-2 text-sm text-slate-400 max-w-lg">
          告别繁冗弹窗与复杂的连接器堆砌。直接用自然语言描述目标，或从下方场景开始。
        </p>

        {/* 极简自然语言对话输入框 */}
        <div className="mt-6 w-full relative">
          <div className="relative flex items-center">
            <Search className="absolute left-4 h-4 w-4 text-slate-400" />
            <input
              type="text"
              value={promptInput}
              onChange={(e) => {
                setPromptInput(e.target.value);
              }}
              placeholder="输入任务需求，例如：'分析前端性能瓶颈并提出优化方案'..."
              className="w-full rounded-xl border border-slate-700/80 bg-slate-900/90 py-3.5 pl-11 pr-24 text-sm text-white placeholder-slate-500 shadow-inner focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/30"
            />
            <button
              type="button"
              className="absolute right-2 inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3.5 py-2 text-xs font-semibold text-white shadow-md hover:bg-indigo-500 transition-all focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <span>发送</span>
              <ArrowRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>

        {/* 快捷场景推荐卡片 */}
        <div className="mt-6 grid w-full grid-cols-1 gap-3 sm:grid-cols-3">
          {quickStarters.map((item, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => {
                setPromptInput(item.title);
              }}
              className="group flex flex-col items-start rounded-xl border border-slate-800 bg-slate-900/40 p-4 text-left transition-all hover:border-indigo-500/40 hover:bg-slate-800/60"
            >
              <div className="text-xs font-semibold text-slate-200 group-hover:text-white">
                {item.title}
              </div>
              <div className="mt-1 text-[11px] text-slate-400 leading-relaxed">
                {item.desc}
              </div>
            </button>
          ))}
        </div>

        {/* 渐进式能力披露卡片 (根据 Tier 动态呈现) */}
        {tier === 'standard' && (
          <div className="mt-8 w-full rounded-xl border border-slate-800 bg-slate-900/60 p-4 text-left animate-in fade-in">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2 text-xs font-semibold text-indigo-300">
                <Layers className="h-4 w-4" />
                标准生产档能力披露：当前会话激活技能与上下文
              </div>
              <span className="text-[11px] text-slate-400">已就绪 3 项预置工具</span>
            </div>
            <div className="grid grid-cols-3 gap-2 text-xs">
              <div className="rounded-lg bg-slate-800/50 p-2.5 border border-slate-800">
                <div className="font-medium text-slate-200">代码分析诊断器</div>
                <div className="text-[11px] text-slate-400">静态扫描 AST 语法树</div>
              </div>
              <div className="rounded-lg bg-slate-800/50 p-2.5 border border-slate-800">
                <div className="font-medium text-slate-200">沙箱执行调度器</div>
                <div className="text-[11px] text-slate-400">隔离执行 Python/Node 命令</div>
              </div>
              <div className="rounded-lg bg-slate-800/50 p-2.5 border border-slate-800">
                <div className="font-medium text-slate-200">动态表单调和守卫</div>
                <div className="text-[11px] text-slate-400">保护输入草稿免受覆盖</div>
              </div>
            </div>
          </div>
        )}

        {tier === 'expert' && (
          <div className="mt-8 w-full rounded-xl border border-indigo-500/30 bg-slate-900/80 p-4 text-left animate-in fade-in">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2 text-xs font-semibold text-indigo-300">
                <Cpu className="h-4 w-4" />
                专家底层档深度透视：MCP 连接器拓扑与沙箱遥测
              </div>
              <span className="text-[11px] text-emerald-400">沙箱内存 32MB / 4096MB</span>
            </div>
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="rounded-lg bg-slate-800/70 p-3 border border-slate-700/60">
                <div className="flex items-center gap-2 font-medium text-slate-200">
                  <Terminal className="h-3.5 w-3.5 text-indigo-400" />
                  PTC 标准协议通道
                </div>
                <div className="mt-1 text-[11px] text-slate-400">
                  双向全双工流式传输，已挂载 stderr 环形缓冲区
                </div>
              </div>
              <div className="rounded-lg bg-slate-800/70 p-3 border border-slate-700/60">
                <div className="flex items-center gap-2 font-medium text-slate-200">
                  <Cpu className="h-3.5 w-3.5 text-indigo-400" />
                  外部 MCP Bridge 探活
                </div>
                <div className="mt-1 text-[11px] text-slate-400">
                  3 个外部 MCP 服务正在以 25ms 延迟正常心跳通讯
                </div>
              </div>
            </div>
          </div>
        )}

        {/* 底部无感提示 */}
        <div className="mt-8 flex items-center justify-center gap-1.5 text-xs text-slate-400">
          <HelpCircle className="h-3.5 w-3.5" />
          <span>点击右上角服务徽标随时展开渐进式能力配置与静默通知</span>
        </div>
      </main>

      {/* 渐进能力披露抽屉 */}
      <ProgressiveDisclosureDrawer />
    </div>
  );
};
