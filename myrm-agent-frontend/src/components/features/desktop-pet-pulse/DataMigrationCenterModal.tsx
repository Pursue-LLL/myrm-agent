/**
 * DataMigrationCenterModal.tsx
 * 数据平滑无感导入与迁移中心：任务、定时Cron、记忆、MCP与智能体静默导入
 */

import React, { useState } from 'react';
import {
  ArrowDownCircle,
  CheckCircle,
  Database,
  FileCheck,
  RefreshCw,
  UploadCloud,
  X,
} from 'lucide-react';
import type {
  ConflictStrategy,
  DataMigrationBundle,
  DataMigrationCategory,
  MigrationReport,
} from './desktopPetPulseTypes';
import {
  executeDataMigrationMerge,
  validateMigrationBundle,
} from './desktopPetPulseEngine';
import { useDesktopPetPulseStore } from './useDesktopPetPulseStore';

export interface DataMigrationCenterModalProps {
  className?: string;
  onMigrationComplete?: (report: MigrationReport) => void;
  onClose?: () => void;
}

const defaultCategories: DataMigrationCategory[] = [
  'tasks',
  'crons',
  'memories',
  'mcps',
  'agents',
];

const categoryLabels: Record<DataMigrationCategory, string> = {
  tasks: '任务工单 (Tasks)',
  crons: '定时调度 (Cron Jobs)',
  memories: '长期记忆 (Memories)',
  mcps: 'MCP 服务 (MCP Servers)',
  agents: '自定义智能体 (Agents)',
};

export const DataMigrationCenterModal: React.FC<
  DataMigrationCenterModalProps
> = ({ className = '', onMigrationComplete, onClose }) => {
  const isMigrationModalOpen = useDesktopPetPulseStore(
    (state) => state.isMigrationModalOpen
  );
  const toggleMigrationModal = useDesktopPetPulseStore(
    (state) => state.toggleMigrationModal
  );
  const lastMigrationReport = useDesktopPetPulseStore(
    (state) => state.lastMigrationReport
  );
  const setLastMigrationReport = useDesktopPetPulseStore(
    (state) => state.setLastMigrationReport
  );

  const [selectedCategories, setSelectedCategories] =
    useState<DataMigrationCategory[]>(defaultCategories);
  const [strategy, setStrategy] = useState<ConflictStrategy>('merge');
  const [isProcessing, setIsProcessing] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  if (!isMigrationModalOpen) {
    return null;
  }

  const handleClose = (): void => {
    toggleMigrationModal(false);
    if (onClose !== undefined) {
      onClose();
    }
  };

  const handleToggleCategory = (cat: DataMigrationCategory): void => {
    if (selectedCategories.includes(cat)) {
      setSelectedCategories(selectedCategories.filter((c) => c !== cat));
    } else {
      setSelectedCategories([...selectedCategories, cat]);
    }
  };

  const executeMigrationWithBundle = (bundle: DataMigrationBundle): void => {
    setIsProcessing(true);
    setErrorMessage(null);

    try {
      const report = executeDataMigrationMerge(bundle, {
        selectedCategories,
        strategy,
      });

      setLastMigrationReport(report);
      if (onMigrationComplete !== undefined) {
        onMigrationComplete(report);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '数据迁移执行失败';
      setErrorMessage(msg);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleAutoDetectAndImport = (): void => {
    // 模拟自动探测并静默导入旧版或竞品数据
    const mockLegacyBundle: DataMigrationBundle = {
      version: '1.0.0',
      source: 'legacy_myrm',
      createdAt: Date.now(),
      tasks: [
        { id: 't-1', title: '代码健康度巡检', prompt: '检查仓库', createdAt: Date.now() },
        { id: 't-2', title: '周报生成任务', prompt: '汇总 commits', createdAt: Date.now() },
      ],
      crons: [
        { id: 'c-1', name: '每日凌晨测试', schedule: '0 0 * * *', prompt: 'run tests', enabled: true },
      ],
      memories: [
        { id: 'm-1', key: 'preferred_language', value: 'TypeScript' },
      ],
      mcps: [
        { id: 'mcp-1', name: 'chrome-devtools', command: 'bunx' },
      ],
      agents: [
        { id: 'ag-1', name: '架构重构专员', systemPrompt: '你是顶级架构师' },
      ],
    };

    executeMigrationWithBundle(mockLegacyBundle);
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>): void => {
    const file = e.target.files?.[0];
    if (file === undefined) {
      return;
    }

    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        const text = event.target?.result as string;
        const parsed: unknown = JSON.parse(text);
        const validation = validateMigrationBundle(parsed);
        if (!validation.valid || validation.bundle === undefined) {
          setErrorMessage(validation.error ?? '无效的迁移数据格式');
          return;
        }
        executeMigrationWithBundle(validation.bundle);
      } catch {
        setErrorMessage('文件解析失败，请上传合法 JSON 格式的迁移包');
      }
    };
    reader.readAsText(file);
  };

  return (
    <dialog
      open
      data-testid="data-migration-center-modal"
      aria-label="数据平滑导入与无感迁移中心"
      className={`fixed inset-0 m-auto w-full max-w-lg bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl p-5 z-50 text-slate-200 flex flex-col gap-4 backdrop:bg-slate-950/70 ${className}`}
    >
      {/* 头部 */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-3">
        <div className="flex items-center gap-2">
          <Database className="w-5 h-5 text-emerald-400" />
          <h2 className="text-base font-semibold">
            数据无感平滑迁移中心
          </h2>
        </div>
        <button
          type="button"
          data-testid="close-migration-modal-btn"
          aria-label="关闭数据迁移弹窗"
          onClick={handleClose}
          className="p-1 rounded text-slate-400 hover:text-slate-200 hover:bg-slate-800"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* 描述信息 */}
      <p className="text-xs text-slate-400 leading-relaxed">
        自动探测旧版 Myrm、Qoder、Hermes 或 Cursor 配置与数据，无缝将任务、Cron 计划、记忆及 MCP 迁移至当前环境。
      </p>

      {/* 迁移项多选 */}
      <fieldset className="flex flex-col gap-2">
        <legend className="text-xs font-medium text-slate-300">
          选择迁移内容类别:
        </legend>
        <div className="grid grid-cols-2 gap-2 text-xs">
          {defaultCategories.map((cat) => (
            <label
              key={cat}
              htmlFor={`cat-checkbox-${cat}`}
              className="flex items-center gap-2 p-2 rounded-lg bg-slate-950/60 border border-slate-800 hover:border-slate-700 cursor-pointer"
            >
              <input
                id={`cat-checkbox-${cat}`}
                data-testid={`category-checkbox-${cat}`}
                type="checkbox"
                checked={selectedCategories.includes(cat)}
                onChange={() => handleToggleCategory(cat)}
                className="rounded border-slate-700 text-blue-600 focus:ring-0"
              />
              <span className="text-slate-300">{categoryLabels[cat]}</span>
            </label>
          ))}
        </div>
      </fieldset>

      {/* 冲突合并策略 */}
      <div className="flex items-center justify-between gap-3 bg-slate-950/50 p-2.5 rounded-xl border border-slate-800">
        <label
          htmlFor="migration-strategy-select"
          className="text-xs font-medium text-slate-300"
        >
          数据冲突合并策略:
        </label>
        <select
          id="migration-strategy-select"
          data-testid="migration-strategy-select"
          value={strategy}
          onChange={(e) => setStrategy(e.target.value as ConflictStrategy)}
          className="text-xs bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 text-slate-200 focus:outline-none focus:border-blue-500"
        >
          <option value="merge">增量合并 (Merge)</option>
          <option value="skip">跳过已存在 (Skip)</option>
          <option value="overwrite">覆盖旧数据 (Overwrite)</option>
        </select>
      </div>

      {/* 错误提示 */}
      {errorMessage !== null && (
        <div
          data-testid="migration-error-message"
          className="text-xs text-red-400 bg-red-950/30 p-2 rounded-lg border border-red-800/50"
        >
          {errorMessage}
        </div>
      )}

      {/* 迁移报告结果 */}
      {lastMigrationReport !== null && (
        <div
          data-testid="migration-report-summary"
          className="bg-emerald-950/30 border border-emerald-600/40 rounded-xl p-3 flex flex-col gap-1.5 text-xs text-emerald-200"
        >
          <div className="flex items-center gap-1.5 font-semibold text-emerald-300">
            <CheckCircle className="w-4 h-4 text-emerald-400" />
            <span>迁移完成（来源: {lastMigrationReport.source}）</span>
          </div>
          <div className="text-[11px] text-emerald-300/80">
            成功导入:{' '}
            {Object.entries(lastMigrationReport.importedCounts)
              .map(([k, v]) => `${k}: ${v}`)
              .join(' | ')}
          </div>
        </div>
      )}

      {/* 动作区 */}
      <div className="flex items-center justify-between pt-2 border-t border-slate-800">
        {/* 文件上传触发 */}
        <label
          htmlFor="migration-bundle-file-input"
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-800 text-slate-300 hover:bg-slate-700 cursor-pointer border border-slate-700"
        >
          <UploadCloud className="w-3.5 h-3.5" />
          <span>上传 .myrm-bundle</span>
          <input
            id="migration-bundle-file-input"
            data-testid="migration-bundle-file-input"
            type="file"
            accept=".json,.myrm-bundle"
            onChange={handleFileUpload}
            className="hidden"
          />
        </label>

        {/* 自动探测并迁移按钮 */}
        <button
          type="button"
          data-testid="auto-detect-import-btn"
          disabled={isProcessing || selectedCategories.length === 0}
          onClick={handleAutoDetectAndImport}
          className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 text-white hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed shadow transition-colors"
        >
          {isProcessing ? (
            <>
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              <span>正在无感导入...</span>
            </>
          ) : (
            <>
              <ArrowDownCircle className="w-3.5 h-3.5" />
              <span>一键自动探测并导入</span>
            </>
          )}
        </button>
      </div>
    </dialog>
  );
};
