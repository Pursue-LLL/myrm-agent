import React, { useState } from 'react';
import {
  Database,
  Sparkles,
  Upload,
  CheckCircle,
  Clock,
  Layers,
  Brain,
  Cpu,
  FileSpreadsheet,
  Terminal,
  ShieldCheck,
  RefreshCw,
} from 'lucide-react';
import { useDataMigrationStore } from './useDataMigrationStore';
import { MigrationReconciliationModal } from './MigrationReconciliationModal';
import { MigrationSilentToast } from './MigrationSilentToast';
import { MigrationSourceType, FourDimensionalAssets } from './dataMigrationTypes';

export interface DataMigrationSectionProps {
  className?: string;
}

export const DataMigrationSection: React.FC<DataMigrationSectionProps> = ({
  className = '',
}) => {
  const {
    autoSilentImportEnabled,
    status,
    logs,
    activeReport,
    setAutoSilentImportEnabled,
    triggerSilentDetection,
    loadIncomingData,
    toggleReconciliationModal,
  } = useDataMigrationStore();

  const [selectedPresetSource, setSelectedPresetSource] =
    useState<MigrationSourceType>('qoder_v1');

  const handleSimulateSourceImport = (sourceType: MigrationSourceType) => {
    setSelectedPresetSource(sourceType);

    const mockAssets: FourDimensionalAssets = {
      tasks: [
        {
          id: `task-${sourceType}-01`,
          title: `[${sourceType}] 全栈代码分析与性能重构`,
          createdAt: Date.now() - 172800000,
          status: 'completed',
        },
      ],
      cronJobs: [
        {
          id: `cron-${sourceType}-01`,
          name: `[${sourceType}] 每周依赖版本巡检`,
          cronExpression: '0 9 * * 1',
          taskTemplate: 'dependency_audit',
          enabled: true,
        },
      ],
      memories: [
        {
          id: `mem-${sourceType}-01`,
          category: 'project',
          content: '项目架构采用模块化与微前端设计',
          confidence: 0.98,
          createdAt: Date.now() - 172800000,
        },
      ],
      mcpConfigs: [
        {
          name: `${sourceType}-database-mcp`,
          transport: 'stdio',
          command: 'python',
          args: ['-m', 'sqlite_mcp_server', '/data/db.sqlite'],
          enabled: true,
        },
      ],
    };

    loadIncomingData(mockAssets, sourceType, `~/.${sourceType}/backup.json`);
  };

  return (
    <div
      data-testid="data-migration-section"
      className={`p-6 max-w-4xl mx-auto space-y-6 font-sans text-zinc-100 ${className}`}
    >
      {/* 1. 顶部标题 */}
      <header className="space-y-1">
        <div className="flex items-center gap-2">
          <div className="p-2 rounded-xl bg-indigo-600/20 text-indigo-400 border border-indigo-500/30">
            <Database className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-base font-bold text-zinc-100">
              数据导入与历史资产无损迁移
            </h2>
            <p className="text-xs text-zinc-400">
              从老版 Qoder、Hermes、OpenClaw 或历史备份平滑搬家，任务、定时、记忆、MCP 资产零感知对齐
            </p>
          </div>
        </div>
      </header>

      {/* 2. 启动期后台静默探测设置卡片 */}
      <section className="p-4 rounded-2xl bg-zinc-900/90 border border-zinc-800 space-y-3 shadow-lg">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-indigo-500/10 text-indigo-400">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-zinc-200">
                启动期自动静默巡检与导入
              </h3>
              <p className="text-xs text-zinc-400">
                初次启动或升级新版时，后台自动扫描已知旧目录，静默完成 Schema 兼容对账
              </p>
            </div>
          </div>

          <label
            aria-label="自动静默巡检与导入开关"
            className="relative inline-flex items-center cursor-pointer"
          >
            <input
              type="checkbox"
              checked={autoSilentImportEnabled}
              onChange={(e) => {
                setAutoSilentImportEnabled(e.target.checked);
              }}
              className="sr-only peer"
            />
            <div className="w-11 h-6 bg-zinc-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-zinc-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-indigo-600" />
          </label>
        </div>

        <div className="flex items-center justify-between pt-2 border-t border-zinc-850 text-xs">
          <span className="text-zinc-500 font-mono text-[11px]">
            检测路径: ~/.qoder, ~/.hermes, ~/.openclaw, Local SQLite
          </span>
          <button
            type="button"
            onClick={() => {
              triggerSilentDetection('qoder_v1');
            }}
            disabled={!autoSilentImportEnabled || status === 'scanning'}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-indigo-300 text-xs font-semibold disabled:opacity-40 transition-colors"
          >
            <RefreshCw
              className={`w-3.5 h-3.5 ${status === 'scanning' ? 'animate-spin' : ''}`}
            />
            <span>立即执行后台静默扫描</span>
          </button>
        </div>
      </section>

      {/* 3. 常见旧版智能体快速迁入卡片网格 */}
      <section className="space-y-3">
        <h3 className="text-xs font-bold text-zinc-300 tracking-wider uppercase font-mono">
          一键预置来源导入通道
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {[
            {
              key: 'qoder_v1' as const,
              title: '老版 Qoder 工作台',
              desc: '导入历史定时任务、长短期记忆与 MCP 配置',
              badge: '推荐 · 官方无损映射',
            },
            {
              key: 'hermes_legacy' as const,
              title: 'Hermes 历史环境',
              desc: '导入历史任务记录与环境变量配置',
              badge: '兼容 ~/.hermes',
            },
            {
              key: 'openclaw' as const,
              title: 'OpenClaw Agent',
              desc: '导入多智能体编排与工作流模版',
              badge: '兼容 ~/.openclaw',
            },
          ].map((src) => (
            <div
              key={src.key}
              className="p-4 rounded-2xl bg-zinc-900/90 border border-zinc-800 hover:border-indigo-500/40 transition-all space-y-2.5 flex flex-col justify-between"
            >
              <div className="space-y-1">
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">
                  {src.badge}
                </span>
                <h4 className="text-xs font-bold text-zinc-100">{src.title}</h4>
                <p className="text-[11px] text-zinc-400 leading-relaxed font-sans">
                  {src.desc}
                </p>
              </div>

              <button
                type="button"
                onClick={() => {
                  handleSimulateSourceImport(src.key);
                }}
                className="w-full py-1.5 px-3 rounded-lg bg-zinc-800 hover:bg-indigo-600 text-zinc-200 hover:text-white text-xs font-semibold transition-colors flex items-center justify-center gap-1"
              >
                <Upload className="w-3.5 h-3.5" />
                <span>载入并对账</span>
              </button>
            </div>
          ))}
        </div>
      </section>

      {/* 4. 手动文件归档上传对账区 */}
      <section className="p-4 rounded-2xl bg-zinc-900/90 border border-zinc-800 space-y-3">
        <h3 className="text-xs font-bold text-zinc-200">
          自定义 SQLite / JSON 数据包导入
        </h3>
        <p className="text-[11px] text-zinc-400">
          支持从外部导出的 .sqlite、.db 或 JSON 资产清单文件进行宽类型容错转换
        </p>

        <div className="border-2 border-dashed border-zinc-750 hover:border-indigo-500 rounded-xl p-6 text-center space-y-2 transition-colors cursor-pointer bg-zinc-950/40">
          <Upload className="w-8 h-8 text-zinc-500 mx-auto" />
          <div className="text-xs text-zinc-300">
            <span className="font-semibold text-indigo-400">点击选择归档文件</span>{' '}
            或拖拽文件至此处
          </div>
          <p className="text-[10px] text-zinc-500 font-mono">
            支持 *.json, *.db, *.sqlite 格式（单文件最大 100MB）
          </p>
        </div>
      </section>

      {/* 5. 迁移历史与审计日志 */}
      {logs.length > 0 && (
        <section className="p-4 rounded-2xl bg-zinc-900/90 border border-zinc-800 space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="font-semibold text-zinc-200 flex items-center gap-1.5 font-mono">
              <Terminal className="w-3.5 h-3.5 text-indigo-400" />
              数据迁移审计日志 ({logs.length})
            </span>
            {activeReport && (
              <button
                type="button"
                onClick={() => {
                  toggleReconciliationModal(true);
                }}
                className="text-[11px] text-indigo-400 hover:underline flex items-center gap-1 font-mono"
              >
                <FileSpreadsheet className="w-3 h-3" />
                <span>查看当前对账单</span>
              </button>
            )}
          </div>

          <div className="space-y-1.5 max-h-44 overflow-y-auto">
            {logs.map((log) => (
              <div
                key={log.id}
                className="flex items-start gap-2 p-2 rounded-lg bg-zinc-950 border border-zinc-850 text-[11px] font-mono text-zinc-300"
              >
                <span className="text-zinc-500 shrink-0">
                  {new Date(log.timestamp).toLocaleTimeString()}
                </span>
                <span className="text-indigo-400 font-bold shrink-0">
                  [{log.level.toUpperCase()}]
                </span>
                <span className="truncate">{log.message}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* 模态对账弹窗与轻量通知挂载 */}
      <MigrationReconciliationModal />
      <MigrationSilentToast />
    </div>
  );
};
